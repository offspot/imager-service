FROM tiangolo/uwsgi-nginx:python3.8

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y && \
    apt-get -y --no-install-recommends install cron && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
ENV DATA_DIR /data
ENV CARDSHOP_API_URL https://api.cardshop.hotspot.kiwix.org
ENV MANAGER_API_TOKEN NOT_SET
ENV ADMIN_PASSWORD admin
ENV SUPPORT_EMAIL stephane@kiwix.org

VOLUME /data

# update pip
RUN pip install -U pip setuptools virtualenv

COPY nginx.conf /etc/nginx/conf.d/

# copy app code
RUN rm -rf /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY manage.py /app/manage.py
COPY manager /app/manager
COPY contents.json /app/contents.json
COPY uwsgi-manager.ini /etc/uwsgi/manager.ini

# for status page
ENV STATUS_S3_URL "http://org-kiwix-hotspot-cardshop-download.s3.us-west-1.wasabisys.com"
ENV STATUS_CARDSHOP_URL "https://cardshop.hotspot.kiwix.org"
ENV STATUS_CARDSHOP_API_URL "https://api.cardshop.hotspot.kiwix.org"
ENV USERNAME ""
ENV STATUS_MANAGER_PASSWORD ""
ENV MONGODB_URI "mongodb://mongodb"
ENV STATUS_SCHEDULER_USERNAME ""
ENV STATUS_SCHEDULER_PASSWORD ""

COPY status /app/status
RUN virtualenv -p python3 /app/status-env
RUN /app/status-env/bin/pip install -r /app/status/requirements.txt
COPY uwsgi-status.ini /etc/uwsgi/uwsgi-status.ini

# replace line in supervisor to enable emperor mode
RUN sed -i "s/uwsgi --ini \/etc\/uwsgi\/uwsgi.ini/uwsgi --emperor \/etc\/uwsgi/g" /etc/supervisor/conf.d/supervisord.conf
# add route in uwsgi to enable status page
RUN printf "\nroute-uri = ^/health-check(/?)$ uwsgi:/tmp/uwsgi-status.sock,0,0" >> /etc/uwsgi/uwsgi.ini

ENV UWSGI_INI /etc/uwsgi/manager.ini
COPY entrypoint.sh /manager-entrypoint.sh
RUN chmod 755 /manager-entrypoint.sh
WORKDIR /app
RUN printf "SHELL=/bin/bash\nBASH_ENV=/container.env\nDJANGO_SETTINGS_MODULE=manager.settings\n*/5 * * * * cd /app && /usr/local/bin/python ./manage.py periodic-tasks >> /proc/1/fd/1 2>>/proc/1/fd/2\n" > /etc/cron.d/manager-cron
RUN chmod 0644 /etc/cron.d/manager-cron
RUN crontab /etc/cron.d/manager-cron

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/manager-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
