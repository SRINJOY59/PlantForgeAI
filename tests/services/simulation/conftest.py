import sys
from pathlib import Path

# the simulation package lives under services/, like the other service packages
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))
