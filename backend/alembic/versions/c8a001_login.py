"""Login: password hash and active flag on users; server-side sessions (token hashes only)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='c8a001'
down_revision='c7a001'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('users',sa.Column('password_hash',sa.String(),nullable=True))
    op.add_column('users',sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table('user_sessions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('token_hash',sa.String(),nullable=False,unique=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('revoked_at',sa.DateTime(timezone=True)))
    op.create_index('ix_user_sessions_user_id','user_sessions',['user_id'])

def downgrade():
    op.drop_table('user_sessions')
    op.drop_column('users','is_active')
    op.drop_column('users','password_hash')
