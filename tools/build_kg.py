"""Build the knowledge graph the production way - through redis queues and
celery workers, exactly as the deployed system runs.

Phases: infra up -> schema -> workers up -> submit -> drain -> report.

usage:
    python -m tools.build_kg data/samples            whole directory
    python -m tools.build_kg data/samples/work_orders.csv [...]
    python -m tools.build_kg --keep ...              leave workers running
"""

import sys
import time

from plantmind_core.bus import RedisBus
from plantmind_core.config import get_settings
from plantmind_core.devtools import find_file
from plantmind_core.queues import Flow

from infra import Infrastructure, WorkerFleet


class KGBuilder:
    """Submits documents into the pipeline, watches the queues drain,
    reports what landed in the graph."""

    def __init__(self, settings):
        self._s = settings
        self._bus = RedisBus.from_settings()

    def submit(self, paths):
        """Every file enters the same way: bytes to staging, a note to the
        pipeline's entry queue (Flow.ingest). Routing to the right worker
        happens inside the pipeline, per the topology."""
        from plantmind_core.celeryapp import WorkerApp
        from plantmind_core.storage import ObjectStore
        from ingestion.submit import submit_file

        sender = WorkerApp("build-kg-cli").send
        store = ObjectStore.from_settings()
        for path in paths:
            submit_file(path, store, sender, source="build_kg")
            print(f"submitted: {path.name}")

    def wait_drained(self, timeout=600):
        """Empty queues can still hide in-flight tasks, so 'drained' means
        every depth stayed zero across several consecutive polls."""
        print("\nwatching queues (ctrl+c to stop waiting)...")
        idle_polls, last_line = 0, ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            depths = self._bus.depths()
            line = "  ".join(f"{q}:{n}" for q, n in depths.items() if n) \
                or "all empty"
            if line != last_line:
                print(f"queues: {line}   graph v{self._bus.graph_version()}")
                last_line = line
            idle_polls = idle_polls + 1 if not any(depths.values()) else 0
            if idle_polls >= 5:
                print(f"pipeline drained (graph version "
                      f"{self._bus.graph_version()})")
                return
            time.sleep(2)
        print("warning: timeout waiting for drain - check logs/")

    def report(self):
        from neo4j import GraphDatabase
        with GraphDatabase.driver(
                self._s.neo4j_uri,
                auth=(self._s.neo4j_user, self._s.neo4j_password)) as driver:
            nodes, _, _ = driver.execute_query(
                "MATCH (n) UNWIND labels(n) AS l WITH l WHERE l <> 'Entity' "
                "RETURN l AS label, count(*) AS n ORDER BY n DESC")
            edges, _, _ = driver.execute_query(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n "
                "ORDER BY n DESC")
            failures, _, _ = driver.execute_query(
                "MATCH (e:Equipment)-[:HAS_FAILURE]->(f) "
                "RETURN e.surface_form AS tag, "
                "collect(DISTINCT f.surface_form) AS modes")

        print("\n=== knowledge graph ===")
        for rec in nodes:
            print(f"  {rec['label']:20s} {rec['n']}")
        print("  ---")
        for rec in edges:
            print(f"  {rec['t']:20s} {rec['n']}")
        if failures:
            print("\n=== failure history (from graph) ===")
            for rec in failures:
                print(f"  {rec['tag']}: {', '.join(rec['modes'])}")


def gather(args) -> list:
    """Files and/or directories; directories submit every regular file inside."""
    paths = []
    for arg in args:
        p = find_file(arg)
        if p.is_dir():
            paths.extend(sorted(
                f for f in p.iterdir()
                if f.is_file() and not f.name.startswith(".")))
        else:
            paths.append(p)
    return paths


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep = "--keep" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    paths = gather(args)

    # 1. the pipeline topology (queues and their order), declared in core
    print("pipeline topology:")
    print(Flow.describe())

    # 2. infrastructure: the shared memory everything coordinates through
    settings = get_settings()
    infra = Infrastructure(settings)
    infra.up()
    infra.apply_schema()

    # 3. the workers that consume those queues
    fleet = WorkerFleet()
    fleet.start()

    # 4. the documents
    builder = KGBuilder(settings)
    print(f"\nsubmitting {len(paths)} files:")
    try:
        builder.submit(paths)
        builder.wait_drained()
        builder.report()
    finally:
        if keep:
            print("workers left running (--keep)")
        else:
            fleet.stop()


if __name__ == "__main__":
    main()
