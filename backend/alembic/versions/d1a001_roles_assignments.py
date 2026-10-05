"""Firm roles (owner / reviewer / preparer), optional separate-approver policy, period assignee."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = 'd1a001'
down_revision = 'c9a001'
branch_labels = None
depends_on = None

def upgrade():
    # Existing users keep full rights: they become owners.
    op.add_column('users', sa.Column('role', sa.String(), nullable=False, server_default='owner'))
    op.add_column('users', sa.Column('display_name', sa.String(), nullable=True))
    op.add_column('organizations', sa.Column('require_separate_approver', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('filing_periods', sa.Column('assignee_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_filing_periods_assignee_id', 'filing_periods', ['assignee_id'])

def downgrade():
    op.drop_index('ix_filing_periods_assignee_id', 'filing_periods')
    op.drop_column('filing_periods', 'assignee_id')
    op.drop_column('organizations', 'require_separate_approver')
    op.drop_column('users', 'display_name')
    op.drop_column('users', 'role')
