# OrderDesk deployment

Repository: https://github.com/deveshsawant05/orderdesk

- Customer: https://orderdesk-frontend.vercel.app/
- Operations: https://orderdesk-operations.vercel.app/
- AWS API: http://16.178.180.29:8000/health (demo address; may change after an EC2 stop/start).

## Run locally

Requires Git and Docker Desktop with Linux containers, or Docker Engine with the Compose plugin. Docker installs Node/Python dependencies; host Node, Python and PostgreSQL are not required.

```bash
git clone https://github.com/deveshsawant05/orderdesk.git
cd orderdesk
cp .env.example .env
```

Edit `.env`: set `POSTGRES_PASSWORD` to a locally generated hexadecimal password (no URL-reserved characters) and set `DEMO_PASSWORD` to the reviewer password below. Keep the template's demo seeding and OTP-skip settings for this fictional-data review. Compose constructs the database connection internally; no separate `DATABASE_URL` edit is needed for Docker.

```bash
docker compose up -d --build
```

Wait for the first image builds and API startup. Migrations run automatically, followed by insert-only sample seeding when enabled.

- Customer: http://localhost:3000
- Operations login: http://localhost:3001/login
- API health: http://localhost:8000/health

If startup fails: `docker compose logs --tail=80 api db`. Stop with `docker compose down`; keep the database volume to retain orders. Password changes in `.env` do not reset already-created database or staff passwords.

## Reviewer accounts and access

**Shared demo password: `OrderDesk-demo-2026!`**. These are public, fictional evaluation accounts, not production credentials.

- `manager.all@orderdesk.demo` — central manager; all-outlet dashboard, live/history/party orders, outlet filtering, central menu and stock controls.
- `admin@orderdesk.demo` — central manager with the same chain-wide access.
- `manager.<outlet-id>@orderdesk.demo` — outlet manager; own outlet's dashboard, orders, party decisions and stock. Cannot access another outlet or edit the central menu.
- `kitchen.<outlet-id>@orderdesk.demo` — kitchen staff; own live kitchen orders, preparation/time controls, unavailable-item cancellation, ready/handoff actions and accepted party fulfilment. Cannot approve party requests or access other outlets.
- `customer@orderdesk.demo` — seeded backend customer account. The customer website's normal flow uses name/mobile at checkout, not an email login; use a fictitious number to create orders and recover its history. OTP is skipped for the demo.

Example branch logins: `manager.kondapur@orderdesk.demo` and `kitchen.kondapur@orderdesk.demo`.

Available outlet IDs: `kondapur`, `kukatpally`, `jubilee-hills`, `banjara-hills`, `madhapur`, `hitech-city`, `begumpet`, `secunderabad`, `ameerpet`, `manikonda`, `miyapur`, `sainikpuri`, `dilsukhnagar`, `lb-nagar`, `gachibowli`, `nallagandla`, `uppal`. Substitute any ID in the manager/kitchen patterns above.

## Quick review

Select a deliverable Hyderabad pin near Kondapur, add food and complete a simulated UPI/card payment with fictitious contact details. Keep tracking open. Log into the matching kitchen, prepare the ticket, adjust its time, mark ready and hand off; updates reach the customer through SSE. For catering, request a time at least six hours ahead, accept it as manager, and fulfil it in the separate kitchen party queue. The three supplied historical snapshots are stored but excluded from current queues and analytics; create a new order to review the live flow.

## Deployment and environment names

The customer and operations apps are independent Vercel projects rooted at `frontend` and `operations`. FastAPI and PostgreSQL run in Docker on one EC2 instance in Sydney using the default VPC and a persistent database volume. Browser `/api` requests are rewritten by each frontend to the API. The currently reported public API transport is HTTP; HTTPS to Vercel does not encrypt the Vercel-to-EC2 leg. Only fictitious data should be used.

Environment names (supply private values through deployment settings; never commit `.env`):

- Local Docker credentials: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DEMO_PASSWORD`. Database name and localhost origins have defaults in Compose.
- Backend demo controls: `DEMO_MODE`, `MOBILE_LOGIN_SKIP_OTP` (provided in the local example).
- Deployed backend: `APP_ORIGIN`, `OPS_APP_ORIGIN`, `COOKIE_SECURE`, `ROUTING_API_URL`, `GEOCODER_URL`, plus the database/seed credentials above. `DATABASE_URL` is needed for a standalone backend; Compose constructs it from database credentials.
- Both Vercel projects: `API_INTERNAL_URL`. Leave `NEXT_PUBLIC_API_URL` unset to use its `/api` default, or set it explicitly to the same relative path.
- Operations Vercel project: `CUSTOMER_SITE_URL`, for the customer-site QR.

Set the API origin before building/redeploying either frontend. Use the actual customer/operations origins in the backend's allowlist. No database credentials belong on Vercel. Public OSM routing/geocoding require internet access and have no availability guarantee.

After pulling an update on EC2, rebuild the API image and run `alembic upgrade head` before starting the new API (the Compose startup command also runs migrations). Redeploy both Vercel projects. Do not reseed on every release when demo seeding is disabled, and do not delete volumes containing orders. Tests and screenshots are described in the TDD; sustained production capacity and real-device usability are not claimed.
