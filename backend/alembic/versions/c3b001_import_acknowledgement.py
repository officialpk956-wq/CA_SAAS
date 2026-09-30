"""Persist explicit import acknowledgement notes."""
from alembic import op
import sqlalchemy as sa
revision = 'c3b001'
down_revision = '595c6a7763db'
branch_labels = None
depends_on = None
def upgrade():
    op.add_column('import_batches', sa.Column('commit_note', sa.Text(), nullable=True))
def downgrade():
    op.drop_column('import_batches', 'commit_note')
