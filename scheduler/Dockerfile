FROM tiangolo/uwsgi-nginx:python3.6

ENV INIT_USERNAME admin
ENV INIT_PASSWORD admin_pass
ENV SYSTEM_PASWORD system

RUN rm -rf /app
COPY src /app
COPY src/entrypoint.sh /scheduler-entrypoint.sh

RUN chmod 755 /scheduler-entrypoint.sh

RUN pip install -r /app/requirements.txt

ENV UWSGI_INI /app/uwsgi.ini
WORKDIR /app

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/scheduler-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
