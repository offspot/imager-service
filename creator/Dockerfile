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
# RUN tar xf kiwix-hotspot-linux.tar.gz && mv kiwix-hotspot /usr/bin/kiwix-hotspot && rm kiwix-hotspot-linux.tar.gz

ENTRYPOINT ["python", "creator"]
