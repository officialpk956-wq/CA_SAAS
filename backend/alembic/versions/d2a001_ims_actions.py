"""IMS actions: append-only accept / reject / pending per supplier invoice in a committed statement."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = 'd2a001'
down_revision = 'd1a001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('ims_actions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('record_id', UUID(as_uuid=True), sa.ForeignKey('import_records.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_ims_actions_record_id', 'ims_actions', ['record_id'])

def downgrade():
    op.drop_table('ims_actions')
