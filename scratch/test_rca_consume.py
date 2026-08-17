import redis
import json

r = redis.from_url("redis://redis:6379/0")

print("Reading from alerts stream starting from 0-0...")
try:
    entries = r.xread({"alerts": "0-0"}, count=100)
    if not entries:
        print("No entries found!")
    else:
        for stream, messages in entries:
            print(f"Found {len(messages)} messages in stream {stream.decode()}")
            for entry_id, fields in messages[:5]:
                payload_str = fields.get(b"payload", b"").decode()
                if payload_str:
                    payload = json.loads(payload_str)
                    print(f"  - Entry {entry_id.decode()}: kind={payload.get('kind')}, type={payload.get('type')}, fingerprint={payload.get('fingerprint')}")
except Exception as e:
    print("Error:", e)
