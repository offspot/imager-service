FROM python:3.7.0-slim-stretch

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
RUN echo "UTC" > /etc/timezone
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends sudo curl unzip udisks2 exfat-fuse exfat-utils xz-utils bzip2 gzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN pip3 install -U pip

# https://github.com/q3aql/aria2-static-builds/releases
RUN curl -LO https://github.com/q3aql/aria2-static-builds/releases/download/v1.34.0/aria2-1.34.0-linux-gnu-64bit-build1.tar.bz2
RUN tar xf aria2-1.34.0-linux-gnu-64bit-build1.tar.bz2 && mv aria2-1.34.0-linux-gnu-64bit-build1/aria2c /usr/bin/aria2c
RUN rm -rf aria2-1.34.0-linux-gnu-64bit-build1 aria2-1.34.0-linux-gnu-64bit-build1.tar.bz2

# kiwix-hotspot
RUN curl -LO http://mirror.download.kiwix.org/release/kiwix-hotspot/v2.2.1/kiwix-hotspot-linux.tar.gz
RUN tar xf kiwix-hotspot-linux.tar.gz && mv kiwix-hotspot /usr/bin/kiwix-hotspot
RUN rm -f kiwix-hotspot-linux.tar.gz

# etcher-cli (abandonned in 1.5.0+)
RUN curl -LO https://github.com/balena-io/etcher/releases/download/v1.4.9/balena-etcher-cli-1.4.9-linux-x64.tar.gz
RUN tar xf balena-etcher-cli-1.4.9-linux-x64.tar.gz && mv balena-etcher-cli-1.4.9-linux-x64-dist /usr/local/etcher

RUN echo "--- dependencies version:"
RUN /usr/bin/curl --version
RUN /usr/bin/aria2c --version
RUN /usr/bin/kiwix-hotspot --version
RUN /usr/local/etcher/balena-etcher --version
RUN echo "------"

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
