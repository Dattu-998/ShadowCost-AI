# Deploying ShadowCost

Two pieces: the **API** (FastAPI, Python) on Render and the **web app** (Next.js) on Vercel.
Both have free plans. Deploy the API first, because the web app needs its URL.

## 1. The API on Render

1. Push the repository to GitHub.
2. In the Render dashboard choose **New → Blueprint**, pick the repository, and Render reads
   `render.yaml`: one free web service, `shadowcost-api`, built with `pip install ".[api]"` and
   started with `uvicorn shadowcost.api:app`.
3. When asked for `SHADOWCOST_CORS_ORIGINS`, enter your Vercel URL (for example
   `https://shadowcost.vercel.app`). Comma-separate several. Until you know it, `*` works.
4. Deploy, then open `https://<service>.onrender.com/health` and `/docs` to check it.

Things to know about the free plan:

- The service **sleeps after about 15 minutes idle**. The first request after that takes about
  a minute; the app shows "Waking the API" while it waits.
- The disk is temporary. The public demo's approvals and queue live in SQLite under
  `/tmp/shadowcost` and reset on each restart. Signed-in workspaces keep everything in Supabase,
  so only their processing cache is rebuilt after a restart.
- The "full year" dataset is generated on its first request (about 20 seconds), then reused
  until the next restart.

The demo needs no Groq key: the bundled `specs/` were drafted ahead of time with
`shadowcost-agent generate`. Signed-in workspaces draft from their own data when `GROQ_API_KEY` is
set (section 3).

## 2. The web app on Vercel

1. In Vercel choose **Add New → Project** and import the same repository.
2. Set **Root Directory** to `web`. Vercel detects Next.js.
3. Add the environment variables:
   - `NEXT_PUBLIC_API_URL`: the Render URL, e.g. `https://shadowcost-api.onrender.com`
   - `NEXT_PUBLIC_REPO_URL`: the GitHub repository URL (used by the footer links)
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: from Supabase (see
     below). Without them the site and the public demo still work; sign-up is switched off.
4. Deploy. The data in `/demo` and `/app` comes from the API in the browser.
5. Put the Vercel URL into Render's `SHADOWCOST_CORS_ORIGINS` if you used `*` before.

## 3. Accounts, billing, email and connectors

The signed-in product (`/signup`, `/app`) needs Supabase; everything else is optional and switches
itself on when its keys are present (`GET /v1/me` reports which features are live).

**Supabase (required for accounts).** The schema is in `supabase/migrations/`; apply it with the
Supabase CLI (`supabase db push`) or paste the files into the SQL editor, in order.

- Project settings → API keys: put the **secret** key into Render as `SUPABASE_SECRET_KEY`.
- Authentication → URL configuration: set **Site URL** to the Vercel URL and add
  `https://<vercel-url>/auth/callback` to **Redirect URLs** (and `http://localhost:3000/auth/callback`
  for local work).
- Authentication → Emails: Supabase's built-in sender is rate-limited; add custom SMTP (Resend
  offers it) before real sign-ups.

**Stripe (test mode).** Copy the test secret key into `STRIPE_SECRET_KEY`, then create the
products once with `python scripts/stripe_setup.py`. Add a webhook endpoint pointing at
`https://<render-url>/v1/stripe/webhook` with the events `checkout.session.completed` and
`customer.subscription.created/updated/deleted`; its signing secret is `STRIPE_WEBHOOK_SECRET`.
Turn on the Customer Portal in Stripe's billing settings.

**Resend.** `RESEND_API_KEY`, and `EMAIL_FROM` with an address on a domain you verified there.
Without it, invitations show a link to copy and notifications are logged only.

**Google Sheets and Gmail.** In Google Cloud, enable the Sheets and Gmail APIs, configure the
OAuth consent screen (scopes `spreadsheets.readonly` and `gmail.readonly`; in testing mode, add
your test users) and create a *Web application* OAuth client with the redirect URI
`https://<render-url>/v1/connectors/google/callback`. Set `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, and `TOKEN_ENCRYPTION_KEY` (Render generates one from the blueprint).

**Daily sync.** `.github/workflows/sync.yml` calls `/v1/cron/sync` each morning. Set a random
`CRON_SECRET` on Render, add the same value and `API_URL` as GitHub repository secrets, and set the
repository variable `SYNC_ENABLED` to `true`.

**Groq.** `GROQ_API_KEY` lets workspaces draft agents from their own data. Without it, only the
sample's bundled specs are available.

## Docker

The `Dockerfile` builds the API alone, for any container host:

```bash
docker build -t shadowcost-api .
docker run -p 8000:8000 shadowcost-api
```

The demo routes (`/datasets/...`, `/specs`) have no authentication and serve only the bundled
sample. Customer data goes through the `/v1` routes, which require a Supabase session.
