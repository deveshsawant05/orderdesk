"""Keep party ownership and a separate catering fulfilment lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = '20261110_party_scope'
down_revision = '20261109_mobile_history'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('party_requests', sa.Column('user_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_party_user', 'party_requests', 'users', ['user_id'], ['id'])
    op.create_index('ix_party_requests_user_id', 'party_requests', ['user_id'])
    op.create_index('ix_party_phone_created', 'party_requests', ['phone', 'created_at'])
    for constraint in sa.inspect(op.get_bind()).get_check_constraints('party_requests'):
        if 'status' in constraint['sqltext']:
            op.drop_constraint(constraint['name'], 'party_requests', type_='check')
    op.create_check_constraint('ck_party_status', 'party_requests', "status IN ('pending','accepted','rejected','preparing','ready','fulfilled')")


def downgrade():
    # Do not silently erase fulfilment state to fit the old constraint.
    active = op.get_bind().scalar(sa.text("SELECT count(*) FROM party_requests WHERE status IN ('preparing','ready','fulfilled')"))
    if active:
        raise RuntimeError('Party fulfilment records must be resolved before downgrading.')
    op.drop_constraint('ck_party_status', 'party_requests', type_='check')
    op.create_check_constraint('party_requests_status_check', 'party_requests', "status IN ('pending','accepted','rejected')")
    op.drop_index('ix_party_phone_created', table_name='party_requests')
    op.drop_index('ix_party_requests_user_id', table_name='party_requests')
    op.drop_constraint('fk_party_user', 'party_requests', type_='foreignkey')
    op.drop_column('party_requests', 'user_id')
