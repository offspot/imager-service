FROM python:3.7.0-slim-stretch

VOLUME /data
ENV USERNAME ""
ENV PASSWORD ""
ENV WORKING_DIR "/data"
ENV INSTALLER_BIN_PATH "/usr/bin/kiwix-hotspot"
ENV CARDSHOP_API_URL "https://api.cardshop.hotspot.kiwix.org"

RUN mkdir -p $WORKING_DIR
COPY . /usr/src/worker
WORKDIR /usr/src/worker
RUN pip3 install -U pip
RUN pip3 install -r ./requirements.txt
RUN wget -c http://mirror.download.kiwix.org/release/kiwix-hotspot/v2.0-rc18/kiwix-hotspot-linux.tar.gz
RUN tar xf kiwix-hotspot-linux.tar.gz
RUN mv kiwix-hotspot /usr/bin/kiwix-hotspot
RUN rm kiwix-hotspot-linux.tar.gz

ENTRYPOINT ["python", "creator"]
