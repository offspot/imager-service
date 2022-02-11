#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import logging
import datetime
import subprocess

import requests
import humanfriendly

from emailing import send_order_failed_email
from utils.mongo import Orders, Tasks, AutoImages
from utils.templates import (
    get_public_download_url,
    get_public_download_torrent_url,
    get_magnet_for_torrent,
)
from routes.orders import create_order_from

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_next_month():
    """ get next month's 1st day at 08:00 """
    start_of_month = datetime.date(*datetime.date.today().timetuple()[:2], 1)
    return datetime.datetime(
        *(start_of_month + datetime.timedelta(days=31)).timetuple()[:2], 1, 8, 0
    )


def is_expired(status, since, size="0"):
    now = datetime.datetime.now()
    min_bps = int(humanfriendly.parse_size("4MiB") / 8)

    if status == Tasks.building:
        return since < now - datetime.timedelta(hours=12)

    if status == Tasks.wiping_sdcard:
        return since < now - datetime.timedelta(minutes=30)

    if status in (Tasks.uploading, Tasks.downloading, Tasks.writing):
        size = humanfriendly.parse_size(size)
        return since < now - datetime.timedelta(seconds=int(size / min_bps))


def remove_image(image_fname, upload_uri):

    # use manager credentials to be able to delete files over FTP
    username = "manager"
    req = requests.post(
        url="{api_url}/auth/authorize".format(
            api_url=os.getenv("CARDSHOP_API_INTERNAL_URL")
        ),
        headers={
            "username": "manager",
            "password": os.getenv("MANAGER_API_KEY"),
            "Content-type": "application/json",
        },
    )
    try:
        req.raise_for_status()
    except Exception:
        return False
    access_token = req.json().get("access_token")

    args = [
        "/usr/bin/curl",
        "--connect-timeout",
        "60",
        "--insecure",
        "--ipv4",
        "--retry-connrefused",
        "--retry-delay",
        "60",
        "--retry",
        "20",
        "--stderr",
        "-",
        "--user",
        "{user}:{passwd}".format(user=username, passwd=access_token),
        upload_uri,
        "-Q",
        "-DELE {}".format(image_fname),
    ]

    return subprocess.run(args).returncode == 0


def run_periodic_tasks():
    logger.info("running periodic tasks !!")

    # manage auto-images
    logger.info("managing auto-images")
    check_autoimages()

    # timeout orders based on status

    # orders cant stay in creation for more than 12h
    # orders in downloading/writing cant be slower than 4Mb/s
    # now = datetime.datetime.now()
    # min_bps = int(humanfriendly.parse_size("4MiB") / 8)

    # for morder in Orders().find(
    #     {"status": {"$in": [Orders().creating, Orders.downloading, Orders.writing]}},
    #     {"_id": 1},
    # ):
    #     order = Orders().get_with_tasks(morder["_id"])
    #     ls = order["statuses"][-1]

    #     # prepare expired dt based on status
    #     if ls["status"] == Orders().creating:
    #         task = CreatorTasks().get(order["tasks"]["create"])
    #     elif ls["status"] in (Orders.downloading, Orders.writing):
    #         size = humanfriendly.parse_size(order["config"]["size"])
    #         expired = now - datetime.timedelta(seconds=int(size / min_bps))
    #         if ls["status"] == Orders.downloading:
    #             task_cls, task_id = DownloaderTasks, order["tasks"]["download"]
    #         else:
    #             task_cls, task_id = WriterTasks, order["tasks"]["write"]
    #     else:
    #         # last status not in-progress
    #         continue

    #     # compare last update with expiry datetime
    #     if ls["on"] > expired:
    #         continue

    #     # timeout task
    #     task_cls().update_status(task_id=task_id, status=task_cls.timedout)

    #     # timeout order
    #     task_cls().cascade_status(task_id=task_id, status=task_cls.timedout)

    #     # notify failure
    #     send_order_failed_email(order["_id"])  # TODO: forward to task/order mgmt

    logger.info("timing out expired orders")
    for task in Tasks.all_inprogress():
        task_id = task["_id"]
        ls = task["statuses"][-1]

        if not is_expired(ls["status"], ls["on"]):
            logger.info("skipping non-expired task #{}".format(task_id))
            continue

        logger.info("timing out task #{}".format(task_id))

        order = Orders().get_with_tasks(task["order"])

        # timeout task
        task.update_status(task_id=task_id, status=Tasks.timedout)

        # if write, cancel peers
        if ls["status"] in (Tasks.wiping_sdcard, Tasks.writing):
            for peer in order["tasks"]["write"]:
                if peer["_id"] == task_id:
                    continue
                task.update_status(task_id=peer["_id"], status=Tasks.canceled)

        # cascade
        task.cascade_status(task_id=task_id, status=task.timedout)

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

        # logger.info(
        #     "Order #{} has reach expiration. deleting file".format(order["_id"])
        # )
        # order_fname = "{}.img".format(order["_id"])

        # # actually delete file
        # if remove_image(order_fname, order["warehouse"]["upload_uri"]):
        #     # update order (all done)
        #     Orders().update_status(order["_id"], Orders.expired)
        # else:
        #     logger.error("Failed to remove expired file {}".format(order_fname))


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
                expire_on=get_next_month(),
            )
            continue

        logger.info(f".. order still building: {order['status']}")

    # find images that must be recreated
    logger.info("Looking for images needing building…")
    for image in AutoImages.all_needing_rebuild():
        logger.info(f".. {image['slug']} ; starting build")

        # create order
        payload = AutoImages.create_order_payload(image["slug"])
        try:
            order_id = create_order_from(payload)
        except Exception as exc:
            logger.error(f"Error creating image `{image['slug']}`: {exc}")
            logger.exception(exc)
            AutoImages.update_status(image["slug"], status="failed")
            continue

        # update with order ID and status: building
        AutoImages.update_status(image["slug"], status="building", order=order_id)


if __name__ == "__main__":
    run_periodic_tasks()
