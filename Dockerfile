# The ShadowCost API. The web frontend lives in web/ and deploys to Vercel.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
COPY data/sample ./data/sample
COPY specs ./specs

ENV SHADOWCOST_WORKSPACE=/tmp/shadowcost
EXPOSE 8000
CMD ["sh", "-c", "uvicorn shadowcost.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
