"""OSIsoft PI Historian via the PI Web API.

PI is time-series; the graph is documents and relations. Rather than force
raw samples into the pipeline, this emits a trend SUMMARY per tag as
markdown - the shape the text lane already understands. The equipment tag
in the heading is picked up by the regex mention pass, so a temperature
creep on K-301 becomes a fact attached to K-301, next to its work orders
and incidents.

connectors.json:
  {"type": "pi", "id": "pi-historian",
   "base_url": "https://pi.example.com/piwebapi",
   "tags": ["\\\\PISRV\\\\K-301.TI302", "\\\\PISRV\\\\C-220.PDI221"],
   "username_env": "PI_USER", "password_env": "PI_PASSWORD",
   "days": 7, "interval": "1h"}
"""

import os
from datetime import datetime, timezone

import httpx

from plantmind_core.telemetry import get_logger

from connectors.base import Connector, SyncItem

log = get_logger("connectors.pi")


class PiHistorianConnector(Connector):
    def __init__(self, id: str, base_url: str, tags: list,
                 username_env="PI_USER", password_env="PI_PASSWORD",
                 days=7, interval="1h", client=None):
        super().__init__(id)
        self._base = base_url.rstrip("/")
        self._tags = tags
        self._days = days
        self._interval = interval
        self._auth = (os.getenv(username_env, ""), os.getenv(password_env, ""))
        self._client = client

    def fetch(self, since: str):
        client = self._client or httpx.Client(auth=self._auth, timeout=60)
        try:
            for path in self._tags:
                try:
                    samples = self._samples(client, path)
                except Exception as e:
                    log.warning("pi tag failed", tag=path, error=str(e)[:160])
                    continue
                if not samples:
                    continue
                marker = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                name = _tag_name(path)
                yield SyncItem(
                    filename=f"pi_trend_{name}_{marker}.md",
                    data=_summary_md(path, name, samples, self._days,
                                     self._interval).encode("utf-8"),
                    marker=marker)
        finally:
            if self._client is None:
                client.close()

    def _samples(self, client, path: str) -> list:
        point = client.get(f"{self._base}/points", params={"path": path})
        point.raise_for_status()
        web_id = _web_id(point.json())
        if not web_id:
            return []

        resp = client.get(
            f"{self._base}/streams/{web_id}/interpolated",
            params={"startTime": f"*-{self._days}d", "endTime": "*",
                    "interval": self._interval})
        resp.raise_for_status()
        out = []
        for item in resp.json().get("Items", []):
            value = item.get("Value")
            # bad/digital values come back as an object, not a number
            if isinstance(value, dict) or value is None:
                continue
            if item.get("Good") is False:
                continue
            try:
                out.append((item.get("Timestamp", ""), float(value)))
            except (TypeError, ValueError):
                continue
        return out


def _web_id(payload: dict):
    if payload.get("WebId"):
        return payload["WebId"]
    items = payload.get("Items") or []
    return items[0].get("WebId") if items else None


def _tag_name(path: str) -> str:
    return path.replace("\\", " ").strip().split(" ")[-1]


def _summary_md(path, name, samples, days, interval) -> str:
    values = [v for _, v in samples]
    first, last = values[0], values[-1]
    delta = last - first
    direction = ("rising" if delta > 0 else "falling" if delta < 0
                 else "flat")
    rows = "\n".join(f"| {ts} | {v:.2f} |" for ts, v in samples[-24:])

    return f"""# PI trend: {name}

**Source:** OSIsoft PI Historian, tag `{path}`
**Window:** last {days} days at {interval} interval
**Samples:** {len(samples)}

## Summary

{name} is {direction} over the last {days} days: {first:.2f} to {last:.2f}
(change {delta:+.2f}). Minimum {min(values):.2f}, maximum {max(values):.2f},
average {sum(values)/len(values):.2f}. Latest reading {last:.2f} at
{samples[-1][0]}.

## Recent readings

| timestamp | value |
|-----------|-------|
{rows}
"""
