"""Retired (2026-10-05). This early script seeded an unused "Test Org" into the development database and failed
when run twice. Use the maintained, idempotent seed instead:

    python backend/gst_copilot/cli/seed.py           # demo firm and admin user
    python scripts/seed_demo_data.py --api http://127.0.0.1:8000   # synthetic 8-client demo roster (API must be running)
"""
raise SystemExit(__doc__)
