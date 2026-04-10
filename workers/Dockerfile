FROM docker.io/library/python:3.14-slim-trixie
LABEL org.opencontainers.image.source=https://github.com/offspot/imager-service

VOLUME /data
VOLUME /cache
ENV WORKING_DIR "/data"
ENV CACHE_DIR "/cache"
ENV CARDSHOP_API_URL "https://api.imager.kiwix.org"
ENV USERNAME ""
ENV PASSWORD ""
ENV IMAGER_BIN_PATH "/usr/local/bin/image-creator"
ENV CURL_BIN_PATH "/usr/bin/curl"
ENV PRIVATE_SSH_KEY_PATH "/etc/ssh/imager-worker"
ENV HOST_KNOW_FILE=/etc/ssh/known_hosts
ENV MARKER_FILE=/usr/share/marker
ENV SCP_BIN_PATH=/usr/bin/scp
ENV SFTP_BIN_PATH=/usr/bin/sftp

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && apt-get update -y \
    && apt-get install -y --no-install-recommends \
        curl \
        openssh-client \
        coreutils util-linux dmsetup \
        mount fdisk e2fsprogs qemu-utils parted \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p $WORKING_DIR $CACHE_DIR \
    && printf "enabled: false\noci_images:\n  enabled: false\nfiles:\n  enabled: false\n" > /cache/policy.yaml \
    && pip3 install -U pip \
    # image-creator
    && curl -L -o /usr/local/bin/image-creator_1.1.5 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_1.1.5 \
    && chmod +x /usr/local/bin/image-creator_1.1.5 \
    #&& echo "--- dependencies version: " && image-creator_1.1.5 --version \
    # set default
    && ln -s /usr/local/bin/image-creator_1.1.5 /usr/local/bin/image-creator \
    && touch $MARKER_FILE

COPY requirements.txt /src/
RUN pip install -r /src/requirements.txt
COPY worker /src/worker
WORKDIR /src/

ENTRYPOINT ["python", "worker"]
