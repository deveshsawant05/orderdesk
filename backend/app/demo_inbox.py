"""Read the newest code for a synthetic phone from the local mock SMS outbox."""
import os
import re
import sys
from datetime import timedelta
from sqlalchemy import select
from .db import SessionLocal
from .loyalty import DEMO_PHONE
from .models import DemoMessage, now


def main():
    if os.getenv('DEMO_MODE') != 'true' or len(sys.argv) != 2 or not re.fullmatch(DEMO_PHONE, sys.argv[1]):
        raise SystemExit('Use DEMO_MODE and a synthetic number from 6000000000 to 6000000099.')
    with SessionLocal() as db:
        message = db.scalar(select(DemoMessage).where(
            DemoMessage.kind == 'otp', DemoMessage.destination == sys.argv[1],
            DemoMessage.created_at >= now() - timedelta(minutes=5),
        ).order_by(DemoMessage.created_at.desc()).limit(1))
        if not message:
            raise SystemExit('No current verification code. Request one from checkout.')
        print(message.body)


if __name__ == '__main__':
    main()
