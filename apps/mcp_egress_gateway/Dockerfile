ARG MCP_GATEWAY_PYTHON_BASE_IMAGE=python:3.12.11-slim-bookworm
FROM ${MCP_GATEWAY_PYTHON_BASE_IMAGE} AS runtime-base

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

FROM runtime-base AS verification

RUN pip install --no-cache-dir pytest==8.3.5
COPY . /workspace
ENV PYTHONPATH=/srv/geem:/workspace/apps/api
RUN python -m pytest -q -p no:cacheprovider \
    --confcutdir=/workspace/apps/mcp_egress_gateway/tests \
    /workspace/apps/mcp_egress_gateway/tests \
    && mkdir -p /verification \
    && printf '%s\n' passed > /verification/gateway-tests

FROM runtime-base

# The final image depends on the verification stage, but contains neither the
# repository test tree nor pytest. The copied marker is immediately removed.
COPY --from=verification /verification/gateway-tests /tmp/gateway-tests
RUN test "$(cat /tmp/gateway-tests)" = passed && rm -f /tmp/gateway-tests

USER 10001:10001

EXPOSE 8443

CMD ["python", "-m", "gateway.main"]
