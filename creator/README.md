# Creator Worker

Connects to the scheduler with worker credentials and polls it frequently for creation tasks.
Tasks consists of launching kiwix-hotspot to create images and uploading them to the warehouse.

```
docker run \
    -v /Users/reg/staging:/data \
    -e USERNAME=creator1 \
    -e PASSWORD=creator1 \
    -e WORKING_DIR=/data \
    -e CARDSHOP_API_URL=http://192.168.1.103 \
    -e CARDSHOP_WAREHOUSE_URL=ftp://192.168.1.103:21 \
    creator-worker
```
