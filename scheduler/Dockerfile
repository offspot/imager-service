FROM tiangolo/uwsgi-nginx:python3.7

RUN apt-get update && apt-get install -y wkhtmltopdf

ENV MONGODB_URI mongo
ENV MANAGER_ACCOUNT_PASSWORD manager
ENV PUBLIC_URL https://cardshop.hotspot.kiwix.org
ENV SMTP_USERNAME SMTP_USERNAME
ENV SMTP_PASSWORD SMTP_PASSWORD
ENV SMTP_HOST smtp.gmail.com
ENV SMTP_ENCTYPE auto  # auto,tls,ssl,none (defaults to tls)
ENV SMTP_PORT auto # based on enctype or set for local debug
ENV SMTP_SKIP_LOGIN 0  # for local debug

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
