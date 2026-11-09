# OrderDesk developer notes

OrderDesk has two independently deployable Next.js apps: `frontend/` for customers and `operations/` for staff. FastAPI owns pricing, payment simulation, permissions and order state. PostgreSQL stores operational data and the event log. The initial customer menu is server rendered from the public API and revalidated by the browser.

## Run locally

Use Docker Compose, Node.js 22 for host-side frontend work, and Python 3.13 for host-side API work. Copy `.env.example` to `.env` if one does not exist. Set your own demo-only `POSTGRES_PASSWORD` and `DEMO_PASSWORD`, and use the same database credentials in `DATABASE_URL`. Keep `.env` and `frontend/.env.local` private.

```sh
docker compose up --build
```

- Customer menu and checkout at `http://localhost:3000`
- Staff sign-in at `http://localhost:3001/login`
- FastAPI health and OpenAPI at `http://localhost:8000/health` and `http://localhost:8000/docs`
- PostgreSQL listens on loopback port 5438. Compose runs migrations before starting the API and seeds only with `DEMO_MODE=true`.

For host development, start only the database with `docker compose up -d db`. From `backend/`, install `requirements.lock.txt` into your virtual environment and run:

```sh
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --timeout-graceful-shutdown 3 --no-access-log
```

In a second terminal, run `npm ci` and `npm run dev` from `frontend/`. When `APP_ORIGIN` points to a loopback host, the API accepts both `localhost` and `127.0.0.1` on the configured frontend port. Browser requests use the same loopback hostname as the page so session cookies work. Set `NEXT_PUBLIC_API_URL` for other API addresses and `API_INTERNAL_URL` when server rendering needs a different private address. Compose sets the internal address automatically.

## Try one order

1. Browse the menu as a guest and add a family portion with an extra. In the bag, use **Choose delivery point** and select the synthetic Kondapur neighbourhood. The server chooses the outlet.
2. Use a fictional name and a synthetic mobile such as `6000000000`. Apply the demo coupon `DIRECT10` for 10% off up to ₹150, or try rewards. Choose UPI or Card and simulate a result. Keep the tracking page open.
3. In a separate tab, sign in to operations as `manager.kondapur@orderdesk.demo` with the configured `DEMO_PASSWORD`. Accept the order and adjust preparation with the ±5-minute buttons. The customer and staff sessions use separate HTTP-only cookies, so both tabs can share a browser.
4. Enter Kitchen Mode. You can also sign in from a separate browser profile as `kitchen.kondapur@orderdesk.demo`. Mark the ticket ready, then confirm handoff. The tracker updates through SSE. The live kitchen excludes terminal tickets and earlier shifts.
5. Use `admin@orderdesk.demo` for central menu permissions. The same synthetic password applies. Change stock for a single outlet or edit a central dish and watch the menu update.
6. Submit a party request at least six hours ahead. Confirm capacity or reject with a reason in the Control Room’s **Party requests** section. The kitchen schedule lists confirmed requests and the customer link shows the decision.

### Demo rewards

Enter a synthetic number from `6000000000` through `6000000099` and select **Queue demo SMS**. Read the local outbox from `backend/` using `python -m app.demo_inbox 6000000000`, or from the repo root using `docker compose exec api python -m app.demo_inbox 6000000000`. Enter the returned code in checkout. The app earns one point per ₹100 paid at handoff. Each point redeems ₹1, up to 20% of the food subtotal. Remove any coupon before redeeming. A cancelled order restores redeemed points.

## Design and assumptions

