"""Close Supabase's automatic Data API over our tables.

Supabase publishes every table in `public` through PostgREST to its `anon` and `authenticated` roles. This app
never uses that API (all access goes through FastAPI as the table owner), so: enable row-level security with no
policies on every table (denies those roles; the owner is unaffected) and revoke their privileges, including on
tables later migrations create. On a plain PostgreSQL without those roles only the RLS step runs.
"""
from alembic import op

revision = 'c9a001'
down_revision = 'c8a001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
  END IF;
END $$;
""")


def downgrade():
    # Privileges revoked from Supabase's API roles are deliberately not re-granted.
    op.execute("""
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
""")
