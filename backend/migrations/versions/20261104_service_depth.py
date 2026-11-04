"""Persist loyalty, demonstration verification, and party requests."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_depth'
down_revision = '20261104_control'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sessions', sa.Column('verified_phone', sa.String(10)))
    op.create_table(
        'loyalty_accounts',
        sa.Column('phone', sa.String(10), primary_key=True),
        sa.Column('balance', sa.Integer(), nullable=False),
        sa.CheckConstraint('balance >= 0'),
    )
    op.create_table(
        'otp_challenges',
        sa.Column('session_id', sa.String(64), sa.ForeignKey('sessions.token_hash', ondelete='CASCADE'), primary_key=True),
        sa.Column('phone', sa.String(10), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'demo_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('destination', sa.String(10), nullable=False),
        sa.Column('body', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column('orders', sa.Column('started_at', sa.DateTime(timezone=True)))
    op.add_column('orders', sa.Column('loyalty_phone', sa.String(10), sa.ForeignKey('loyalty_accounts.phone')))
    op.add_column('orders', sa.Column('redeemed_points', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('orders', 'redeemed_points', server_default=None)
    op.create_table(
        'loyalty_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('phone', sa.String(10), sa.ForeignKey('loyalty_accounts.phone'), nullable=False),
        sa.Column('order_id', sa.String(40), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.UniqueConstraint('order_id', 'kind'),
    )
    op.create_table(
        'party_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('token', sa.String(64), nullable=False, unique=True),
        sa.Column('outlet_id', sa.String(50), sa.ForeignKey('outlets.id'), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('phone', sa.String(10), nullable=False),
        sa.Column('address', sa.String(300), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('notes', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reason', sa.String(300)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','accepted','rejected')"),
    )
    op.create_index('ix_party_requests_outlet_id', 'party_requests', ['outlet_id'])
    op.add_column('events', sa.Column('party_id', sa.String(36), sa.ForeignKey('party_requests.id')))
    op.create_index('ix_events_party_id', 'events', ['party_id'])


def downgrade():
    op.drop_column('events', 'party_id')
    op.drop_table('party_requests')
    op.drop_table('loyalty_transactions')
    for column in ('redeemed_points', 'loyalty_phone', 'started_at'):
        op.drop_column('orders', column)
    op.drop_table('demo_messages')
    op.drop_table('otp_challenges')
    op.drop_table('loyalty_accounts')
    op.drop_column('sessions', 'verified_phone')
