"""Move original demo pins to documented Hyderabad locality reference points."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_map_pins'
down_revision = '20261104_depth'
branch_labels = None
depends_on = None

PINS = (
    ('kondapur', 17.4622, 78.3568, 17.45879, 78.37306),
    ('kukatpally', 17.4948, 78.3996, 17.4931, 78.4054),
    ('jubilee-hills', 17.4311, 78.4073, 17.43084, 78.41029),
    ('banjara-hills', 17.4156, 78.4347, 17.41775, 78.4399),
    ('madhapur', 17.4483, 78.3915, 17.44089, 78.39163),
    ('hitech-city', 17.4504, 78.3808, 17.44441, 78.3779),
    ('begumpet', 17.4448, 78.4664, 17.4462, 78.46302),
    ('secunderabad', 17.4399, 78.4983, 17.432, 78.487),
    ('manikonda', 17.4015, 78.3753, 17.40371, 78.37662),
    ('miyapur', 17.4968, 78.3614, 17.49816, 78.35676),
    ('sainikpuri', 17.4860, 78.5400, 17.48922, 78.54249),
    ('dilsukhnagar', 17.3687, 78.5247, 17.36887, 78.52562),
    ('lb-nagar', 17.3457, 78.5522, 17.3502, 78.5511),
    ('gachibowli', 17.4401, 78.3489, 17.44362, 78.35196),
    ('nallagandla', 17.4708, 78.3006, 17.47748, 78.30604),
    ('uppal', 17.4058, 78.5591, 17.415, 78.5432),
)


def move_demo_pins(reverse=False):
    outlets = sa.table(
        'outlets', sa.column('id'), sa.column('synthetic'), sa.column('lat'), sa.column('lng'),
    )
    for outlet_id, old_lat, old_lng, lat, lng in PINS:
        if reverse:
            old_lat, old_lng, lat, lng = lat, lng, old_lat, old_lng
        # Preserve real locations and demo pins that were already moved by an operator.
        op.execute(outlets.update().where(
            outlets.c.id == outlet_id, outlets.c.synthetic.is_(True),
            outlets.c.lat == old_lat, outlets.c.lng == old_lng,
        ).values(lat=lat, lng=lng))


def upgrade():
    move_demo_pins()


def downgrade():
    move_demo_pins(reverse=True)
