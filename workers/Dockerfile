FROM python:3.7.0-slim-stretch

RUN ln -s /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update && apt-get install -y curl unzip udisks2 exfat-fuse exfat-utils xz-utils bzip2 gzip
RUN pip3 install -U pip

COPY assets/aria2c_linux-static_v1.34.0 /usr/bin/aria2c
COPY assets/kiwix-hotspot_linux-static_v2.0.3 /usr/bin/kiwix-hotspot
COPY assets/etcher_linux-static_v1.4.8.zip /usr/local
RUN cd /usr/local/ && unzip etcher_linux-static_v1.4.8 && cd -

VOLUME /data
ENV WORKING_DIR "/data"
ENV CARDSHOP_API_URL "https://api.cardshop.hotspot.kiwix.org"
ENV USERNAME ""
ENV PASSWORD ""

ENV INSTALLER_BIN_PATH "/usr/bin/kiwix-hotspot"
ENV ARIA2_BIN_PATH "/usr/bin/aria2c"
ENV CURL_BIN_PATH "/usr/bin/curl"
ENV ETCHER_BIN_PATH "/usr/local/etcher/balena-etcher"

ENV USB_SLOT=""
ENV USB_PATH=""

ENV WORKER_TYPE="unknown"

COPY requirements.txt /usr/src/
RUN pip3 install -r /usr/src/requirements.txt

RUN mkdir -p $WORKING_DIR
COPY worker /usr/src/worker
WORKDIR /usr/src/

ENTRYPOINT ["python", "worker"]