- The 14 outlets and three cloud kitchens use documented Hyderabad neighbourhood reference points as their demo pins. Service radii, generated food imagery, allergy details and licence placeholders are synthetic. The three named client order samples and their totals, payment modes, times and stages are preserved. Their assumed reference day is 2 November 2026 IST and their sample clock is fixed at 21:20 IST.
- Routing filters for open outlets within their service radius, then compares full-precision Haversine distances. The stable outlet ID breaks exact ties. Stock and current routing are revalidated at payment confirmation. The chosen outlet and prices are snapshotted in the paid order.
- The delivery picker defaults to OpenStreetMap street tiles, with pan, mouse-wheel, pinch and button zoom, tap or drag to select a pin, geolocation, and manual coordinates. It shows the selected outlet’s service radius and never requests a driving route during address selection. Configure `NEXT_PUBLIC_MAP_TILE_URL` and `NEXT_PUBLIC_MAP_ATTRIBUTION` to change the raster provider. [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
- The order tracker loads driving distance and highlights the outlet-to-destination route automatically. Checkout explains that the routing provider receives both pins and that the demo provider logs requests. Demo mode uses the FOSSGIS OSRM car service. For other environments set `ROUTING_API_URL` to a compatible OSRM endpoint. A routing outage leaves the map pins, order tracking, and checkout available. [FOSSGIS routing policy](https://routing.openstreetmap.de/about.html)
- The checkout uses integer paise. GST is embedded in the discounted total at 5/105, rounded to the nearest paise. The demo has free delivery. Marketing consent is separate from transactional updates.
- Each order has an internal UUID, a unique public reference, and a unique daily number per outlet and IST service date. A PostgreSQL upsert allocates the daily number inside the payment transaction. A payment attempt is unique per user and idempotency key. Locking the cart and payment prevents two confirmations from creating separate orders.
- Paid orders enter the assigned kitchen immediately. Kitchen staff start preparation, mark orders ready, confirm handoff, and can cancel new or preparing orders for an unavailable item. Only party requests require manager approval. Use `manager.all@orderdesk.demo` with the configured demo password to manage any outlet. A cancellation records a simulated reversal.
- The prep model is ordinary least squares, trained on 480 reproducible synthetic observations with 120 held out. Features include outlet load, pending quantities, maximum item prep and recent completions. Promise duration takes the higher of the model or fallback estimate and the outlet minimum. Manager changes are audited. The worker alerts once when an active ticket passes its current promise by ten minutes.
- SSE replays the committed PostgreSQL event log. Separate streams expose outlet stock, outlet-scoped operations, or an individual opaque tracking token. Reconnect sends a cursor and refetches canonical state. The demo uses one-second DB polling per active stream and a 15-second recovery fetch when disconnected. Order board hydration uses batched queries. Multi-worker production would benefit from shared event fan-out and a proxy with SSE buffering disabled.
- Reports use paid orders in the selected rolling placement window. Prep duration is measured from the start of preparation to ready. Repeat customers count verified numbers with at least two handoffs at that outlet in the window. Historical samples are excluded.

## Separate deployments

`frontend/` and `operations/` each own their package lock, Next app routes, components, styles, public assets and Dockerfile. Run `docker compose up -d --build` to start both, or build each directory separately. Customer routes use port 3000; staff routes use port 3001 at `/dashboard`, `/orders`, `/menu`, `/kitchen`, `/display` and `/login`. Customer routes no longer include `/ops`.

Both apps proxy `/api` to `API_INTERNAL_URL`. Set API `APP_ORIGIN` and `OPS_APP_ORIGIN` to their deployed domains. Set `CUSTOMER_SITE_URL` on operations to the public customer origin for the QR. Use `COOKIE_SECURE=true` with HTTPS. Host-side dev commands are `npm run dev` in each app directory (3000 and 3001 respectively).

Outlet staff remain pinned to their account outlet. Central accounts with no assigned outlet currently open the first outlet; no outlet switch is presented. Live queues cover the last 12 hours, including cross-midnight work; older unresolved tickets remain available to managers in history.

Preparation adjustments use `/orders/{id}/adjust-time`, accept only ±5, validate outlet and version, clamp to the outlet minimum, and emit `order.eta_updated`. They do not create promise-history rows. Tracking arrival combines the current preparation time with an effective 20 km/h driving estimate and five-minute handoff allowance using OSRM road distance. Routing outages show an unavailable ETA.

With MOBILE_LOGIN_SKIP_OTP=true, mobile sign-in skips OTP and retrieves orders for that mobile across sessions. When that flag is false, cross-session history requires the session to have verified that number. Marketing remains separate opt-in.

## Touch operations and repeat checkout

The kitchen shows one responsive grid of active live tickets, oldest first, with preparation, cancellation, completion and direct time controls. Offscreen tickets use content visibility to reduce painting work; timers update every 15 seconds. Control Room cards open a manager action dialog. Outlet selection uses a button grid dialog, and stock changes use full-width state buttons.

After successful checkout, the authenticated customer session can read its own last order contact details through `/auth/profile`. Contact and address fields are reused until edited. Customer cookies last 30 days; staff cookies remain 12 hours. Contact is remembered on the browser; mobile sign-in restores matching order history across sessions with local OTP skipping enabled, or after verification when disabled. Marketing consent is separate and persisted with the payment confirmation. Database order retention is independent of cookie expiry.

All seeded outlets use the deliberately invalid placeholder FSSAI number `00000000000000`; replace these with verified licences before real service. Sample snapshot tabs and customer-facing demo labels are removed; payment simulation remains explicitly identified.

Local capacity smoke check on 4 November 2026: 25 orders at 3-second intervals (1,200/hour arrival rate) across the seeded outlets, with 25 duplicate confirmations. All completed with unique tickets and idempotent confirmations. Full synthetic purchase flow p50 166 ms, p95 798 ms; elapsed 72.76 seconds. This used an isolated PostgreSQL database and in-process ASGI requests, so it does not establish sustained production network, SSE fan-out, or physical Android tablet capacity.

## Detailed dashboard and delivery tracking

The manager dashboard offers 24-hour, 7-, 30- and 90-day rolling windows. PostgreSQL aggregates status counts, gross and retained order value, cancellations, discounts, tax, hourly demand in IST, daily totals, payment mix, top dishes and preparation percentiles. Contact repeat rates group supplied phone numbers and exclude cancellations; they do not imply verified identity. Preparation punctuality compares the marked-ready timestamp with the current promise. Live ticket counts cover the last 12 hours; stock is current. Party totals count requests created in the selected window, while upcoming dates are independent of creation time. No customer contact details are exposed in the report response.

Customer tracking presents an OrderDesk terracotta status header with remaining minutes, the actual OSM driving route, delivery address and expandable receipt. Refresh and SSE updates recalculate the countdown. Unknown or overdue estimates show an update state instead of an invented countdown. Checkout no longer contains the verification/rewards promotion.

## Order desk and menu display

The manager order desk uses a responsive ticket grid with live status filters, search, quick preparation actions and a separate party-request view. Order details open on demand, including estimate adjustment and a cancellation confirmation. History stays separate from live tickets.

The operations menu display is a passive, full-viewport photo slideshow. Dish details, food marks, allergens, price, QR and FSSAI licence overlay the image. No playback controls or progress indicator are visible. Its QR opens CUSTOMER_SITE_URL at the customer homepage `/`; the separate customer `/menu` landing route has been removed. The normal ordering menu remains on the homepage, and operations `/menu` is the stock CMS.


## Mobile-linked history

Order contact_phone remains the immutable checkout number. GET /orders resolves the history number from the authenticated customer session, not query parameters, and returns that number's orders across guest sessions. GET /orders/{id} applies the same scope. Staff outlet permissions are unchanged. A composite phone / placement-time index supports these lookups; migration does not modify historical orders.

POST /auth/mobile binds the entered number to the current customer. MOBILE_LOGIN_SKIP_OTP=true deliberately skips verification for this local assignment, independently of DEMO_MODE. With MOBILE_LOGIN_SKIP_OTP=false, a matching session verified_phone is required for cross-session access. Saving unverified checkout contact alone never enables production history recovery. Switching mobile numbers resets marketing consent. The orders screen shows the selected number and provides a change-number action. Existing sessions without a phone continue to see only their own orders until mobile sign-in.


Routing configuration is independent of sample data. Set ROUTING_API_URL=https://routing.openstreetmap.de/routed-car for the local OSM-based routing service even when DEMO_MODE=false. A configured endpoint is required outside demo mode; leave DEMO_MODE disabled to avoid reseeding. The public service is suitable for local evaluation; production can point the same setting at a dedicated OSRM service.
