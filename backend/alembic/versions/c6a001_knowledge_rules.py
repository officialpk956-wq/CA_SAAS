"""Knowledge rules: human-confirmed client quirks, and the adjustments they generate."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c6a001'
down_revision='c5a001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('knowledge_rules',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('client_id',UUID(as_uuid=True),sa.ForeignKey('clients.id'),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),
        sa.Column('adjustment_type',sa.String()),sa.Column('tax_head',sa.String()),
        sa.Column('amount',sa.Numeric(14,2)),sa.Column('effective_from',sa.String()),
        sa.Column('status',sa.String(),nullable=False),
        sa.Column('created_by',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('decided_by',UUID(as_uuid=True),sa.ForeignKey('users.id')),
        sa.Column('decided_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_knowledge_rules_client_id','knowledge_rules',['client_id'])
    op.add_column('tax_adjustments',sa.Column('rule_id',UUID(as_uuid=True),sa.ForeignKey('knowledge_rules.id'),nullable=True))

def downgrade():
    op.drop_column('tax_adjustments','rule_id')
    op.drop_table('knowledge_rules')
