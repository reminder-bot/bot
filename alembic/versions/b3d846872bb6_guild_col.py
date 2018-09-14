"""guild col

Revision ID: b3d846872bb6
Revises: c8ce8dc8651d
Create Date: 2018-09-03 09:47:30.261765

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3d846872bb6'
down_revision = 'c8ce8dc8651d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reminders', sa.Column('guild', sa.BigInteger))


def downgrade():
    op.drop_column('reminders', 'guild')
