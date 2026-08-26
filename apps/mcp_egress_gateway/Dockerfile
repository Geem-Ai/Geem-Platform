FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/geem

WORKDIR /srv/geem

RUN groupadd --system --gid 10001 egress \
    && useradd --system --uid 10001 --gid egress --home-dir /nonexistent egress

COPY apps/mcp_egress_gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Copy only the transport-agnostic policy from the application and the gateway
# package. The image contains no ORM, DB/Redis clients, Celery, provider keys,
# application settings, migrations, or tenant datastore credentials.
COPY apps/mcp_egress_gateway/package_stubs/app/__init__.py /srv/geem/app/__init__.py
COPY apps/mcp_egress_gateway/package_stubs/app/common/__init__.py /srv/geem/app/common/__init__.py
COPY apps/api/app/common/outbound_http.py /srv/geem/app/common/outbound_http.py
COPY apps/mcp_egress_gateway/gateway /srv/geem/gateway

USER 10001:10001

EXPOSE 8443

CMD ["python", "-m", "gateway.main"]
