FROM tiangolo/uwsgi-nginx:python3.6

ENV INIT_USERNAME admin
ENV INIT_PASSWORD admin_pass
ENV SYSTEM_PASWORD system

COPY src /usr/src/flask
COPY src/entrypoint.sh /scheduler-entrypoint.sh

RUN chmod 755 /scheduler-entrypoint.sh

RUN pip install -r /usr/src/flask/requirements.txt

ENV UWSGI_INI /usr/src/flask/uwsgi.ini
WORKDIR /usr/src/flask

ENTRYPOINT ["/scheduler-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
