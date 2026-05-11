import sys
from pathlib import Path

# Tests for arrival_simulator_service need its source on sys.path so
# `from core.* import ...` works the same way it does inside the container.
_SVC = Path(__file__).resolve().parents[2] / "services" / "arrival_simulator_service"
if str(_SVC) not in sys.path:
    sys.path.insert(0, str(_SVC))
