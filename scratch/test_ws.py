import asyncio
import websockets
import json

async def test():
    print("Attempting to connect to ws://localhost:8000/ws/plant-telemetry...")
    try:
        async with websockets.connect("ws://localhost:8000/ws/plant-telemetry") as ws:
            print("Connected successfully!")
            for i in range(10):
                msg = await ws.recv()
                data = json.loads(msg)
                print(f"[{i}] Received: type={data.get('type')}, tag_id={data.get('tag_id')}, val={data.get('value')}")
    except Exception as e:
        print("WebSocket client error:", e)

if __name__ == "__main__":
    asyncio.run(test())
