-- Canonical historian schema. This is what plantmind_core.timeseries.client
-- applies at startup (ensure_schema); it is kept here in readable form too, so
-- the shape of the historian can be reviewed without reading Python, and so it
-- can be applied by hand to a managed DB that restricts DDL from the app role.
--
-- The timescaledb block is optional. On Timescale Cloud it runs and the table
-- becomes a compressed, retained hypertable. On Supabase / stock Postgres the
-- extension is absent, the block is skipped, and the plain indexed table below
-- serves every read and write unchanged.

CREATE TABLE IF NOT EXISTS plant_telemetry (
    ts       timestamptz      NOT NULL,
    tag_id   text             NOT NULL,
    value    double precision,
    quality  text,
    unit     text
);

-- Per-tag window scans are the dominant read (one tag over a time range), so
-- the index leads with tag_id and orders ts descending for "latest N".
CREATE INDEX IF NOT EXISTS ix_plant_telemetry_tag_ts
    ON plant_telemetry (tag_id, ts DESC);

-- ---------------------------------------------------------------------------
-- TimescaleDB features (skipped automatically where the extension is absent)
-- ---------------------------------------------------------------------------
-- CREATE EXTENSION IF NOT EXISTS timescaledb;
-- SELECT create_hypertable('plant_telemetry', 'ts',
--                          if_not_exists => TRUE, migrate_data => TRUE);
--
-- ALTER TABLE plant_telemetry SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'tag_id'
-- );
-- SELECT add_compression_policy('plant_telemetry', INTERVAL '1 day');
-- SELECT add_retention_policy('plant_telemetry', INTERVAL '90 days');
