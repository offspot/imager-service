#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import time
import asyncio
import datetime

import pymongo
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request

loop = asyncio.get_event_loop()
app = Flask(__name__)

HTTP_TIMEOUT = 5  # seconds
WASABI_HTTP_TIMEOUT = HTTP_TIMEOUT * 5  # seconds


@app.template_filter("status_text")
def status_text(value):
    return "Operational" if value else "Failure"


@app.template_filter("status_class")
def status_class(value):
    return "text-success" if value else "text-danger"


@app.route(r"/", methods=["GET"])
@app.route(r"/<path>", methods=["GET"])
def status(path=""):
    if request.args.get("timeout", ""):
        try:
            timeout = int(request.args.get("timeout"))
        except Exception:
            timeout = HTTP_TIMEOUT
        time.sleep(timeout)
        return jsonify({"timeout": timeout})

    context = loop.run_until_complete(collect_statuses())
    return (
        render_template("status.html", **context),
        200 if context["global_status"] else 503,
    )


async def collect_statuses():
    """ gather all status checks in a single dict """
    scheduler_token = get_scheduler_token()
    scheduler_workers_list = get_scheduler_workers_list(scheduler_token)
    loop = asyncio.get_event_loop()
    context = {}

    def wrap(key, func, *args):
        return {key: func(*args)}

    futures = [
        loop.run_in_executor(
            None,
            wrap,
            "scheduler_status",
            get_scheduler_status,
            scheduler_workers_list,
        ),
        loop.run_in_executor(
            None,
            wrap,
            "worker_status",
            get_worker_status,
            scheduler_workers_list,
        ),
        loop.run_in_executor(None, wrap, "manager_status", get_manager_status),
        loop.run_in_executor(None, wrap, "database_status", get_database_status),
        loop.run_in_executor(None, wrap, "images_status", get_images_status),
        loop.run_in_executor(None, wrap, "wasabi_status", get_wasabi_status),
        loop.run_in_executor(
            None, wrap, "creatorload_status", get_creatorload_status, scheduler_token
        ),
    ]

    for response in await asyncio.gather(*futures):
        context.update(response)

    context.update({"global_status": all(context.values())})
    return context


def collect_statuses_sequential():
    scheduler_token = get_scheduler_token()
    scheduler_workers_list = get_scheduler_workers_list(scheduler_token)
    scheduler_status = get_scheduler_status(scheduler_workers_list)
    worker_status = get_worker_status(scheduler_workers_list)
    manager_status = get_manager_status()
    database_status = get_database_status()
    images_status = get_images_status()
    wasabi_status = get_wasabi_status()
    creatorload_status = get_creatorload_status(scheduler_token)
    global_status = all(
        [
            scheduler_status,
            worker_status,
            manager_status,
            database_status,
            images_status,
            wasabi_status,
            creatorload_status,
        ]
    )
    return {
        "scheduler_status": scheduler_status,
        "worker_status": worker_status,
        "manager_status": manager_status,
        "database_status": database_status,
        "images_status": images_status,
        "wasabi_status": wasabi_status,
        "creatorload_status": creatorload_status,
        "global_status": global_status,
    }


def _get_scheduler_token(url, username, password):
    req = requests.post(
        url=f"{url}/auth/authorize",
        headers={
            "username": username,
            "password": password,
            "Content-type": "application/json",
        },
        timeout=HTTP_TIMEOUT,
    )
    req.raise_for_status()
    return req.json().get("access_token"), req.json().get("refresh_token")


def get_scheduler_token():
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")
    # authenticate over scheduler
    try:
        access_token, _ = _get_scheduler_token(
            url,
            os.getenv("STATUS_SCHEDULER_USERNAME", ""),
            os.getenv("STATUS_SCHEDULER_PASSWORD", ""),
        )
    except Exception as exc:
        print(f"Unable to get scheduler token: {exc}")
        return None
    return access_token


def get_scheduler_workers_list(access_token):
    """ Retrieve workers list from scheduler API to test scheduler and workers """

    # fetch our urls
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")

    try:
        resp = requests.get(
            f"{url}/workers/",
            headers={
                "token": access_token,
                "Content-type": "application/json",
            },
            timeout=HTTP_TIMEOUT,
        )
        return resp.json().get("items")
    except Exception as exc:
        print(f"Unable to get workers list: {exc}")
        return None


