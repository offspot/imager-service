#!/usr/bin/env python

import datetime
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

import humanfriendly
import requests
from emailing import send_order_failed_email
from routes.orders import create_order_from
from utils.files import FileChecker
from utils.mongo import AutoImages, Orders, Tasks, UploadedFiles
from utils.templates import (
    get_public_download_torrent_urls,
    get_public_download_urls,
)
from woocommerce import API

MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://imager.kiwix.org/api")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")
DISABLE_PERIODIC_TASKS = bool(os.getenv("DISABLE_PERIODIC_TASKS", "") == "y")
RECREATE_AUTO_MONTHLY = bool(os.getenv("RECREATE_AUTO_MONTHLY", "") == "y")
SHOP_WOO_API_URL = os.getenv("SHOP_WOO_API_URL", "https://get.kiwix.org/")
SHOP_WOO_CONSUMER_KEY = os.getenv("SHOP_WOO_CONSUMER_KEY", "not-set")
SHOP_WOO_CONSUMER_SECRET = os.getenv("SHOP_WOO_CONSUMER_SECRET", "not-set")
LAST_CHECKED_UPLOADED_ON = datetime.datetime.now() - datetime.timedelta(
    days=2
)  # in past
LAST_EXTENDED_EXPIRATIONS_ON = datetime.datetime.now() - datetime.timedelta(
    days=2
)  # in past


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_wc_api():
    return API(
        url=SHOP_WOO_API_URL,
        consumer_key=SHOP_WOO_CONSUMER_KEY,
        consumer_secret=SHOP_WOO_CONSUMER_SECRET,
        version="wc/v3",
    )


def get_next_month():
    """get next month's 1st day at 08:00"""
    start_of_month = datetime.date(*datetime.date.today().timetuple()[:2], 1)
    return datetime.datetime(
        *(start_of_month + datetime.timedelta(days=31)).timetuple()[:2], 1, 8, 0
    )


def is_expired(status, since, size=0):
    now = datetime.datetime.now()
    min_bps = int(humanfriendly.parse_size("4MiB") / 8)

    if status == Tasks.building:
        return since < now - datetime.timedelta(hours=36)

    if status == Tasks.wiping_sdcard:
        return since < now - datetime.timedelta(minutes=30)

    if status in (Tasks.uploading, Tasks.downloading, Tasks.writing):
        return since < now - datetime.timedelta(seconds=int(size / min_bps))


def run_periodic_tasks():
    logger.info("running periodic tasks !!")

    # manage auto-images
    logger.info("managing auto-images")
    check_autoimages()

    extend_autoimages_expiration()

    delete_expired_files()

    logger.info("timing out expired orders")
    for task_cls, task in Tasks.all_inprogress():
        task_id = task["_id"]
        ls = task["statuses"][-1]

        if not is_expired(ls["status"], ls["on"], task_cls.get_size(task_id)):
            logger.info("skipping non-expired task #{}".format(task_id))
            continue

        logger.info("timing out task #{}".format(task_id))

        order = Orders().get_with_tasks(task["order"])

        # timeout task
        task_cls.update_status(task_id=task_id, status=Tasks.timedout)

        # if write, cancel peers
        if ls["status"] in (Tasks.wiping_sdcard, Tasks.writing):
            for peer in order["tasks"]["write"]:
                if peer["_id"] == task_id:
                    continue
                task_cls.update_status(task_id=peer["_id"], status=Tasks.canceled)

        # cascade
        task_cls.cascade_status(task_id=task_id, task_status=task_cls.timedout)

        # notify
        send_order_failed_email(order["_id"])  # TODO: forward to task/order mgmt

    logger.info("Marking orders as expired")
    now = datetime.datetime.now()

    for order in Orders.all_pending_expiry():
        ls = order["statuses"][-1]

        if not ls["status"] == Orders.pending_expiry:
            continue  # wrong timing

        if not order["sd_card"]["expiration"] < now:
            continue  # expiration not reached

        logger.info("Order #{} has reach expiration.".format(order["_id"]))
        Orders().update_status(order["_id"], Orders.expired)


def set_product_download_urls(product_id: int, downloads):
    wc_api = get_wc_api()
    resp = wc_api.put(f"products/{product_id}", data={"downloads": downloads})
    resp.raise_for_status()


