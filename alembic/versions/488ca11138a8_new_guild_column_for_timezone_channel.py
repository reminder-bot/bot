"""new guild column for timezone channel

Revision ID: 488ca11138a8
Revises:
Create Date: 2018-08-15 04:54:13.189593

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '488ca11138a8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('servers', sa.Column('tz_channel', sa.BigInteger))


def downgrade():
    op.drop_column('servers', 'tz_channel')
