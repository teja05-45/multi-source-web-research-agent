import sys
from pathlib import Path

# Ensure `app` package is importable when running pytest from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
