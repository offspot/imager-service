FROM tiangolo/uwsgi-nginx:python3.6

COPY src /usr/src/flask
COPY src/entrypoint.sh /scheduler-entrypoint.sh

RUN chmod 755 /scheduler-entrypoint.sh

RUN pip install -r /usr/src/flask/requirements.txt

ENV UWSGI_INI /usr/src/flask/uwsgi.ini
WORKDIR /usr/src/flask

ENTRYPOINT ["/scheduler-entrypoint.sh"]
CMD ["/usr/bin/supervisord"]
