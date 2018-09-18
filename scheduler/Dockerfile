FROM python:3.7.0-stretch

RUN apt-get update && \
    apt-get upgrade -y && \
   rm -rf /var/lib/apt/lists/*

RUN pip3 install -U pip setuptools
RUN pip3 install uwsgi

COPY src /usr/src/flask
COPY src/entrypoint.sh /entrypoint.sh

RUN chmod 755 /entrypoint.sh
RUN pip install -r /usr/src/flask/requirements.txt

WORKDIR /usr/src/flask
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/local/bin/uwsgi", "--ini", "/usr/src/flask/uwsgi.ini"]