def get_scheduler_status(workers_list):
    """ Verify that we can connect to and retrieve data from scheduler API """
    if not workers_list:
        return False
    try:
        return isinstance(workers_list, list)
    except Exception as exc:
        print(f"Unable to get Scheduler status: {exc}")
        return False


def get_worker_status(workers_list):
    """Verify that there is at least one worker registered to the scheduler

    - authenticates to the API
    - retrieves the list of workers
    - ensures at least one has been seen in last 15mn"""
    fifteen_ago = datetime.datetime.now() - datetime.timedelta(minutes=15)
    if not workers_list:
        return False
    try:
        return bool(
            [
                worker
                for worker in workers_list
                if datetime.datetime.fromisoformat(worker["on"].replace("Z", ""))
                >= fifteen_ago
            ]
        )
    except Exception as exc:
        print(f"Unable to get Workers status: {exc}")
        return False


def get_manager_status():
    """Verify that manager is online and prints homepage once logged-in

    It's important to log-in to ensure django doesn't crash on DB operations
    which would not be noticeable on the non-identified home page (login)"""

    url = os.getenv("STATUS_CARDSHOP_URL", "") + "/login/?next=/configurations/"
    payload = {
        "username": os.getenv("STATUS_MANAGER_USERNAME"),
        "password": os.getenv("STATUS_MANAGER_PASSWORD"),
        "next": "/configurations/",
    }
    try:
        with requests.Session() as session:
            resp = session.get(url, timeout=HTTP_TIMEOUT)
            html = BeautifulSoup(resp.text, "html.parser")
            payload["csrfmiddlewaretoken"] = html.find("input").attrs["value"]
            resp = session.post(url, data=payload, headers={"Referer": url})
            return resp.status_code == 200
    except Exception as exc:
        print(f"Unable to connect to manager: {exc}")
        return False


def get_database_status():
    """ connect to mongo and verify that number of `users` col records is positive """
    timeout = 1000
    try:
        client = pymongo.MongoClient(
            host=os.getenv("MONGODB_URI"),
            connectTimeoutMS=timeout,
            socketTimeoutMS=timeout,
            serverSelectionTimeoutMS=timeout,
            waitQueueTimeoutMS=timeout,
        )
        db = client["Cardshop"]
        return db["users"].count_documents({}) > 0
    except Exception as exc:
        print(f"Unable to connect to mongo database: {exc}")
        return False


def get_images_status():
    """ Verify that a standard image is available through its standard name """
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")
    try:
        return (
            requests.head(
                f"{url}/auto-images/demo/redirect/http",
                allow_redirects=True,
                timeout=HTTP_TIMEOUT,
            ).status_code
            == 200
        )
    except Exception as exc:
        print(f"Unable to get auto-image: {exc}")
        return False


def get_wasabi_status():
    """Testing the download of a specific file in our bucket that expires after 1y

    and serve only this specific purpose. If this starts failing, check the expiry
    date and update it"""
    url = os.getenv("STATUS_S3_URL", "") + "/status"
    try:
        return (
            requests.head(
                url, allow_redirects=True, timeout=WASABI_HTTP_TIMEOUT
            ).status_code
            == 200
        )
    except Exception as exc:
        print(f"Unable to get Wasabi status: {exc}")
        return False


def get_creatorload_status(access_token):

    url = os.getenv("STATUS_CARDSHOP_API_URL", "")

    try:
        resp = requests.get(
            f"{url}/workers/load",
            headers={
                "token": access_token,
                "Content-type": "application/json",
            },
            timeout=HTTP_TIMEOUT,
        )
        load = resp.json()
        if load.get("pending_tasks") == 0:
            return True
        if not load.get("estimated_completion"):
            return False
        completes_on = datetime.datetime.fromisoformat(
            load["estimated_completion"].replace("Z", "")
        )
        return (completes_on - datetime.datetime.now()).total_seconds() <= 86400
    except Exception as exc:
        print(f"Unable to get creators load: {exc}")
        return False


def timed_run():
    """ DEBUG: run and print the checks once with timeit """
    import timeit

    print(
        timeit.timeit(
            "pprint.pprint(loop.run_until_complete(collect_statuses()))",
            setup="from __main__ import loop, collect_statuses; import pprint",
            number=1,
        )
    )


if __name__ == "__main__":
    if "cli" in sys.argv:
        timed_run()
    else:
        app.run(port=8080)
