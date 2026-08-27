FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends squid ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/spool/squid/*

COPY squid.conf /etc/squid/squid.conf
COPY static-deny-networks.txt /etc/geem/mcp-egress/static-deny-networks.txt
COPY render_config.py /usr/local/lib/geem/render_mcp_proxy_config.py

USER proxy
EXPOSE 3128

ENTRYPOINT ["python3", "/usr/local/lib/geem/render_mcp_proxy_config.py"]
