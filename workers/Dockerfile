FROM python:3.11-slim-bookworm
LABEL org.opencontainers.image.source https://github.com/offspot/imager-service

VOLUME /data
VOLUME /cache
ENV WORKING_DIR "/data"
ENV CACHE_DIR "/cache"
ENV CARDSHOP_API_URL "https://api.imager.kiwix.org"
ENV USERNAME ""
ENV PASSWORD ""
ENV IMAGER_BIN_PATH "/usr/local/bin/image-creator"
ENV CURL_BIN_PATH "/usr/bin/curl"

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && apt-get update -y \
    && apt-get install -y --no-install-recommends \
        curl \
        coreutils util-linux dmsetup \
        mount fdisk e2fsprogs qemu-utils parted \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p $WORKING_DIR $CACHE_DIR \
    && printf "enabled: false\noci_images:\n  enabled: false\nfiles:\n  enabled: false\n" > /cache/policy.yaml \
    && pip3 install -U pip \
    # image-creator
    && curl -L -o /usr/local/bin/image-creator_0.9.7 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_0.9.7 \
    && chmod +x /usr/local/bin/image-creator_0.9.7 \
    && ln -s /usr/local/bin/image-creator_0.9.7 //usr/local/bin/image-creator \
    && echo "--- dependencies version: " && image-creator --version \
    # beta version
    && curl -L -o /usr/local/bin/image-creator_1.0.0 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_1.0.0 \
    && chmod +x /usr/local/bin/image-creator_1.0.0 \
    && echo "--- beta version: " && image-creator_1.0.0 --version \
    && curl -L -o /usr/local/bin/image-creator_1.0.1 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_1.0.1 \
    && chmod +x /usr/local/bin/image-creator_1.0.1 \
    && echo "--- beta version: " && image-creator_1.0.1 --version \
    && curl -L -o /usr/local/bin/image-creator_1.0.2 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_1.0.2 \
    && chmod +x /usr/local/bin/image-creator_1.0.2 \
    && echo "--- beta version: " && image-creator_1.0.2 --version \
    && curl -L -o /usr/local/bin/image-creator_1.1.0 https://drive.offspot.it/image-creator/image-creator_linux-x86_64_1.1.0 \
    && chmod +x /usr/local/bin/image-creator_1.1.0 \
    && echo "--- beta version: " && image-creator_1.1.0 --version

COPY requirements.txt /src/
RUN pip install -r /src/requirements.txt
COPY worker /src/worker
WORKDIR /src/

ENTRYPOINT ["python", "worker"]
