FROM tiangolo/uwsgi-nginx:python3.7

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
RUN pip install -U pip setuptools

COPY nginx.conf /etc/nginx/conf.d/

# copy app code
RUN rm -rf /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY manage.py /app/manage.py
COPY manager /app/manager
COPY contents.json /app/contents.json

COPY uwsgi.ini /app/uwsgi.ini
COPY entrypoint.sh /manager-entrypoint.sh
RUN chmod 755 /manager-entrypoint.sh

ENV UWSGI_INI /app/uwsgi.ini
WORKDIR /app

RUN echo "* * * * */5 /usr/local/bin/python /app/manage.py periodic-tasks > /proc/1/fd/1 2>/proc/1/fd/2\n" > /etc/cron.d/manager-cron
RUN chmod 0644 /etc/cron.d/manager-cron
RUN crontab /etc/cron.d/manager-cron

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/manager-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
