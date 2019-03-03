#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import datetime
import subprocess

import humanfriendly

from emailing import send_order_failed_email
from utils.mongo import Orders, Tasks, Users, AccessToken

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def is_expired(status, since, size=0):
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
    user = Users().get_manager()
    access_token = AccessToken.encode(user)

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
        "{user}:{passwd}".format(user=user["username"], passwd=access_token),
        upload_uri,
        "-Q",
        "-DELE {}".format(image_fname),
    ]

    return subprocess.run(args).returncode == 0


def run_periodic_tasks():
    logger.info("running periodic tasks !!")

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

        logger.info("Order #{} has reach expiration; deleting file")
        order_fname = "{}.img".format(order["_id"])

        # actually delete file
        if remove_image(order_fname, order["warehouse"]["upload_uri"]):
            # update order (all done)
            order.update_status(order["_id"], Orders.expired)
        else:
            logger.error("Failed to remove expired file {}".format(order_fname))


if __name__ == "__main__":
    run_periodic_tasks()
