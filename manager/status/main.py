#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import asyncio
import datetime
import http
import logging
import os
import sys
import time
from typing import Any

import pymongo
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
app = Flask(__name__)

HTTP_TIMEOUT = 10  # seconds
CREATOR_HTTP_TIMEOUT = HTTP_TIMEOUT * 2.5  # seconds
WASABI_HTTP_TIMEOUT = HTTP_TIMEOUT * 2.5  # seconds


@app.template_filter("status_text")
def status_text(value: Any) -> str:
    return "Operational" if value else "Failure"


@app.template_filter("status_class")
def status_class(value: Any) -> str:
    return "text-success" if value else "text-danger"


@app.route(r"/", methods=["GET"])
@app.route(r"/<path>", methods=["GET"])
def status(path: str = ""):  # noqa: ARG001
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
        http.HTTPStatus.OK
        if context["global_status"]
        else http.HTTPStatus.SERVICE_UNAVAILABLE,
    )


async def collect_statuses():
    """gather all status checks in a single dict"""
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


def collect_statuses_sequential() -> dict[str, str | bool]:
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


def _get_scheduler_token(url: str, username: str, password: str):
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


def get_scheduler_token() -> str:
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")
    # authenticate over scheduler
    try:
        access_token, _ = _get_scheduler_token(
            url,
            os.getenv("STATUS_SCHEDULER_USERNAME", ""),
            os.getenv("STATUS_SCHEDULER_PASSWORD", ""),
        )
    except Exception as exc:
        logger.debug(f"Unable to get scheduler token: {exc}")
        return "unknown"
    return access_token


def get_scheduler_workers_list(access_token: str) -> list[dict[str, Any]] | None:
    """Retrieve workers list from scheduler API to test scheduler and workers"""

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
        logger.debug(f"Unable to get workers list: {exc}")
        return None


def get_scheduler_status(workers_list: list[str]) -> bool:
    """Verify that we can connect to and retrieve data from scheduler API"""
    if not workers_list:
        return False
    try:
        return isinstance(workers_list, list)
    except Exception as exc:
        logger.debug(f"Unable to get Scheduler status: {exc}")
        return False


def get_worker_status(workers_list: list[dict[str, Any]] | None) -> bool:
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
        logger.debug(f"Unable to get Workers status: {exc}")
        return False


def get_manager_status() -> bool:
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
            return resp.status_code == http.HTTPStatus.OK
    except Exception as exc:
        logger.debug(f"Unable to connect to manager: {exc}")
        return False


def get_database_status() -> bool:
    """connect to mongo and verify that number of `users` col records is positive"""
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
        logger.debug(f"Unable to connect to mongo database: {exc}")
        return False


def get_images_status() -> bool:
    """Verify that a standard image is available through its standard name"""
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")
    try:
        return (
            requests.head(
                f"{url}/auto-images/demo/redirect/http",
                allow_redirects=True,
                timeout=HTTP_TIMEOUT,
            ).status_code
            == http.HTTPStatus.OK
        )
    except Exception as exc:
        logger.debug(f"Unable to get auto-image: {exc}")
        return False


def get_wasabi_status() -> bool:
    """Testing the download of a specific file in our bucket that expires after 1y

    and serve only this specific purpose. If this starts failing, check the expiry
    date and update it"""
    url = os.getenv("STATUS_S3_URL", "") + "/status"
    try:
        return (
            requests.head(
                url, allow_redirects=True, timeout=WASABI_HTTP_TIMEOUT
            ).status_code
            == http.HTTPStatus.OK
        )
    except Exception as exc:
        logger.debug(f"Unable to get Wasabi status: {exc}")
        return False


def get_creatorload_status(access_token: str) -> bool:
    url = os.getenv("STATUS_CARDSHOP_API_URL", "")
    two_days = 60 * 60 * 48

    try:
        resp = requests.get(
            f"{url}/workers/load",
            headers={
                "token": access_token,
                "Content-type": "application/json",
            },
            timeout=CREATOR_HTTP_TIMEOUT,
        )
        load = resp.json()
        if load.get("pending_tasks") == 0:
            return True
        if not load.get("estimated_completion"):
            return False
        completes_on = datetime.datetime.fromisoformat(
            load["estimated_completion"].replace("Z", "")
        )
        return (completes_on - datetime.datetime.now()).total_seconds() <= two_days
    except Exception as exc:
        logger.debug(f"Unable to get creators load: {exc}")
        return False


def timed_run():
    """DEBUG: run and print the checks once with timeit"""
    import timeit

    logger.info(
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
