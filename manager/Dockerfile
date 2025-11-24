FROM docker.io/library/python:3.11-slim-bookworm
LABEL="org.opencontainers.image.source https://github.com/offspot/imager-service"

ARG GIT_REV

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y \
    && apt-get -y --no-install-recommends install \
        curl git-core \
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
    && pip install -U pip \
    && python3 -m venv /app/manager-env \
    && python3 -m venv /app/status-env

# install uwsgi from source to be able to build the http plugin (outside venv)
RUN curl -L -O https://files.pythonhosted.org/packages/a7/4e/c4d5559b3504bb65175a759392b03cac04b8771e9a9b14811adf1151f02f/uwsgi-2.0.22.tar.gz \
    && tar xf uwsgi-2.0.22.tar.gz \
    && cd uwsgi-2.0.22 \
    && python uwsgiconfig.py -p plugins/http \
    && python uwsgiconfig.py -p plugins/python \
    && mkdir -p /usr/local/lib/uwsgi \
    && cp -v /uwsgi-2.0.22/*_plugin.so /usr/local/lib/uwsgi/ \
    && pip install . \
    && cd - \
    && rm -rf /uwsgi-2.0.22

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
COPY uwsgi-manager.ini /etc/uwsgi/apps/manager.ini
RUN mkdir -p /app/.git/refs/heads \
    && mkdir -p /app/.git/objects/info \
    && echo "ref: refs/heads/main" > /app/.git/HEAD \
    && echo $GIT_REV > /app/.git/refs/heads/main
RUN /app/manager-env/bin/pip install /app

# install health-check app code (in its own env)
COPY status /app/status
RUN /app/status-env/bin/pip install -r /app/status/requirements.txt
COPY uwsgi-status.ini /etc/uwsgi/apps/status.ini

# install uwsgitop for easier monitoring
RUN /app/manager-env/bin/pip install uwsgitop

# install periodic-tasks cron job
RUN printf "SHELL=/bin/bash\n\
BASH_ENV=/container.env\n\
DJANGO_SETTINGS_MODULE=manager.settings\n\
*/5 * * * * cd /app && /app/manager-env/bin/python ./manage.py periodic_tasks >> /proc/1/fd/1 2>>/proc/1/fd/2\n\
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
ENV CARDSHOP_API_URL https://api.imager.kiwix.org
ENV CARDSHOP_API_URL_EXTERNAL https://api.imager.kiwix.org
ENV MANAGER_API_TOKEN NOT_SET
ENV ADMIN_PASSWORD admin
ENV SUPPORT_EMAIL stephane@kiwix.org
ENV DJANGO_SETTINGS_MODULE manager.settings

# for status page
ENV STATUS_S3_URL "http://org-kiwix-hotspot-cardshop-download.s3.us-west-1.wasabisys.com"
ENV STATUS_CARDSHOP_URL "https://imager.kiwix.org"
ENV STATUS_CARDSHOP_API_URL "https://api.imager.kiwix.org"
ENV USERNAME ""
ENV STATUS_MANAGER_PASSWORD ""
ENV MONGODB_URI "mongodb://mongodb"
ENV STATUS_SCHEDULER_USERNAME ""
ENV STATUS_SCHEDULER_PASSWORD ""

EXPOSE 80

ENTRYPOINT ["/manager-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
