"""webhook storage column

Revision ID: bef608bad0d2
Revises: 488ca11138a8
Create Date: 2018-09-02 18:00:55.974355

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bef608bad0d2'
down_revision = '488ca11138a8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reminders', sa.Column('webhook', sa.String(120)))
    op.drop_column('servers', 'tz_channel')


def downgrade():
    op.drop_column('servers', 'webhook')
    op.add_column('servers', sa.Column('tz_channel', sa.BigInteger))
