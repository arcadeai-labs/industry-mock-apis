# Industry Demo APIs: FastAPI + embedded Postgres 17 with mock data, in one container.
FROM postgres:17-alpine

RUN apk add --no-cache python3 bash curl tini \
 && addgroup -S api && adduser -S -G api -H -h /app api

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app
COPY docker/initdb/ /docker-entrypoint-initdb.d/
COPY docker/entrypoint.sh /usr/local/bin/industry-entrypoint.sh
RUN chmod 755 /usr/local/bin/industry-entrypoint.sh /docker-entrypoint-initdb.d/*.sh \
 && /opt/venv/bin/python -m compileall -q /app/app

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POSTGRES_USER=demo \
    POSTGRES_DB=industry

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8080/health >/dev/null || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/industry-entrypoint.sh"]
