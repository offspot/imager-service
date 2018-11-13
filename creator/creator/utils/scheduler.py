#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import datetime

import requests

from .setting import Setting

GET = "GET"
POST = "POST"
PATCH = "PATCH"
DELETE = "DELETE"
TOKEN = None
TOKEN_EXPIRY = None
REFRESH_TOKEN = None
REFRESH_TOKEN_EXPIRY = None


class SchedulerAPIError(Exception):
    pass


def get_url(path):
    return "/".join([Setting.api_url, path[1:] if path[0] == "/" else path])


def get_token(username, password):
    req = requests.post(
        url=get_url("/auth/authorize"),
        headers={
            "username": username,
            "password": password,
            "Content-type": "application/json",
        },
    )
    req.raise_for_status()
    return req.json().get("access_token"), req.json().get("refresh_token")


def authenticate(force=False):
    global TOKEN, REFRESH_TOKEN, TOKEN_EXPIRY, REFRESH_TOKEN_EXPIRY

    if (
        not force
        and TOKEN is not None
        and TOKEN_EXPIRY > datetime.datetime.now() + datetime.timedelta(minutes=2)
    ):
        return

    try:
        token, access_token = get_token(
            username=Setting.username, password=Setting.password
        )
    except Exception as exp:
        TOKEN = REFRESH_TOKEN = TOKEN_EXPIRY = None
    else:
        TOKEN, REFRESH_TOKEN = token, access_token
        TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(minutes=59)
        REFRESH_TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(days=29)


def auth_required(func):
    def wrapper(*args, **kwargs):
        authenticate()
        return func(*args, **kwargs)

    return wrapper


def get_token_headers():
    return {"token": TOKEN, "Content-type": "application/json"}


@auth_required
def query_api(method, path, payload=None):
    try:
        req = getattr(requests, method.lower(), "get")(
            url=get_url(path), headers=get_token_headers(), json=payload
        )
    except Exception as exp:
        import traceback

        print(traceback.format_exc())
        return (False, "ConnectionError", "ConnectionErrorL -- {}".format(exp))

    try:
        resp = req.json() if req.text else {}
    except json.JSONDecodeError:
        return (
            False,
            req.status_code,
            "ResponseError (not JSON): -- {}".format(req.text),
        )
    except Exception as exp:
        return (
            False,
            req.status_code,
            "ResponseError -- {} -- {}".format(str(exp), req.text),
        )

    if req.status_code in (200, 201):
        return True, req.status_code, resp

    return (False, req.status_code, resp["error"] if "error" in resp else str(resp))


@auth_required
def test_connection():
    return query_api(GET, "/")


@auth_required
def get_available_tasks():
    success, code, response = query_api(GET, "/tasks/")
    return success, response


@auth_required
def request_task(task_id):
    success, code, response = query_api(PATCH, "/tasks/{id}/request".format(id=task_id))
    return success, response


@auth_required
def update_task_status(task_id, status, log=None):
    payload = {"status": status, "log": log}
    success, code, response = query_api(
        PATCH, "/tasks/{id}/status".format(id=task_id), payload=payload
    )
    return success, response


@auth_required
def upload_logs(task_id, worker_log=None, installer_log=None):
    payload = {}
    if worker_log is not None:
        payload.update({"worker_log": worker_log})
    if installer_log is not None:
        payload.update({"installer_log": installer_log})

    success, code, response = query_api(
        POST, "/tasks/{id}/logs".format(id=task_id), payload=payload
    )
    return success, response
