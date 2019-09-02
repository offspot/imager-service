FROM tiangolo/uwsgi-nginx:python3.7

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends cron curl xfonts-75dpi xfonts-base && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN curl -O -L https://downloads.wkhtmltopdf.org/0.12/0.12.5/wkhtmltox_0.12.5-1.stretch_amd64.deb && \
    apt-get install -y --no-install-recommends ./wkhtmltox_0.12.5-1.stretch_amd64.deb && \
    rm ./wkhtmltox_0.12.5-1.stretch_amd64.deb
RUN wkhtmltopdf --version

ENV MONGODB_URI mongo
ENV MANAGER_ACCOUNT_PASSWORD manager
ENV PUBLIC_URL https://cardshop.hotspot.kiwix.org
ENV SMTP_USERNAME SMTP_USERNAME
ENV SMTP_PASSWORD SMTP_PASSWORD
ENV SMTP_HOST smtp.gmail.com
ENV SMTP_ENCTYPE auto  # auto,tls,ssl,none (defaults to tls)
ENV SMTP_PORT auto # based on enctype or set for local debug
ENV SMTP_SKIP_LOGIN 0  # for local debug
ENV SUPPORT_EMAIL stephane@kiwix.org

RUN rm -rf /app
COPY src /app
COPY src/entrypoint.sh /scheduler-entrypoint.sh

RUN chmod 755 /scheduler-entrypoint.sh

RUN pip install -r /app/requirements.txt

ENV UWSGI_INI /app/uwsgi.ini
WORKDIR /app

RUN touch /container.env
COPY crontab /etc/cron.d/scheduler-cron
RUN chmod 0644 /etc/cron.d/scheduler-cron
RUN crontab /etc/cron.d/scheduler-cron

RUN rm -rf /lib/systemd/system/supervisor.service
RUN update-rc.d -f supervisor remove
RUN rm -f /etc/init.d/supervisor

ENTRYPOINT ["/scheduler-entrypoint.sh"]
EXPOSE 80 443
CMD ["/usr/bin/supervisord"]
