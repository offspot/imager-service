FROM tiangolo/uwsgi-nginx:python3.6

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

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/manager-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
