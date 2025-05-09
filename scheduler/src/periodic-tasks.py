#!/usr/bin/env python

import datetime
import logging
import os

import humanfriendly
import requests

from emailing import send_order_failed_email
from routes.orders import create_order_from
from utils.mongo import AutoImages, Orders, Tasks
from utils.templates import (
    get_magnet_for_torrent,
    get_public_download_torrent_url,
    get_public_download_url,
)
from utils.wasabi import get_autodelete_date_for, update_autodelete_for

MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://imager.kiwix.org/api")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")
DISABLE_PERIODIC_TASKS = bool(os.getenv("DISABLE_PERIODIC_TASKS", "") == "y")
RECREATE_AUTO_MONTHLY = bool(os.getenv("RECREATE_AUTO_MONTHLY", "") == "y")
AUTO_IMAGES_EXTEND_BEFORE_DAYS = int(os.getenv("AUTO_IMAGES_EXTEND_BEFORE_DAYS") or 5)
AUTO_IMAGES_EXTEND_FOR_DAYS = int(os.getenv("AUTO_IMAGES_EXTEND_FOR_DAYS") or 10)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
        return since < now - datetime.timedelta(hours=12)

    if status == Tasks.wiping_sdcard:
        return since < now - datetime.timedelta(minutes=30)

    if status in (Tasks.uploading, Tasks.downloading, Tasks.writing):
        return since < now - datetime.timedelta(seconds=int(size / min_bps))


def run_periodic_tasks():
    logger.info("running periodic tasks !!")

    # manage auto-images
    logger.info("managing auto-images")
    check_autoimages()

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

    logger.info("removing expired donwload files")
    now = datetime.datetime.now()

    for order in Orders.all_pending_expiry():
        ls = order["statuses"][-1]

        if not ls["status"] == Orders.pending_expiry:
            continue  # wrong timing

        if not order["sd_card"]["expiration"] < now:
            continue  # expiration not reached

        logger.info("Order #{} has reach expiration.".format(order["_id"]))
        Orders().update_status(order["_id"], Orders.expired)


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
            torrent_url = get_public_download_torrent_url(order)
            AutoImages.update_status(
                image["slug"],
                status="ready",
                order=None,
                http_url=get_public_download_url(order),
                torrent_url=torrent_url,
                magnet_url=get_magnet_for_torrent(torrent_url),
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

    # find images that needs auto-delete grace
    logger.info("Looking for images needing auto-delete date bump")
    now = datetime.datetime.now()
    max_renewal_date = now + datetime.timedelta(days=AUTO_IMAGES_EXTEND_BEFORE_DAYS)
    for image in AutoImages.all_ready():
        auto_delete_on = get_autodelete_date_for(image["slug"])
        if auto_delete_on <= max_renewal_date:
            new_autodelete_on = auto_delete_on + datetime.timedelta(
                days=AUTO_IMAGES_EXTEND_FOR_DAYS
            )
            logger.info(
                f".. extending from {auto_delete_on.isoformat()} "
                f"to {new_autodelete_on.isoformat()}"
            )
            update_autodelete_for(slug=image["slug"], on=new_autodelete_on)
        else:
            logger.debug(f".. deletion scheduled for {auto_delete_on}")


if __name__ == "__main__":
    if not DISABLE_PERIODIC_TASKS:
        run_periodic_tasks()