def check_autoimages():
    # update images that were building
    logger.info("Looking for currently building images…")
    for image in AutoImages.all_currently_building():
        logger.info(f".. {image['slug']}")
        # check order status
        order = Orders.get(image["order"])

        # order is considered failed
        if order["status"] in Orders.FAILED_STATUSES:
            logger.info(f".. order failed: {order['status']}")
            AutoImages.update_status(image["slug"], status="failed")
            continue

        # order is considered successful
        if order["status"] in Orders.SUCCESS_STATUSES + [Orders.pending_expiry]:
            logger.info(f".. order succeeded: {order['status']}")
            torrent_urls = get_public_download_torrent_urls(order)
            http_urls = get_public_download_urls(order)

            # not all images are product on the shop
            if image.get("woo_id"):
                downloads = []
                for index, http_url in enumerate(http_urls):
                    downloads.append(
                        {
                            "id": f"http_url{index}",
                            "name": Path(urlsplit(http_url).path).name,
                            "file": http_url,
                        }
                    )

                for index, torrent_url in enumerate(torrent_urls):
                    downloads.append(
                        {
                            "id": f"torrent_url{index}",
                            "name": Path(urlsplit(torrent_url).path).name,
                            "file": torrent_url,
                        }
                    )

                if not downloads:
                    logger.error(f".. No download URLs for product={image['woo_id']}")
                    continue

                set_product_download_urls(
                    product_id=image["woo_id"], downloads=downloads
                )

            AutoImages.update_status(
                image["slug"],
                status="ready",
                order=None,
                http_url=http_urls[0],
                torrent_url=torrent_urls[0],
                http_urls=http_urls,
                torrent_urls=torrent_urls,
                expire_on=get_next_month() if RECREATE_AUTO_MONTHLY else None,
            )

            continue

        logger.info(f".. order still building: {order['status']}")

    # find images that must be recreated
    logger.info("Looking for images needing building…")
    for image in AutoImages.all_needing_rebuild():
        logger.info(f".. {image['slug']} ; starting build")

        payload = AutoImages.create_order_payload(image["slug"])
        try:
            # retrieve up-to-date YAML from stored JSON config
            resp = requests.post(
                f"{MANAGER_API_URL}/json-to-yaml",
                headers={"Token": MANAGER_ACCOUNTS_API_TOKEN},
                json=payload["config"],
            )
            resp.raise_for_status()
            payload["config_yaml"] = resp.text

            # create order
            order_id = create_order_from(payload)
        except Exception as exc:
            logger.error(f"Error creating image `{image['slug']}`: {exc}")
            logger.exception(exc)
            AutoImages.update_status(image["slug"], status="failed")
            continue

        # update with order ID and status: building
        AutoImages.update_status(image["slug"], status="building", order=order_id)


def extend_autoimages_expiration():
    # extended file expiration for images needing it
    now = datetime.datetime.now()
    if now < LAST_EXTENDED_EXPIRATIONS_ON + datetime.timedelta(days=1):
        logger.debug(
            f"Not extending uploaded files expiration ({LAST_EXTENDED_EXPIRATIONS_ON.isoformat()})"
        )
        return

    logger.info("Looking for files needing an expiration bump…")

    for image in AutoImages.all_ready():
        logger.info(f"> {image['slug']}")
        for file in AutoImages.get_uploaded_files(image["slug"]):
            fc = FileChecker(file)
            if fc.extend_if_expiring_soon():
                logger.info(
                    f".. extended by {fc.extend_for_days} days "
                    f"from {fc.next_expiration_on.isoformat()} "
                    f"to {fc.next_expiration_on.isoformat()}"
                )
            else:
                logger.debug(f".. deletion scheduled for {fc.expire_on.isoformat()}")


def delete_expired_files():
    now = datetime.datetime.now()
    if now < LAST_CHECKED_UPLOADED_ON + datetime.timedelta(days=1):
        logger.debug(
            f"Not checking uploaded files ({LAST_CHECKED_UPLOADED_ON.isoformat()})"
        )
        return
    logger.info("Checking Uploaded files…")

    # remove entries that have been pending for a week
    a_week_ago = now - datetime.timedelta(days=7)
    for file in UploadedFiles().find(
        {"status": "pending", "created_on": {"$lte": a_week_ago}}
    ):
        logger.info(f"Removing pending state {file['_id']!s}")
        FileChecker(file).remove_anyway()

    for file in UploadedFiles().find({"status": "confirmed"}):
        if FileChecker(file).remove_if_expired():
            logger.info(f"Removed expired file {file['_id']!s}")


if __name__ == "__main__":
    if not DISABLE_PERIODIC_TASKS:
        run_periodic_tasks()
