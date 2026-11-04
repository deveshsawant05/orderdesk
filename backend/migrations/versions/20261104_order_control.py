"""Preserve historical references and add scoped order control."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_control'
down_revision = '19ab5ca8b510'
branch_labels = None
depends_on = None

ORDER_CHILDREN = ('estimates', 'events', 'notifications', 'order_items', 'overrides')


def remap_order_keys(source):
    for table in ORDER_CHILDREN:
        op.drop_constraint(f'{table}_order_id_fkey', table, type_='foreignkey')
        op.execute(f'UPDATE {table} child SET order_id = orders.{source} FROM orders WHERE child.order_id = orders.id')
    op.execute(f'UPDATE orders SET id = {source}')
    for table in ORDER_CHILDREN:
        op.create_foreign_key(f'{table}_order_id_fkey', table, 'orders', ['order_id'], ['id'])


def upgrade():
    op.execute('ALTER TABLE users DROP CONSTRAINT users_role_check')
    op.execute("UPDATE users SET role = 'manager' WHERE role = 'admin'")
    op.execute("UPDATE users SET can_manage = FALSE WHERE role = 'kitchen'")
    op.create_check_constraint('users_role_check', 'users', "role IN ('customer','manager','kitchen')")
    op.add_column('orders', sa.Column('public_ref', sa.String(40)))
    op.add_column('orders', sa.Column('tracking_token', sa.String(64)))
    op.add_column('orders', sa.Column('service_date', sa.Date()))
    op.add_column('orders', sa.Column('daily_number', sa.Integer()))
    op.add_column('orders', sa.Column('destination_lat', sa.Float()))
    op.add_column('orders', sa.Column('destination_lng', sa.Float()))
    op.add_column('orders', sa.Column('contact_name', sa.String(80)))
    op.add_column('orders', sa.Column('contact_phone', sa.String(10)))
    op.add_column('orders', sa.Column('resolution_reason', sa.String(300)))
    op.add_column('orders', sa.Column('refunded_at', sa.DateTime(timezone=True)))
    op.execute("""UPDATE orders SET public_ref = id,
        tracking_token = replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
        service_date = (placed_at AT TIME ZONE 'Asia/Kolkata')::date""")
    op.add_column('orders', sa.Column('uuid_tmp', sa.String(40)))
    op.execute('UPDATE orders SET uuid_tmp = gen_random_uuid()::text')
    remap_order_keys('uuid_tmp')
    op.drop_column('orders', 'uuid_tmp')
    op.execute("""UPDATE orders SET daily_number = numbered.n FROM (
        SELECT id, row_number() OVER (PARTITION BY outlet_id, service_date ORDER BY placed_at, id) AS n FROM orders
        ) numbered WHERE orders.id = numbered.id""")
    for field in ('public_ref', 'tracking_token', 'service_date', 'daily_number'):
        op.alter_column('orders', field, nullable=False)
    op.create_unique_constraint('uq_order_public_ref', 'orders', ['public_ref'])
    op.create_unique_constraint('uq_order_tracking_token', 'orders', ['tracking_token'])
    op.create_unique_constraint('uq_outlet_service_number', 'orders', ['outlet_id', 'service_date', 'daily_number'])
    op.create_table(
        'daily_counters',
        sa.Column('outlet_id', sa.String(50), sa.ForeignKey('outlets.id'), primary_key=True),
        sa.Column('service_date', sa.Date(), primary_key=True),
        sa.Column('last_number', sa.Integer(), nullable=False),
    )
    op.execute("""INSERT INTO daily_counters
        SELECT outlet_id, service_date, max(daily_number) FROM orders GROUP BY outlet_id, service_date""")


def downgrade():
    remap_order_keys('public_ref')
    op.drop_table('daily_counters')
    for field in ('refunded_at', 'resolution_reason', 'contact_phone', 'contact_name', 'destination_lng', 'destination_lat',
                  'daily_number', 'service_date', 'tracking_token', 'public_ref'):
        op.drop_column('orders', field)
    op.drop_constraint('users_role_check', 'users', type_='check')
    op.execute("UPDATE users SET role = CASE WHEN can_manage THEN 'admin' ELSE 'kitchen' END WHERE role = 'manager'")
    op.create_check_constraint('users_role_check', 'users', "role IN ('customer','admin','kitchen')")
