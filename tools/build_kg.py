"""One command to build the knowledge graph the production way - through
redis queues and celery workers, exactly as the deployed system runs it.

Checks the infra containers (starts them via docker compose if needed),
applies the neo4j schema, launches one celery worker per pipeline stage,
submits the given documents, watches the queues drain, then reports what
landed in the graph.

usage:
    python -m tools.build_kg data/samples/work_orders.csv [...]
    python -m tools.build_kg --keep ...      leave workers running afterwards
"""

import subprocess
import sys
import time
from pathlib import Path

from plantmind_core.bus import RedisBus
from plantmind_core.config import get_settings
from plantmind_core.devtools import find_file

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "logs"

# name, celery app module, queues, pool, concurrency, beat
# (prefork is broken on windows, so threads/solo pools)
WORKERS = [
    ("ingestion", "ingestion.tasks", "q_classify", "threads", 4, False),
    ("extraction", "extraction.tasks",
     "q_parse_wo,q_extract_pnid,q_extract_text", "threads", 8, False),
    ("resolution", "resolution.tasks", "q_resolve", "threads", 4, False),
    ("graphd", "graphd.writer", "q_write", "solo", 1, True),
]


class StackRunner:
    def __init__(self):
        self.settings = get_settings()
        self.procs = []
        self.bus = None

    # ---------------------------------------------------------------- infra
    def ensure_infra(self):
        if self._redis_up():
            print("infra: redis reachable")
        else:
            print("infra: starting containers (docker compose)...")
            subprocess.run(["docker", "compose", "up", "-d",
                            "redis", "neo4j", "minio"],
                           cwd=REPO, check=True)
        deadline = time.time() + 180
        while time.time() < deadline:
            if self._redis_up() and self._neo4j_up():
                self.bus = RedisBus.from_settings()
                print("infra: redis + neo4j + minio ready")
                return
            time.sleep(3)
        raise RuntimeError("infra did not come up within 3 minutes")

    def _redis_up(self) -> bool:
        try:
            import redis
            return redis.Redis.from_url(self.settings.redis_url,
                                        socket_connect_timeout=2).ping()
        except Exception:
            return False

    def _neo4j_up(self) -> bool:
        try:
            from neo4j import GraphDatabase
            with GraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user,
                          self.settings.neo4j_password)) as driver:
                driver.verify_connectivity()
            return True
        except Exception:
            return False

    def apply_schema(self):
        from neo4j import GraphDatabase
        statements = [s.strip() for s in
                      (REPO / "infra" / "neo4j" / "init.cypher")
                      .read_text().split(";") if s.strip()
                      and not s.strip().startswith("//")]
        applied = skipped = 0
        with GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user,
                      self.settings.neo4j_password)) as driver:
            for stmt in statements:
                try:
                    driver.execute_query(stmt)
                    applied += 1
                except Exception as e:      # e.g. role grants on community edition
                    skipped += 1
                    print(f"schema: skipped one statement ({str(e)[:80]})")
        print(f"schema: {applied} statements applied, {skipped} skipped")

    # -------------------------------------------------------------- workers
    def start_workers(self):
        LOGS.mkdir(exist_ok=True)
        for name, module, queues, pool, conc, beat in WORKERS:
            cmd = [sys.executable, "-m", "celery", "-A", module, "worker",
                   "-Q", queues, "-P", pool, "-c", str(conc),
                   "--loglevel", "info"]
            if beat:
                cmd += ["-B", "-s", str(LOGS / "beat-schedule")]
            logfile = open(LOGS / f"{name}.log", "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, cwd=REPO, stdout=logfile,
                                    stderr=subprocess.STDOUT)
            self.procs.append((name, proc, logfile))
            print(f"worker: {name} started (pid {proc.pid}, queues {queues})")
        time.sleep(8)      # let them connect before we submit

    # --------------------------------------------------------------- submit
    def submit(self, paths):
        from plantmind_core.celeryapp import WorkerApp
        from plantmind_core.storage import ObjectStore
        from ingestion.submit import submit_file

        sender = WorkerApp("build-kg-cli").send
        store = ObjectStore.from_settings()
        for path in paths:
            submit_file(path, store, sender, source="build_kg")
            print(f"submitted: {path.name}")

    # ---------------------------------------------------------------- watch
    def wait_drained(self, timeout=600):
        print("\nwatching queues (ctrl+c to stop waiting)...")
        idle_polls = 0
        last_line = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            depths = self.bus.depths()
            version = self.bus.graph_version()
            line = "  ".join(f"{q}:{n}" for q, n in depths.items() if n) \
                or "all empty"
            if line != last_line:
                print(f"queues: {line}   graph v{version}")
                last_line = line
            # empty queues can still mean in-flight tasks; require it to
            # stay empty across several polls before calling it done
            idle_polls = idle_polls + 1 if not any(depths.values()) else 0
            if idle_polls >= 5:
                print(f"pipeline drained (graph version {version})")
                return
            time.sleep(2)
        print("warning: timeout waiting for drain - check logs/")

    # --------------------------------------------------------------- report
    def report(self):
        from neo4j import GraphDatabase
        with GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user,
                      self.settings.neo4j_password)) as driver:
            counts, _, _ = driver.execute_query(
                "MATCH (n) UNWIND labels(n) AS l "
                "WITH l WHERE l <> 'Entity' "
                "RETURN l AS label, count(*) AS n ORDER BY n DESC")
            edges, _, _ = driver.execute_query(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n "
                "ORDER BY n DESC")
            failures, _, _ = driver.execute_query(
                "MATCH (e:Equipment)-[:HAS_FAILURE]->(f) "
                "RETURN e.surface_form AS tag, collect(f.surface_form) AS modes")

        print("\n=== knowledge graph ===")
        for rec in counts:
            print(f"  {rec['label']:20s} {rec['n']}")
        print("  ---")
        for rec in edges:
            print(f"  {rec['t']:20s} {rec['n']}")
        if failures:
            print("\n=== failure history (from graph) ===")
            for rec in failures:
                print(f"  {rec['tag']}: {', '.join(rec['modes'])}")

    # ------------------------------------------------------------- shutdown
    def shutdown(self):
        for name, proc, logfile in self.procs:
            proc.terminate()
            logfile.close()
        if self.procs:
            print(f"workers stopped ({len(self.procs)}) - logs in logs/")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep = "--keep" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    paths = [find_file(a) for a in args]

    runner = StackRunner()
    runner.ensure_infra()
    runner.apply_schema()
    runner.start_workers()
    try:
        runner.submit(paths)
        runner.wait_drained()
        runner.report()
    finally:
        if keep:
            print("workers left running (--keep)")
        else:
            runner.shutdown()


if __name__ == "__main__":
    main()
