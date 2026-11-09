# OrderDesk operations

Independent Next.js staff app. `npm ci` then `npm run dev` starts port 3001. `npm run build` produces a standalone deployment. Set API_INTERNAL_URL at build time; browser API calls remain same-origin at /api. Set CUSTOMER_SITE_URL at runtime for the customer menu QR.

Routes: /dashboard, /orders, /menu, /kitchen, /display, /login. Staff authentication uses a separate HTTP-only cookie and outlet permissions enforced by FastAPI. Docker Compose builds this directory separately from ../frontend.
