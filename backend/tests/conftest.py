import os
import sys
import tempfile
from pathlib import Path

# Ensure `app` package is importable when running pytest from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Keep tests hermetic: point the app at a throwaway SQLite database instead of
# the developer's local `researchlens.db`. Set before any `app.*` import so the
# cached Settings singleton picks it up.
_test_db_dir = tempfile.mkdtemp(prefix="researchle_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_test_db_dir) / 'test.db'}"