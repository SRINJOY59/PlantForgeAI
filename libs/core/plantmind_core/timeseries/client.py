"""The plant's time-series system of record.

One narrow wrapper over a Postgres connection, the way storage/objectstore.py
wraps MinIO: services speak in telemetry rows and time windows, and the SQL,
the connection handling and the TimescaleDB-vs-plain-Postgres branch all stay
in here.

Portable on purpose. The same code runs against Timescale Cloud, where it gets
a hypertable with compression and a retention policy, and against Supabase or
any stock Postgres, where it falls back to a plain indexed table. It decides by
looking for the timescaledb extension at schema time - callers never know or
care which they got, because the read and write surface is identical.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

try:
    import psycopg
except ModuleNotFoundError:
    # the driver ships only in the historian image; leaving core importable
    # without it means every other service and the tests don't carry a
    # Postgres dependency they never use. Opening a connection re-checks.
    psycopg = None

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("timeseries")

TABLE = "plant_telemetry"

# Fail fast rather than hang. Both exist so a stalled cloud instance surfaces
# as a logged, retried error instead of a silently dead historian.
CONNECT_TIMEOUT_S = 10
STATEMENT_TIMEOUT_MS = 30_000


@dataclass
class TelemetryRow:
    """One sample, as the sink hands it to the DB and the reader hands it back.
    ts is timezone-aware UTC; the stream carries an ISO-8601 'Z' string."""
    ts: datetime
    tag_id: str
    value: float | None
    quality: str
    unit: str

    @classmethod
    def from_stream(cls, fields: dict) -> "TelemetryRow | None":
        """Parse one plant:telemetry entry. Returns None for an unparseable
        row rather than raising - one malformed sample must not stall the sink
        that is draining the whole stream."""
        tag_id = fields.get("tag_id")
        if not tag_id:
            return None
        ts = _parse_ts(fields.get("timestamp"))
        try:
            value = float(fields.get("value"))
        except (TypeError, ValueError):
            value = None
        return cls(ts=ts, tag_id=tag_id, value=value,
                   quality=fields.get("status", "GOOD"),
                   unit=fields.get("unit", ""))


def _end_read(conn) -> None:
    """Close the implicit transaction a SELECT opened.

    The connection is cached and autocommit is off (the sink needs a batch to
    commit atomically), so a read that never commits leaves the session `idle
    in transaction` holding ACCESS SHARE on the telemetry table - forever, for
    a long-lived reader. That is not theoretical: one leaked `window()` sat
    idle for three hours and blocked ensure_schema's ALTER TABLE, which
    blocked every historian restart's CREATE EXTENSION behind it, which meant
    the sink never consumed a single sample and every diagnosis downstream
    reported "no telemetry around onset".

    rollback, not commit: a read has nothing to persist, and rollback is the
    cheaper way to end the transaction.
    """
    try:
        conn.rollback()
    except Exception:                       # a dead connection is not a read error
        log.debug("could not end read transaction", exc_info=True)


def _parse_ts(raw) -> datetime:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class TimeseriesDB:
    def __init__(self, dsn: str, retention_days: int = 90):
        self._dsn = dsn
        self._retention_days = retention_days
        self._conn: psycopg.Connection | None = None
        self._has_timescale: bool | None = None

    @classmethod
    def from_settings(cls) -> "TimeseriesDB | None":
        """Return a configured client, or None when no DSN is set - the signal
        the historian is disabled, so the sink can idle instead of crash-loop."""
        s = get_settings()
        if not s.timescale_dsn:
            return None
        return cls(s.timescale_dsn, retention_days=s.historian_retention_days)

    # connection ------------------------------------------------------------
    def _connect(self):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is not installed; it ships in the historian image. "
                "Add 'psycopg[binary]' to run the historian outside it.")
        if self._conn is None or self._conn.closed:
            # autocommit off: the sink commits a whole batch atomically, so a
            # failed insert redelivers rather than half-lands.
            #
            # connect_timeout is not optional. Without it a stalled handshake
            # blocks forever - and because the sink connects BEFORE its first
            # log line, the whole historian died silently: pod Ready, log
            # empty, no consumer group, 50k telemetry entries unread, and
            # downstream every diagnosis reported "no telemetry around onset"
            # with nothing anywhere pointing at the database. A paused cloud
            # instance accepts TCP and then never completes startup, which is
            # exactly the shape that hangs here. Failing fast lets
            # _ensure_schema's retry loop log it and keep trying.
            kwargs = {"autocommit": False}
            if "connect_timeout" not in self._dsn:
                kwargs["connect_timeout"] = CONNECT_TIMEOUT_S
            self._conn = psycopg.connect(self._dsn, **kwargs)
            # a query that hangs must not wedge the sink either
            with self._conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            self._conn.commit()
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
        self._conn = None

    # schema ----------------------------------------------------------------
    def ensure_schema(self):
        """Idempotent. Creates the table, then upgrades it to a hypertable with
        compression and retention *if* timescaledb is present; otherwise leaves
        a plain indexed table that every Postgres can serve."""
        conn = self._connect()
        with conn.cursor() as cur:
            available = self._timescale_available(cur)
            if available:
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    ts       timestamptz      NOT NULL,
                    tag_id   text             NOT NULL,
                    value    double precision,
                    quality  text,
                    unit     text
                )
            """)
            # per-tag window scans ("reactor P for the 10 min before the trip")
            # are the whole point, so the index leads with tag_id then ts desc
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS ix_{TABLE}_tag_ts
                ON {TABLE} (tag_id, ts DESC)
            """)

            if available:
                self._apply_timescale(cur)
            conn.commit()

        self._has_timescale = available
        log.info("historian schema ready",
                 backend="timescaledb" if available else "postgres",
                 retention_days=self._retention_days if available else None)

    @staticmethod
    def _timescale_available(cur) -> bool:
        cur.execute(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
        return cur.fetchone() is not None

    def _apply_timescale(self, cur):
        # create_hypertable is a no-op once the table is already one, given
        # if_not_exists; migrate_data lets it adopt a table that already has
        # rows (e.g. a plain deployment later pointed at Timescale)
        cur.execute(
            f"SELECT create_hypertable('{TABLE}', 'ts', "
            "if_not_exists => TRUE, migrate_data => TRUE)")
        # compress anything older than a day - telemetry past the live window
        # is read in bulk, never updated, which is exactly what compression wants
        cur.execute(f"""
            ALTER TABLE {TABLE} SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'tag_id'
            )
        """)
        self._add_policy(cur,
            f"SELECT add_compression_policy('{TABLE}', INTERVAL '1 day')")
        self._add_policy(cur,
            f"SELECT add_retention_policy('{TABLE}', "
            f"INTERVAL '{self._retention_days} days')")

    @staticmethod
    def _add_policy(cur, sql: str):
        # policies are not IF NOT EXISTS-able across versions; a duplicate just
        # means it is already installed, which is success, not failure
        try:
            cur.execute(sql)
        except psycopg.errors.DatabaseError as e:
            cur.connection.rollback()
            log.info("timescale policy already present", detail=str(e)[:120])

    # writes ----------------------------------------------------------------
    def insert_batch(self, rows: list[TelemetryRow]) -> int:
        """COPY a batch in one round trip. Returns the count written. Raises on
        failure so the caller can leave the batch unacked and retry it."""
        if not rows:
            return 0
        conn = self._connect()
        try:
            with conn.cursor() as cur, cur.copy(
                f"COPY {TABLE} (ts, tag_id, value, quality, unit) "
                "FROM STDIN"
            ) as copy:
                for r in rows:
                    copy.write_row((r.ts, r.tag_id, r.value, r.quality, r.unit))
            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise

    # reads -----------------------------------------------------------------
    def window(self, tag_ids: list[str], start: datetime, end: datetime,
               limit: int = 100_000) -> list[TelemetryRow]:
        """Raw samples for the given tags in [start, end], oldest first - the
        shape signature extraction and trend charts both want."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT ts, tag_id, value, quality, unit FROM {TABLE}
                WHERE tag_id = ANY(%s) AND ts >= %s AND ts <= %s
                ORDER BY ts ASC
                LIMIT %s
            """, (tag_ids, start, end, limit))
            rows = [TelemetryRow(*row) for row in cur.fetchall()]
        _end_read(conn)
        return rows

    def latest(self, tag_ids: list[str]) -> dict[str, TelemetryRow]:
        """Most recent sample per tag - a cheap 'current value' read."""
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT ON (tag_id) ts, tag_id, value, quality, unit
                FROM {TABLE}
                WHERE tag_id = ANY(%s)
                ORDER BY tag_id, ts DESC
            """, (tag_ids,))
            rows = {row[1]: TelemetryRow(*row) for row in cur.fetchall()}
        _end_read(conn)
        return rows

    def distinct_tags(self, since_minutes: int = 1440) -> list[str]:
        """Every tag the historian has seen in the last `since_minutes`. Lets a
        consumer discover the plant's tag universe from what was actually
        recorded, instead of importing a topology it would rather not depend on."""
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT tag_id FROM {TABLE} WHERE ts >= %s", (since,))
            tags = [r[0] for r in cur.fetchall()]
        _end_read(conn)
        return tags

    def ping(self) -> bool:
        try:
            with self._connect().cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception as e:
            log.warning("historian ping failed", error=str(e))
            return False
