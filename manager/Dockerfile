FROM docker.io/library/python:3.11-slim-bookworm
LABEL org.opencontainers.image.source https://github.com/offspot/cardshop

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y \
    && apt-get -y --no-install-recommends install \
        curl \
        python3-dev default-libmysqlclient-dev build-essential pkg-config \
        cron libmagic1 \
        supervisor \
    && curl -o /tmp/caddy_2.7.4_linux_amd64.deb -L https://github.com/caddyserver/caddy/releases/download/v2.7.4/caddy_2.7.4_linux_amd64.deb \
    && dpkg -i /tmp/caddy_2.7.4_linux_amd64.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /lib/systemd/system/supervisor.service \
    && update-rc.d -f supervisor remove \
    && rm -f /etc/init.d/supervisor \
    && pip install -U pip uwsgi==2.0.22

# install main setup: supervisor, which launches uwsgi and caddy
COPY uwsgi.ini /etc/uwsgi/uwsgi.ini
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY Caddyfile /etc/caddy/Caddyfile

# install code
COPY pyproject.toml README.md /app/
COPY manage.py /app/manage.py
COPY manager /app/manager
COPY locale /app/locale
COPY contents.json /app/contents.json
COPY uwsgi-manager.ini /etc/uwsgi/manager.ini
RUN pip install /app

# install health-check app code (in its own env)
COPY status /app/status
RUN python3 -m venv /app/status-env \
    && /app/status-env/bin/pip install -r /app/status/requirements.txt
COPY uwsgi-status.ini /etc/uwsgi/uwsgi-status.ini

# install periodic-tasks cron job
RUN printf "SHELL=/bin/bash\n\
BASH_ENV=/container.env\n\
DJANGO_SETTINGS_MODULE=manager.settings\n\
*/5 * * * * cd /app && /usr/local/bin/python ./manage.py periodic_tasks >> /proc/1/fd/1 2>>/proc/1/fd/2\n\
" > /etc/cron.d/manager-cron \
    && touch /etc/cron.d/manager-cron \
    && chmod 0644 /etc/cron.d/manager-cron \
    && crontab /etc/cron.d/manager-cron

# install entrypoint to prepare DB and collect static
COPY entrypoint.sh /manager-entrypoint.sh
RUN chmod 755 /manager-entrypoint.sh

WORKDIR /app
VOLUME /data
ENV DATA_DIR /data
ENV CARDSHOP_API_URL https://api.cardshop.hotspot.kiwix.org
ENV CARDSHOP_API_URL_EXTERNAL https://api.cardshop.hotspot.kiwix.org
ENV MANAGER_API_TOKEN NOT_SET
ENV ADMIN_PASSWORD admin
ENV SUPPORT_EMAIL stephane@kiwix.org

# for status page
ENV STATUS_S3_URL "http://org-kiwix-hotspot-cardshop-download.s3.us-west-1.wasabisys.com"
ENV STATUS_CARDSHOP_URL "https://cardshop.hotspot.kiwix.org"
ENV STATUS_CARDSHOP_API_URL "https://api.cardshop.hotspot.kiwix.org"
ENV USERNAME ""
ENV STATUS_MANAGER_PASSWORD ""
ENV MONGODB_URI "mongodb://mongodb"
ENV STATUS_SCHEDULER_USERNAME ""
ENV STATUS_SCHEDULER_PASSWORD ""

EXPOSE 80

ENTRYPOINT ["/manager-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
