import tempfile
import subprocess
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "sample_data" / "v1"
CLI_PATH = PROJECT_ROOT / "backend" / "gst_copilot" / "cli.py"

def run_cli(*args):
    # Running as `python -m backend.gst_copilot.cli`
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    cmd = ["python", "-m", "backend.gst_copilot.cli"] + list(args)
    return subprocess.run(cmd, env=env, capture_output=True, text=True)

def test_cli_success():
    with tempfile.TemporaryDirectory() as outdir:
        res = run_cli(
            "--purchases", str(DATA_DIR / "purchase_register.csv"),
            "--statements", str(DATA_DIR / "gstr2b_demo.csv"),
            "--suppliers", str(DATA_DIR / "suppliers.csv"),
            "--outdir", outdir
        )
        assert res.returncode == 0
        assert (Path(outdir) / "reconciliation_results.json").exists()
        assert (Path(outdir) / "reconciliation_summary.json").exists()

def test_cli_overwrite_protection():
    with tempfile.TemporaryDirectory() as outdir:
        # First run succeeds
        res = run_cli(
            "--purchases", str(DATA_DIR / "purchase_register.csv"),
            "--statements", str(DATA_DIR / "gstr2b_demo.csv"),
            "--suppliers", str(DATA_DIR / "suppliers.csv"),
            "--outdir", outdir
        )
        assert res.returncode == 0
        
        # Second run without --overwrite fails
        res2 = run_cli(
            "--purchases", str(DATA_DIR / "purchase_register.csv"),
            "--statements", str(DATA_DIR / "gstr2b_demo.csv"),
            "--suppliers", str(DATA_DIR / "suppliers.csv"),
            "--outdir", outdir
        )
        assert res2.returncode == 1
        assert "Use --overwrite to replace them" in res2.stderr
        
        # Third run with --overwrite succeeds
        res3 = run_cli(
            "--purchases", str(DATA_DIR / "purchase_register.csv"),
            "--statements", str(DATA_DIR / "gstr2b_demo.csv"),
            "--suppliers", str(DATA_DIR / "suppliers.csv"),
            "--outdir", outdir,
            "--overwrite"
        )
        assert res3.returncode == 0

def test_cli_missing_input():
    with tempfile.TemporaryDirectory() as outdir:
        res = run_cli(
            "--purchases", "does_not_exist.csv",
            "--statements", str(DATA_DIR / "gstr2b_demo.csv"),
            "--suppliers", str(DATA_DIR / "suppliers.csv"),
            "--outdir", outdir
        )
        assert res.returncode == 1
        assert "Parsing error: File not found" in res.stderr
