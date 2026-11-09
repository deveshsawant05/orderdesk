"""Remember customer contact without treating it as verified identity."""
from alembic import op
import sqlalchemy as sa
revision='20261107_contact'
down_revision='20261104_map_pins'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('users',sa.Column('contact_phone',sa.String(10)))
def downgrade():
    op.drop_column('users','contact_phone')
