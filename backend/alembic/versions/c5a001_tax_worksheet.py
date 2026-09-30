"""Phase 5A: ITC decisions, adjustments, draft worksheets, approvals, reopening, filing evidence, audit scope."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c5a001'
down_revision='c4b001'
branch_labels=None
depends_on=None

def _id(): return sa.Column('id',UUID(as_uuid=True),primary_key=True)
def _fk(name,target,**kw): return sa.Column(name,UUID(as_uuid=True),sa.ForeignKey(target),nullable=False,**kw)
def _created(): return sa.Column('created_at',sa.DateTime(timezone=True),nullable=False)

def upgrade():
    op.add_column('audit_events',sa.Column('period_id',UUID(as_uuid=True),sa.ForeignKey('filing_periods.id'),nullable=True))
    op.add_column('audit_events',sa.Column('summary',sa.Text(),nullable=True))
    op.create_index('ix_audit_events_period_id','audit_events',['period_id'])
    op.create_table('itc_decisions',_id(),_fk('run_id','reconciliation_runs.id'),sa.Column('result_id',sa.String(),nullable=False),
        _fk('user_id','users.id'),sa.Column('decision',sa.String(),nullable=False),sa.Column('note',sa.Text(),nullable=False),_created())
    op.create_index('ix_itc_decisions_run_id','itc_decisions',['run_id'])
    op.create_table('tax_adjustments',_id(),_fk('period_id','filing_periods.id'),_fk('user_id','users.id'),
        sa.Column('adjustment_type',sa.String(),nullable=False),sa.Column('tax_head',sa.String(),nullable=False),
        sa.Column('amount',sa.Numeric(14,2),nullable=False),sa.Column('note',sa.Text(),nullable=False),_created())
    op.create_index('ix_tax_adjustments_period_id','tax_adjustments',['period_id'])
    op.create_table('tax_adjustment_voids',_id(),_fk('adjustment_id','tax_adjustments.id',unique=True),_fk('user_id','users.id'),
        sa.Column('reason',sa.Text(),nullable=False),_created())
    op.create_table('tax_drafts',_id(),_fk('period_id','filing_periods.id'),_fk('sales_batch_id','sales_batches.id'),
        _fk('run_id','reconciliation_runs.id'),_fk('user_id','users.id'),sa.Column('engine_version',sa.String(),nullable=False),
        sa.Column('fingerprint',sa.String(),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('blockers',sa.JSON(),nullable=False),_created())
    op.create_index('ix_tax_drafts_period_id','tax_drafts',['period_id'])
    op.create_table('tax_approvals',_id(),_fk('draft_id','tax_drafts.id',unique=True),_fk('period_id','filing_periods.id'),
        _fk('user_id','users.id'),sa.Column('note',sa.Text(),nullable=False),_created())
    op.create_index('ix_tax_approvals_period_id','tax_approvals',['period_id'])
    op.create_table('tax_reopens',_id(),_fk('approval_id','tax_approvals.id',unique=True),_fk('user_id','users.id'),
        sa.Column('reason',sa.Text(),nullable=False),_created())
    op.create_table('filing_evidence',_id(),_fk('approval_id','tax_approvals.id'),_fk('user_id','users.id'),
        sa.Column('arn',sa.String(),nullable=False),sa.Column('filed_on',sa.String(),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),_created())
    op.create_index('ix_filing_evidence_approval_id','filing_evidence',['approval_id'])

def downgrade():
    for t in ('filing_evidence','tax_reopens','tax_approvals','tax_drafts','tax_adjustment_voids','tax_adjustments','itc_decisions'):
        op.drop_table(t)
    op.drop_index('ix_audit_events_period_id','audit_events')
    op.drop_column('audit_events','summary')
    op.drop_column('audit_events','period_id')
