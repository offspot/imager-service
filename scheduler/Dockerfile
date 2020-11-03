FROM tiangolo/uwsgi-nginx:python3.8

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends cron curl xfonts-75dpi xfonts-base ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN curl -k -O -L https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.buster_amd64.deb && \
    apt-get install -y --no-install-recommends ./wkhtmltox_0.12.6-1.buster_amd64.deb && \
    rm ./wkhtmltox_0.12.6-1.buster_amd64.deb
RUN wkhtmltopdf --version

# connect to DB
ENV MONGODB_URI mongo
# to create initial scheduler user for manager
ENV MANAGER_ACCOUNT_PASSWORD manager
# to send URLs via email
ENV PUBLIC_URL https://cardshop.hotspot.kiwix.org
# to build URLs Stripe redirects to
ENV CARDSHOP_API_URL https://api.cardshop.hotspot.kiwix.org
# manager API URL to create user accounts (use sloppy version)
ENV MANAGER_API_URL https://cardshop.hotspot.kiwix.org/api
# API token on manager to create user accounts
ENV MANAGER_ACCOUNTS_API_TOKEN dev
# to include in shop widget
ENV STRIPE_PUBLIC_API_KEY -
# to create sessions
ENV STRIPE_API_KEY -
# Stripe Products
ENV STRIPE_METHOD_WP payment
ENV STRIPE_METHOD_ACCESS1M payment
ENV STRIPE_METHOD_ACCESS1Y payment
ENV STRIPE_PRICE_WPEN
ENV STRIPE_PRICE_WPFR
ENV STRIPE_PRICE_WPDE
ENV STRIPE_PRICE_WPES
ENV STRIPE_PRICE_ACCESS1M
ENV STRIPE_PRICE_ACCESS1Y
# to send to Stripe as “go back” button
ENV SHOP_PUBLIC_URL https://www.kiwix.org/en/cardshop-access/
# SMTP email-related (we use mailgun)
# enctype: auto,tls,ssl,none (defaults to tls)
# port: based on enctype or set for local debug
# skip_login: for local debug (without auth)
ENV SMTP_USERNAME SMTP_USERNAME
ENV SMTP_PASSWORD SMTP_PASSWORD
ENV SMTP_HOST smtp.gmail.com
ENV SMTP_ENCTYPE auto
ENV SMTP_PORT auto
ENV SMTP_SKIP_LOGIN 0
# mailgun-related (used if defined)
ENV MAILGUN_API_KEY
ENV MAILGUN_API_URL https://api.mailgun.net/v3/cardshop.hotspot.kiwix.org
ENV MAIL_FROM Hotspot Cardshop <hotspot@kiwix.org>
# sends an email to this address on startup
ENV TEST_EMAIL
ENV SUPPORT_EMAIL stephane@kiwix.org
# sloppy-specific (sloppy cant access other container via public routes)
ENV CARDSHOP_API_INTERNAL_URL http://scheduler.backend.cardshop.kiwixoffline.node.intern
# default values for warehouses
ENV DEFAULT_WAREHOUSE_DOWNLOAD_URI s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-warehouse
ENV DEFAULT_WAREHOUSE_UPLOAD_URI s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-warehouse
ENV DOWNLOAD_WAREHOUSE_DOWNLOAD_URI https+torrent://org-kiwix-hotspot-cardshop-download.s3.us-west-1.wasabisys.com
ENV DOWNLOAD_WAREHOUSE_UPLOAD_URI s3://s3.us-west-1.wasabisys.com/?bucketName=org-kiwix-hotspot-cardshop-download


RUN rm -rf /app
COPY src /app
COPY src/entrypoint.sh /scheduler-entrypoint.sh

RUN chmod 755 /scheduler-entrypoint.sh

RUN pip install -r /app/requirements.txt

ENV UWSGI_INI /app/uwsgi.ini
WORKDIR /app

RUN touch /container.env
COPY crontab /etc/cron.d/scheduler-cron
RUN chmod +x /etc/cron.d/scheduler-cron
RUN crontab /etc/cron.d/scheduler-cron

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/scheduler-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
