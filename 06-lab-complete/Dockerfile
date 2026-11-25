FROM python:3.12-slim AS builder
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" PORT=8000 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 agent
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY utils ./utils
USER agent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['PORT'] + '/health', timeout=2)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
