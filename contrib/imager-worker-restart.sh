#!/bin/bash

# imager worker start/restart script
# stop worker with docker stop imager-worker

USERNAME="worker"
PASSWORD="notset"
CONTAINER="imager-worker"
IMAGE="ghcr.io/offspot/imager-worker:imager"
S3_ACCESS_KEY="notset"
S3_SECRET_KEY="notset"

if [ -f /etc/imager.config ]; then
    source /etc/imager.config
fi

# already running?
docker ps |grep $CONTAINER |awk '{print $1}' | while read line ; do
    echo ">stopping worker container $line"
    docker stop $line
    echo ">removing worker container $line"
    docker rm $line
done

docker stop $CONTAINER
docker rm $CONTAINER

echo ">pulling image $IMAGE…"
docker pull $IMAGE

echo ">starting creator worker"
docker run \
    --name $CONTAINER \
    -v /data/imager:/data \
    -v /data/cache:/cache \
    -e USERNAME="$USERNAME" \
    -e PASSWORD="$PASSWORD" \
    -e S3_ACCESS_KEY="$S3_ACCESS_KEY" \
    -e S3_SECRET_KEY="$S3_SECRET_KEY" \
    -e CARDSHOP_API_URL="https://api.imager.kiwix.org" \
    --privileged \
    --restart unless-stopped \
    --detach \
    $IMAGE
