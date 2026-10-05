"""Client upload links (hashed token, expiry, use limit, revocable) and client contact details for reminders."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = 'd3a001'
down_revision = 'd2a001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('clients', sa.Column('contact_email', sa.String(), nullable=True))
    op.add_column('clients', sa.Column('contact_phone', sa.String(), nullable=True))
    op.create_table('upload_links',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('period_id', UUID(as_uuid=True), sa.ForeignKey('filing_periods.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_upload_links_period_id', 'upload_links', ['period_id'])

def downgrade():
    op.drop_table('upload_links')
    op.drop_column('clients', 'contact_phone')
    op.drop_column('clients', 'contact_email')
