import datetime
import json
import logging

import requests

from .setting import Setting

GET = "GET"
POST = "POST"
PATCH = "PATCH"
DELETE = "DELETE"
ACCESS_TOKEN = None
ACCESS_TOKEN_EXPIRY = datetime.datetime(1970, 1, 1)
REFRESH_TOKEN = None
REFRESH_TOKEN_EXPIRY = None
WORKER_TYPE = "creator"

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent": Setting.user_agent})


class SchedulerAPIError(Exception):
    pass


def get_url(path):
    return "/".join([Setting.api_url, path[1:] if path[0] == "/" else path])


def get_access_token():
    global ACCESS_TOKEN
    return ACCESS_TOKEN


def get_token(username, password):
    req = session.post(
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
    global ACCESS_TOKEN, REFRESH_TOKEN, ACCESS_TOKEN_EXPIRY, REFRESH_TOKEN_EXPIRY

    if (
        not force
        and ACCESS_TOKEN is not None
        and ACCESS_TOKEN_EXPIRY
        > datetime.datetime.now() + datetime.timedelta(minutes=2)
    ):
        return

    logger.debug(f"authenticate() with force={force}")

    try:
        access_token, refresh_token = get_token(
            username=Setting.username, password=Setting.password
        )
    except Exception as exp:
        logger.error(exp)
        ACCESS_TOKEN = REFRESH_TOKEN = ACCESS_TOKEN_EXPIRY = None
    else:
        ACCESS_TOKEN, REFRESH_TOKEN = access_token, refresh_token
        ACCESS_TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(minutes=59)
        REFRESH_TOKEN_EXPIRY = datetime.datetime.now() + datetime.timedelta(days=29)


def auth_required(func):
    def wrapper(*args, **kwargs):
        authenticate()
        return func(*args, **kwargs)

    return wrapper


def get_token_headers():
    return {"token": ACCESS_TOKEN, "Content-type": "application/json"}


@auth_required
def query_api(method, path, payload=None):
    try:
        req = getattr(session, method.lower(), session.get)(
            url=get_url(path),
            headers=get_token_headers(),
            json=payload,
            timeout=30,
        )
    except Exception as exp:
        import traceback

        print(traceback.format_exc())
        return (False, "ConnectionError", f"ConnectionErrorL -- {exp}")

    try:
        resp = req.json() if req.text else {}
    except json.JSONDecodeError:
        return (
            False,
            req.status_code,
            f"ResponseError (not JSON): -- {req.text}",
        )
    except Exception as exp:
        return (
            False,
            req.status_code,
            f"ResponseError -- {exp!s} -- {req.text}",
        )

    if req.status_code in (200, 201):
        return True, req.status_code, resp

    # Unauthorised error: attempt to re-auth as scheduler might have restarted?
    if req.status_code == 401:
        authenticate(True)

    return (False, req.status_code, resp["error"] if "error" in resp else str(resp))


@auth_required
def test_connection():
    return query_api(GET, "/")


@auth_required
def get_available_tasks(slot=None):
    success, code, response = query_api(GET, f"/tasks/{WORKER_TYPE}")
    return success, response


@auth_required
def get_task(task_id):
    success, code, response = query_api(GET, f"/tasks/{WORKER_TYPE}/{task_id}")
    return success, response


@auth_required
def request_task(task_id):
    success, code, response = query_api(
        PATCH, f"/tasks/{WORKER_TYPE}/{task_id}/request"
    )
    return success, response


@auth_required
def update_task_status(task_id, status, log=None, extra={}):
    payload = {"status": status, "log": log, "extra": extra}
    success, code, response = query_api(
        PATCH,
        f"/tasks/{WORKER_TYPE}/{task_id}/status",
        payload=payload,
    )
    return success, response


@auth_required
def upload_logs(task_id, logs={}):
    for key, value in logs.items():
        if value is None:
            del logs[key]

    success, code, response = query_api(
        POST,
        f"/tasks/{WORKER_TYPE}/{task_id}/logs",
        payload=logs,
    )
    return success, response


@auth_required
def send_sos(error):
    success, code, response = query_api(
        POST, "/workers/sos", payload={"error": error, "type": WORKER_TYPE}
    )
    return success, response
