FROM ghcr.io/rgaudin/uwsgi-nginx:python3.13-trixie
LABEL org.opencontainers.image.source=https://github.com/offspot/imager-service

# connect to DB
ENV MONGODB_URI=mongo
# to create initial scheduler user for manager
ENV MANAGER_ACCOUNT_PASSWORD=manager
# to send URLs via email
ENV PUBLIC_URL=https://imager.kiwix.org
# to build URLs Shop redirects to
ENV CARDSHOP_API_URL=https://api.imager.kiwix.org
# manager API URL to create user accounts (use sloppy version)
ENV MANAGER_API_URL=https://imager.kiwix.org/api
# API token on manager to create user accounts
ENV MANAGER_ACCOUNTS_API_TOKEN=dev
ENV SHOP_PUBLIC_URL=https://www.kiwix.org/en/cardshop-access/
# mailgun-related (used if defined)
# ENV MAILGUN_API_KEY
ENV MAILGUN_API_URL=https://api.mailgun.net/v3/cardshop.hotspot.kiwix.org
ENV MAIL_FROM="Kiwix Imager <contact+imager@kiwix.org>"
# sends an email to this address on startup
#ENV TEST_EMAIL
ENV SUPPORT_EMAIL=stephane@kiwix.org
# sloppy-specific (sloppy cant access other container via public routes)
ENV CARDSHOP_API_INTERNAL_URL=http://scheduler.backend.cardshop.kiwixoffline.node.intern
# default values for warehouses
ENV DEFAULT_WAREHOUSE_DOWNLOAD_URI=s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-warehouse
ENV DEFAULT_WAREHOUSE_UPLOAD_URI=s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-warehouse
ENV DOWNLOAD_WAREHOUSE_DOWNLOAD_URI=https+torrent://org-kiwix-hotspot-cardshop-download.s3.us-west-1.wasabisys.com
ENV DOWNLOAD_WAREHOUSE_UPLOAD_URI=s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-download
ENV PRIVATE_SSH_KEY_PATH=/etc/ssh/uploader.key

ENV UWSGI_INI=/app/uwsgi.ini
EXPOSE 80 443

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && apt-get update -y \
    && apt-get install -y --no-install-recommends \
        cron curl ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    # remove demo app from base image
    && rm -rf /app

COPY src /app
COPY src/entrypoint.sh /scheduler-entrypoint.sh
COPY crontab /etc/cron.d/scheduler-cron
RUN pip install -r /app/requirements.txt \
    && touch /container.env\
    && touch $PRIVATE_SSH_KEY_PATH \
    && chmod 755 /scheduler-entrypoint.sh \
    && chmod +x /etc/cron.d/scheduler-cron \
    && crontab /etc/cron.d/scheduler-cron \
    && rm -rf /lib/systemd/system/supervisor.service \
    && update-rc.d -f supervisor remove \
    && rm -f /etc/init.d/supervisor

WORKDIR /app
ENTRYPOINT ["/scheduler-entrypoint.sh"]
CMD ["/usr/bin/supervisord"]
