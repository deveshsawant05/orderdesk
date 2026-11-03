# OrderDesk implementation contract

## Confirmed facts
- Official core: ordering, menu/customization, cart, test payment, central menu CMS, kitchen display, real-time updates, AI preparation estimates.
- PostgreSQL is mandatory. No fallback database or frontend business fixtures.
- 14 physical outlets and three cloud kitchens. Three exact client sample orders.
- Prices include 5% GST. Preparation promise = max(prediction, outlet minimum).
- Outlet-scoped staff and customer-owned orders. No publication/submission authorized.

## Assumptions
- Company A is the restaurant label; OrderDesk is the product (final QuoteDesk mention is interpreted as a typo).
- All coordinates, delivery radii, addresses, extra outlet names, menu configurations, accounts and imagery are synthetic.
- Snapshot reference: 2026-11-02 21:20 Asia/Kolkata. Third sample status is preparing with a recorded late observation, not a separate state.
- Hyderabad is the seeded city; price overrides support other cities in the schema/editor.
- Delivery is free for this assessment. DIRECT10 is a synthetic 10% food coupon, capped at INR 150.
- An explicit demo sign-in creates a real authenticated session backed by a persisted demo account. It is disabled outside DEMO_MODE.

## Architecture / priorities
1. FastAPI + PostgreSQL + SQLAlchemy + Alembic. Normalized users, sessions, outlets, menu, availability, carts, orders, items, payments, estimates, events and notifications. Money in integer paise, canonical UTC timestamps.
2. Authenticated Next.js App Router frontend. Server validates every mutation, row locking serializes checkout and status updates.
3. Database event log + SSE, filtered server-side by customer/outlet, cursor replay, initial state fetch and polling recovery. Committed order state is authoritative.
4. Small regression model trained reproducibly on synthetic kitchen observations; persisted features and outputs, conservative fallback and minimum-time guardrail.
5. Customer editorial menu, warm cream/brick palette; dark, large-type kitchen tickets; compact central menu editor.

## Screen plan
Sign-in / location, menu with customization dialog, cart / checkout, test payment, live tracking/history, kitchen, central menu CMS.

## Verification checklist
- [ ] Repeatable migration and non-destructive seed (17 outlets, exact samples).
- [ ] Customer/staff authentication and outlet authorization.
- [ ] Persisted cart, server totals, customization and availability revalidation.
- [ ] Transactional idempotent simulated payment and order creation.
- [ ] Correct kitchen live delivery and customer status synchronization.
- [ ] CMS edits and per-outlet availability persist and propagate.
- [ ] Trained estimate, minimum protection, override and late escalation.
- [ ] Database integration tests, rendered mobile/tablet/desktop checks.
- [ ] Restart/reseed persistence and explicit backend-unavailable errors.
- [ ] Docker, deployment instructions, TDD and exact two-file submission ZIP.

Optional loyalty, party ordering and analytics are deferred until the core is verified.
