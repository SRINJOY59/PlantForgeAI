from __future__ import annotations
import os
import math
import random
from datetime import datetime, timezone
import redis

class BaseTelemetryPublisher:
    """Base class for telemetry streaming publishers.
    
    Handles Redis connection and pipeline batching for tag payloads.
    """
    def __init__(self, r: redis.Redis | None = None):
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._r = r or redis.from_url(url, decode_responses=True)

    def publish_tags(self, tags: dict[str, tuple[float, str]], timestamp: str | None = None) -> None:
        """Publish a dictionary of {tag_id -> (value, unit)} to the telemetry stream.
        
        Applies non-finite check to set status='BAD' and applies a random 
        uncertain status check (0.5% probability) for testing.
        """
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pipe = self._r.pipeline(transaction=False)
        for tag_id, (val, unit) in tags.items():
            try:
                val_float = float(val)
                is_ok = math.isfinite(val_float)
            except (ValueError, TypeError):
                is_ok = False
            
            if not is_ok:
                status = "BAD"
                val_str = "0.0"
            else:
                status = "UNCERTAIN" if random.random() < 0.005 else "GOOD"
                val_str = str(round(val_float, 4))
                
            payload = {
                "tag_id": tag_id,
                "timestamp": ts,
                "value": val_str,
                "unit": unit,
                "status": status,
            }
            pipe.xadd("plant:telemetry", payload, maxlen=50_000, approximate=True)
        pipe.execute()
