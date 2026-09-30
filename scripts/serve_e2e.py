"""Local browser-test API. Uses only the dedicated E2E database; never resets it."""
import os
from pathlib import Path
import runpy
import subprocess
import sys
root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_e2e_test"
os.environ["STORAGE_DIR"] = str(root / "storage" / "e2e")
# Test-only login for the dedicated E2E database (never the dev database). Keep in sync with frontend/e2e/auth.ts.
os.environ["SEED_ADMIN_PASSWORD"] = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-synthetic-login-only")
if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, str(root / "backend/gst_copilot/cli/seed.py")], check=True)
    import uvicorn
    uvicorn.run("backend.gst_copilot.api.main:app", host="127.0.0.1", port=8002)
