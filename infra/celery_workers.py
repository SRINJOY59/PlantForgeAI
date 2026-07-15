"""Local celery worker processes, one per pipeline stage - the dev-machine
equivalent of the worker containers in docker-compose.yml."""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "logs"


class WorkerFleet:
    # name, app module, queues, pool, concurrency, beat
    # (prefork is broken on windows, hence threads/solo pools)
    SPECS = [
        ("ingestion", "ingestion.tasks", "q_classify", "threads", 4, False),
        ("extraction", "extraction.tasks",
         "q_parse_wo,q_extract_pnid,q_extract_text", "threads", 8, False),
        ("resolution", "resolution.tasks", "q_resolve", "threads", 4, False),
        ("graphd", "graphd.writer", "q_write", "solo", 1, True),
    ]

    def __init__(self):
        self._procs = []

    def start(self, settle_seconds=8):
        LOGS.mkdir(exist_ok=True)
        for name, module, queues, pool, conc, beat in self.SPECS:
            self._spawn(name, [sys.executable, "-m", "celery", "-A", module,
                               "worker", "-Q", queues, "-P", pool,
                               "-c", str(conc), "--loglevel", "info"])
            if beat:
                # celery's embedded beat (-B) refuses to run on windows,
                # so the scheduler gets its own process
                self._spawn(f"{name}-beat",
                            [sys.executable, "-m", "celery", "-A", module,
                             "beat", "-s", str(LOGS / "beat-schedule"),
                             "--loglevel", "info"])
        time.sleep(settle_seconds)   # let them connect before anyone submits

    def _spawn(self, name, cmd):
        logfile = open(LOGS / f"{name}.log", "a", encoding="utf-8")
        logfile.write(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        logfile.flush()
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=logfile,
                                stderr=subprocess.STDOUT)
        self._procs.append((name, proc, logfile))
        print(f"worker: {name} up (pid {proc.pid})")

    def stop(self):
        for name, proc, logfile in self._procs:
            proc.terminate()
            logfile.close()
        if self._procs:
            print(f"workers stopped ({len(self._procs)}) - logs in logs/")
        self._procs = []
