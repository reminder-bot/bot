"""new columns for data

Revision ID: c8ce8dc8651d
Revises: bef608bad0d2
Create Date: 2018-09-02 21:38:44.093366

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8ce8dc8651d'
down_revision = 'bef608bad0d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reminders', sa.Column('avatar', sa.Text))


def downgrade():
    op.drop_column('reminders', 'avatar')
