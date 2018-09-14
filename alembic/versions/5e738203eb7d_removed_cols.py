"""removed cols

Revision ID: 5e738203eb7d
Revises: b3d846872bb6
Create Date: 2018-09-07 16:37:56.533796

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_json import MutableJson


# revision identifiers, used by Alembic.
revision = '5e738203eb7d'
down_revision = 'b3d846872bb6'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('reminders', 'guild')
    op.drop_column('servers', 'tags')


def downgrade():
    op.add_column('reminders', sa.Column('guild', sa.BigInteger))
    op.add_column('servers', sa.Column('tags', MutableJson))
