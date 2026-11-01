# Deploying ShadowCost

## Streamlit Community Cloud (free)

1. Push the repository to GitHub (public, or private with Streamlit's access).
2. Go to <https://share.streamlit.io>, sign in with GitHub, and choose
   **Create app → Deploy a public app from GitHub**.
3. Repository: your ShadowCost repo. Branch: `main`. Main file path:
   `app/streamlit_app.py`. Streamlit installs from `requirements.txt`, which
   installs this package with its `app` extras.
4. Optional, to draft specs for uploaded data: **Advanced settings → Secrets**:

   ```toml
   GROQ_API_KEY = "gsk_..."
   ```

   Without it the app runs on the bundled specs, which cover the sample and the
   simulated year.
5. Deploy. The first load of "Simulated year" takes about 20 seconds while it
   generates and ingests a year of data; after that it's cached.

The app's workspace (approvals, outbox, uploads) lives on the container's disk,
so it resets when Streamlit restarts the app. That's fine for a demo. For real
use, point `SHADOWCOST_WORKSPACE` at persistent storage.

## Docker (Hugging Face Spaces, Render, Fly.io, or anywhere)

```bash
docker build -t shadowcost .
docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... shadowcost
```

On Hugging Face Spaces, create a **Docker** Space, push this repository to it,
set the app port to 8501, and add `GROQ_API_KEY` as a secret.

## API

```bash
pip install -e ".[app]"
uvicorn shadowcost.api:app --host 0.0.0.0 --port 8000
```

Interactive docs are at `/docs`. The API has no authentication: put it behind
one before exposing it beyond a demo.
