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
- The disk is temporary. Approvals, shadow runs and the approval queue live in SQLite under
  `/tmp/shadowcost` and reset on each restart or deploy. That's fine for a demo; for real use,
  attach a Render disk and point `SHADOWCOST_WORKSPACE` at it.
- The "full year" dataset is generated on its first request (about 20 seconds), then reused
  until the next restart.

Drafting new specs with the LLM is a CLI step (`shadowcost-agent generate`), so the API needs no
Groq key. The bundled `specs/` were drafted that way.

## 2. The web app on Vercel

1. In Vercel choose **Add New → Project** and import the same repository.
2. Set **Root Directory** to `web`. Vercel detects Next.js.
3. Add the environment variables:
   - `NEXT_PUBLIC_API_URL`: the Render URL, e.g. `https://shadowcost-api.onrender.com`
   - `NEXT_PUBLIC_REPO_URL`: the GitHub repository URL (used by the footer links)
4. Deploy. Every route is prerendered as a static page; the app's data comes from the API in
   the browser.
5. Put the Vercel URL into Render's `SHADOWCOST_CORS_ORIGINS` if you used `*` before.

## Docker

The `Dockerfile` builds the API alone, for any container host:

```bash
docker build -t shadowcost-api .
docker run -p 8000:8000 shadowcost-api
```

The API has no authentication. Keep it to demo data, or put it behind authentication before
pointing it at a real company's files.
