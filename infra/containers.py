"""The infrastructure containers (redis, neo4j, minio): health checks,
startup via docker compose, and neo4j schema application."""

import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class Infrastructure:
    def __init__(self, settings):
        self._s = settings

    def up(self, timeout=180):
        if all(self.health().values()):
            print("infra: redis + neo4j + minio already up")
            return
        print("infra: starting containers...")
        subprocess.run(["docker", "compose", "up", "-d",
                        "redis", "neo4j", "minio"], cwd=REPO, check=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if all(self.health().values()):
                print("infra: all healthy")
                return
            time.sleep(3)
        down = [name for name, ok in self.health().items() if not ok]
        raise RuntimeError(f"infra not healthy after {timeout}s: {down} "
                           f"- check 'docker compose logs {' '.join(down)}'")

    def health(self) -> dict:
        return {"redis": self._redis_ok(), "neo4j": self._neo4j_ok(),
                "minio": self._minio_ok()}

    def _redis_ok(self):
        try:
            import redis
            return redis.Redis.from_url(self._s.redis_url,
                                        socket_connect_timeout=2).ping()
        except Exception:
            return False

    def _neo4j_ok(self):
        try:
            from neo4j import GraphDatabase
            with GraphDatabase.driver(
                    self._s.neo4j_uri,
                    auth=(self._s.neo4j_user, self._s.neo4j_password)) as d:
                d.verify_connectivity()
            return True
        except Exception:
            return False

    def _minio_ok(self):
        try:
            import urllib.request
            urllib.request.urlopen(
                self._s.minio_endpoint + "/minio/health/live", timeout=2)
            return True
        except Exception:
            return False

    def apply_schema(self):
        from neo4j import GraphDatabase
        # drop comment LINES first, then split - a statement with a comment
        # above it must not be mistaken for a comment itself
        text = (REPO / "infra" / "neo4j" / "init.cypher").read_text()
        code = "\n".join(l for l in text.splitlines()
                         if not l.strip().startswith("//"))
        statements = [s.strip() for s in code.split(";") if s.strip()]

        applied = skipped = 0
        with GraphDatabase.driver(
                self._s.neo4j_uri,
                auth=(self._s.neo4j_user, self._s.neo4j_password)) as driver:
            for stmt in statements:
                try:
                    driver.execute_query(stmt)
                    applied += 1
                except Exception as e:   # e.g. user/role admin on community
                    skipped += 1
                    print(f"schema: skipped '{stmt[:45]}...' ({str(e)[:60]})")
        print(f"schema: {applied} applied, {skipped} skipped")
