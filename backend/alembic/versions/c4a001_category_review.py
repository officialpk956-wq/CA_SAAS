"""Add independent category review records; financial inputs remain unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c4a001'
down_revision='c3b001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('category_proposals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('record_id', UUID(as_uuid=True), sa.ForeignKey('import_records.id'), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False), sa.Column('source',sa.String(),nullable=False),
        sa.Column('model_version',sa.String(),nullable=False), sa.Column('category',sa.String()),
        sa.Column('evidence',sa.Text()), sa.Column('status',sa.String(),nullable=False), sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('category_decisions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),sa.Column('record_id',UUID(as_uuid=True),sa.ForeignKey('import_records.id'),nullable=False),
        sa.Column('proposal_id',UUID(as_uuid=True),sa.ForeignKey('category_proposals.id')),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('category',sa.String()),sa.Column('action',sa.String(),nullable=False),sa.Column('note',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('category_rules',sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('client_id',UUID(as_uuid=True),sa.ForeignKey('clients.id'),nullable=False),
        sa.Column('supplier_ref',sa.String(),nullable=False),sa.Column('description',sa.Text(),nullable=False),
        sa.Column('category',sa.String(),nullable=False),sa.Column('effective_from',sa.String(),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False),sa.Column('approved_by',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    op.drop_table('category_rules')
    op.drop_table('category_decisions')
    op.drop_table('category_proposals')
