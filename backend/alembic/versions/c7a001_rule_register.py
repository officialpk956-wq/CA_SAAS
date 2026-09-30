"""Legal rule register (CA-confirmed), knowledge-rule frequency/kind/firm-wide scope, reminder acknowledgements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c7a001'
down_revision='c6a001'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('knowledge_rules',sa.Column('organization_id',UUID(as_uuid=True),sa.ForeignKey('organizations.id'),nullable=True))
    op.execute('UPDATE knowledge_rules k SET organization_id = c.organization_id FROM clients c WHERE k.client_id = c.id')
    op.alter_column('knowledge_rules','organization_id',nullable=False)
    op.create_index('ix_knowledge_rules_organization_id','knowledge_rules',['organization_id'])
    op.alter_column('knowledge_rules','client_id',nullable=True)
    op.add_column('knowledge_rules',sa.Column('rule_kind',sa.String(),nullable=False,server_default='adjustment'))
    op.add_column('knowledge_rules',sa.Column('frequency',sa.String(),nullable=False,server_default='monthly'))
    op.add_column('knowledge_rules',sa.Column('effective_to',sa.String(),nullable=True))
    op.create_table('rule_acknowledgements',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('rule_id',UUID(as_uuid=True),sa.ForeignKey('knowledge_rules.id'),nullable=False),
        sa.Column('period_id',UUID(as_uuid=True),sa.ForeignKey('filing_periods.id'),nullable=False),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('rule_id','period_id',name='uq_rule_ack_period'))
    op.create_index('ix_rule_acknowledgements_period_id','rule_acknowledgements',['period_id'])
    op.create_table('legal_rules',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('organization_id',UUID(as_uuid=True),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('key',sa.String(),nullable=False),
        sa.Column('value',sa.JSON(),nullable=False),
        sa.Column('source_reference',sa.Text(),nullable=False),
        sa.Column('effective_from',sa.String(),nullable=False),
        sa.Column('status',sa.String(),nullable=False),
        sa.Column('confirmed_by',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('confirmed_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_legal_rules_organization_id','legal_rules',['organization_id'])

def downgrade():
    op.drop_table('legal_rules')
    op.drop_table('rule_acknowledgements')
    op.drop_column('knowledge_rules','effective_to')
    op.drop_column('knowledge_rules','frequency')
    op.drop_column('knowledge_rules','rule_kind')
    op.execute('DELETE FROM knowledge_rules WHERE client_id IS NULL')
    op.alter_column('knowledge_rules','client_id',nullable=False)
    op.drop_index('ix_knowledge_rules_organization_id','knowledge_rules')
    op.drop_column('knowledge_rules','organization_id')
