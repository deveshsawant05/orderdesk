# OrderDesk developer notes

OrderDesk uses one Next.js App Router frontend with distinct customer and staff experiences. FastAPI owns pricing, payment simulation, permissions and order state. PostgreSQL stores operational data and the event log. The initial customer menu is server rendered from the public API and revalidated by the browser.

## Run locally

Use Docker Compose, Node.js 22 for host-side frontend work, and Python 3.13 for host-side API work. Copy `.env.example` to `.env` if one does not exist. Set your own demo-only `POSTGRES_PASSWORD` and `DEMO_PASSWORD`, and use the same database credentials in `DATABASE_URL`. Keep `.env` and `frontend/.env.local` private.

```sh
docker compose up --build
```

- Customer menu and checkout at `http://localhost:3010`
- Staff sign-in at `http://localhost:3010/ops/login`
- FastAPI health and OpenAPI at `http://localhost:8010/health` and `http://localhost:8010/docs`
- PostgreSQL listens on loopback port 5438. Compose runs migrations before starting the API and seeds only with `DEMO_MODE=true`.

For host development, start only the database with `docker compose up -d db`. From `backend/`, install `requirements.lock.txt` into your virtual environment and run:

```sh
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload --no-access-log
```

In a second terminal, run `npm ci` and `npm run dev` from `frontend/`. The API browser origin defaults to `http://localhost:3010`. Set `NEXT_PUBLIC_API_URL` for other API addresses and `API_INTERNAL_URL` when server rendering needs a different private address. Use the same browser hostname for web and API in local development. Compose sets the internal address automatically.

## Try one order

1. Browse the menu as a guest and add a family portion with an extra. In the bag, use **Choose delivery point** and select the synthetic Kondapur neighbourhood. The server chooses the outlet.
2. Use a fictional name and a synthetic mobile such as `6000000000`. Apply the demo coupon `DIRECT10` for 10% off up to ₹150, or try rewards. Choose UPI or Card and simulate a result. Keep the tracking page open.
3. In a separate tab, sign in to operations as `manager.kondapur@orderdesk.demo` with the configured `DEMO_PASSWORD`. Accept the order, then revise its promise and include a reason. The customer and staff sessions use separate HTTP-only cookies, so both tabs can share a browser.
4. Enter Kitchen Mode. You can also sign in from a separate browser profile as `kitchen.kondapur@orderdesk.demo`. Mark the ticket ready, then confirm handoff. The tracker updates through SSE. Try the client sample tab in Kondapur, Gachibowli, and Kukatpally to see the preserved historical examples.
5. Use `admin@orderdesk.demo` for central menu permissions. The same synthetic password applies. Change stock for a single outlet or edit a central dish and watch the menu update.
6. Submit a party request at least 48 hours ahead. In the manager’s **Party requests** tab, confirm capacity or reject with a reason. The kitchen schedule lists confirmed requests and the customer link shows the decision.

### Demo rewards

Enter a synthetic number from `6000000000` through `6000000099` and select **Queue demo SMS**. Read the local outbox from `backend/` using `python -m app.demo_inbox 6000000000`, or from the repo root using `docker compose exec api python -m app.demo_inbox 6000000000`. Enter the returned code in checkout. The app earns one point per ₹100 paid at handoff. Each point redeems ₹1, up to 20% of the food subtotal. Remove any coupon before redeeming. A cancelled order restores redeemed points.

## Design and assumptions

- The 14 outlets, three cloud kitchens, service radii, coordinates, generated food imagery, allergy details and licence placeholders are synthetic. The three named client order samples and their totals, payment modes, times and stages are preserved. Their assumed reference day is 2 November 2026 IST and their sample clock is fixed at 21:20 IST.
- Routing filters for open outlets within their service radius, then compares full-precision Haversine distances. The stable outlet ID breaks exact ties. Stock and current routing are revalidated at payment confirmation. The chosen outlet and prices are snapshotted in the paid order.
- The default map uses a local coordinate grid. To offer street tiles in the delivery picker, configure `NEXT_PUBLIC_MAP_TILE_URL` and `NEXT_PUBLIC_MAP_ATTRIBUTION` for your approved raster provider. Users explicitly load the tiles and can return to the grid. Tracking draws only the assigned outlet and destination. For OpenStreetMap tiles, follow the [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
- The checkout uses integer paise. GST is embedded in the discounted total at 5/105, rounded to the nearest paise. The demo has free delivery. Marketing consent is separate from transactional updates.
- Each order has an internal UUID, a unique public reference, and a unique daily number per outlet and IST service date. A PostgreSQL upsert allocates the daily number inside the payment transaction. A payment attempt is unique per user and idempotency key. Locking the cart and payment prevents two confirmations from creating separate orders.
- Managers accept or cancel active paid orders for their assigned outlet. Kitchen staff can progress an accepted order to ready and handed off. Central permission is a manager capability. A cancellation writes a reversal event. No real payments or external notifications are sent.
- The prep model is ordinary least squares, trained on 480 reproducible synthetic observations with 120 held out. Features include outlet load, pending quantities, maximum item prep and recent completions. Promise duration takes the higher of the model or fallback estimate and the outlet minimum. Manager changes are audited. The worker alerts once when an active ticket passes its current promise by ten minutes.
- SSE replays the committed PostgreSQL event log. Separate streams expose outlet stock, outlet-scoped operations, or an individual opaque tracking token. Reconnect sends a cursor and refetches canonical state. The demo uses one-second DB polling per active stream and a 15-second recovery fetch when disconnected. Order board hydration uses batched queries. Multi-worker production would benefit from shared event fan-out and a proxy with SSE buffering disabled.
- Reports use paid orders in the selected rolling placement window. Prep duration is measured from acceptance to ready. Repeat customers count verified numbers with at least two handoffs at that outlet in the window. Historical samples are excluded.
- Street addresses require a pin or coordinates. There is no automatic address geocoder. Phone verification uses the local mock outbox. Reorder recommendations are outside the implemented slice. Real licence verification and production privacy review are required before taking real orders.

## Development checks

- Backend tests use a separate `orderdesk_test` database. Create it in PostgreSQL first, for example with `docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" orderdesk_test'`. From `backend/` run `python -m pytest -q`. The test fixture applies migrations and seeds the test database. Override its connection with `TEST_DATABASE_URL`.
- From `frontend/` run `npm run typecheck`, `npm run lint` and `npm run build`. With both local services running, run `node --env-file=../.env node_modules/@playwright/test/cli.js test`. Add `--env-file=.env.local` after the first env-file option if you use a frontend override. The suite uses Microsoft Edge by default. Captures go to the ignored `artifacts/` directory.
- For a repeatable smoke workload, create a separate `orderdesk_load` database and migrate and seed it with `DATABASE_URL` pointed there. Set `LOAD_DATABASE_URL` to the same address. From `backend/` run `python -m tests.load_smoke --count 20` for same-outlet concurrency and `python -m tests.load_smoke --count 24 --interval 3` for 1,200 orders/hour pacing.
- The local smoke run confirmed 20 same-outlet checkouts and 20 duplicate confirmation requests in 1.92 seconds, at 441 ms p95 per checkout. The paced run completed 24 checkouts plus 24 duplicate confirmation requests at 154 ms p95. These were FastAPI ASGI-to-PostgreSQL measurements, excluding browser, network and sustained SSE load.
