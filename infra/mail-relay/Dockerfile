ARG PROXY_UBUNTU_BASE_IMAGE=ubuntu:24.04
FROM ${PROXY_UBUNTU_BASE_IMAGE}

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends msmtp msmtp-mta ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && command -v msmtpd >/dev/null \
    && command -v msmtp >/dev/null \
    && groupadd --gid 10002 geem-mail \
    && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin geem-mail

COPY render_config.py /usr/local/lib/geem/render_mail_relay_config.py

USER geem-mail
EXPOSE 25

ENTRYPOINT ["python3", "/usr/local/lib/geem/render_mail_relay_config.py"]
