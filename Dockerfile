FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[app]"
COPY app ./app
COPY data/sample ./data/sample
COPY specs ./specs
COPY .streamlit ./.streamlit

ENV SHADOWCOST_WORKSPACE=/tmp/shadowcost
EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
