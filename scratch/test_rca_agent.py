import sys
import asyncio
from pathlib import Path

# Bootstrap sys.path
_repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo / "libs" / "core"))
sys.path.insert(0, str(_repo / "services" / "agents"))

from plantmind_core.bus import RedisBus
from agents.reader import AgentReader
from agents.usecases.failure_rca import InvestigatorAgent
from agents.watchers import Trigger

async def main():
    reader = AgentReader.from_settings()
    investigator = InvestigatorAgent(reader)
    
    print("Testing hardcoded trigger CSTR-102A / RATE_OF_RISE...")
    trigger = Trigger(
        tag="CSTR-102A",
        mode="RATE_OF_RISE",
        count=1,
        family="CSTR-102",
        siblings=[{"tag": "CSTR-102B"}],
        graph_version=0
    )
    
    try:
        alert_obj, reasoned = await investigator.investigate_reasoned(trigger)
        print("Investigation succeeded!")
        print("Title:", alert_obj.title)
        print("Citations:", [c.doc_id for c in alert_obj.citations])
        print("Body preview:", alert_obj.body[:400])
    except Exception as e:
        print("Investigation failed with exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
