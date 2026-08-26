FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends squid ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/spool/squid/*

COPY squid.conf /etc/squid/squid.conf

USER proxy
EXPOSE 3128

CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
