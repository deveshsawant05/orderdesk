"""Index existing order contacts for cross-session mobile history."""
from alembic import op
revision='20261109_mobile_history'
down_revision='20261107_contact'
branch_labels=None
depends_on=None

def upgrade():
    op.create_index('ix_orders_contact_placed','orders',['contact_phone','placed_at'])

def downgrade():
    op.drop_index('ix_orders_contact_placed',table_name='orders')
