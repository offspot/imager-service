FROM python:3.7.0-slim-stretch

LABEL maintainer=rgaudin

RUN mkdir -p /data
VOLUME /data
ENV DATA_DIR /data

RUN apt-get update && \
    apt-get upgrade -y && \ 	
    apt-get install -y \
    libmagic1 \
	nginx-full \
	build-essential \
	sqlite3 && \
   rm -rf /var/lib/apt/lists/*

RUN pip3 install -U pip setuptools

# install uwsgi early as it takes time (package version not OK)
RUN pip3 install uwsgi

COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

# copy configuration files
COPY deploy/nginx.conf /etc/nginx/sites-available/default
COPY deploy/uwsgi_params /app/
COPY deploy/uwsgi.ini /app/
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# copy app code
COPY manage.py /app/manage.py
COPY manager /app/manager
COPY contents.json /app/contents.json

# start nginx so it sets up www-data
RUN /usr/sbin/nginx

WORKDIR /app/

EXPOSE 80 443
ENTRYPOINT ["/entrypoint.sh"]

CMD ["/usr/local/bin/uwsgi", "--ini", "/app/uwsgi.ini"]
