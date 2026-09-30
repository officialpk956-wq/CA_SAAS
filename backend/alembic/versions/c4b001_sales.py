"""Independent synthetic sales preparation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c4b001'
down_revision='c4a001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('sales_batches',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('period_id',UUID(as_uuid=True),sa.ForeignKey('filing_periods.id'),nullable=False),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('filename',sa.String(),nullable=False),sa.Column('file_hash',sa.String(),nullable=False),
        sa.Column('original_csv',sa.Text(),nullable=False),sa.Column('contract_version',sa.String(),nullable=False),
        sa.Column('status',sa.String(),nullable=False),sa.Column('commit_note',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('period_id','file_hash',name='uq_sales_period_hash'))
    op.create_table('sales_records',sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('batch_id',UUID(as_uuid=True),sa.ForeignKey('sales_batches.id'),nullable=False),
        sa.Column('row_number',sa.Integer(),nullable=False),sa.Column('raw_data',sa.JSON(),nullable=False),
        sa.Column('validation_status',sa.String(),nullable=False),sa.Column('issues',sa.JSON(),nullable=False),
        sa.UniqueConstraint('batch_id','row_number',name='uq_sales_batch_row'))
    op.create_index('ix_sales_records_batch_id','sales_records',['batch_id'])
    op.create_table('sales_reviews',sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('record_id',UUID(as_uuid=True),sa.ForeignKey('sales_records.id'),nullable=False),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('decision',sa.String(),nullable=False),sa.Column('note',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_sales_reviews_record_id','sales_reviews',['record_id'])

def downgrade():
    op.drop_table('sales_reviews');op.drop_table('sales_records');op.drop_table('sales_batches')
