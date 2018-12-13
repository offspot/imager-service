#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import logging
import datetime

from django.conf import settings

import requests

GET = "GET"
POST = "POST"
PATCH = "PATCH"
DELETE = "DELETE"
# URL = "https://api.demo.plug.kiwix.org"
URL = settings.CARDSHOP_API_URL
USERNAME = settings.MANAGER_API_USERNAME
PASSWORD = settings.MANAGER_API_KEY
ACCESS_TOKEN = None
ACCESS_TOKEN_EXPIRY = None
REFRESH_TOKEN = None
REFRESH_TOKEN_EXPIRY = None
ROLES = {
    "manager": "Manager (WebUI)",
    "creator": "Creator Worker",
    "writer": "Writer Worker",
}
logger = logging.getLogger(__name__)


class SchedulerAPIError(Exception):
    pass


def get_url(path):
    return "/".join([URL, path[1:] if path[0] == "/" else path])


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
    global ACCESS_TOKEN, REFRESH_TOKEN, ACCESS_TOKEN_EXPIRY, REFRESH_TOKEN_EXPIRY

    if (
        not force
        and ACCESS_TOKEN is not None
        and ACCESS_TOKEN_EXPIRY
        > datetime.datetime.now() + datetime.timedelta(minutes=2)
    ):
        return

    logger.debug("authenticate() with force={}".format(force))

    try:
        access_token, refresh_token = get_token(username=USERNAME, password=PASSWORD)
    except Exception as exp:
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
        req = getattr(requests, method.lower(), "get")(
            url=get_url(path), headers=get_token_headers(), json=payload
        )
    except Exception as exp:
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

    # Unauthorised error: attempt to re-auth as scheduler might have restarted?
    if req.status_code == 401:
        authenticate(True)

    return (False, req.status_code, resp["error"] if "error" in resp else str(resp))


@auth_required
def test_connection():
    return query_api(GET, "/")


def fix_id(item):
    if not isinstance(item, dict):
        return item
    if "id" not in item.keys() and "_id" in item.keys():
        item.update({"id": item["_id"]})
    return item


def as_items_or_none(success, response):
    if success and "items" in response:
        return map(fix_id, response.get("items", []))
    return None


@auth_required
def get_users_list():
    success, code, response = query_api(GET, "/users/")
    return success, response


@auth_required
def get_user_detail(user_id):
    success, code, response = query_api(GET, "/users/{}".format(user_id))
    return success, response


@auth_required
def add_user(username, email, password, role, is_admin=False):
    payload = {
        "username": username,
        "email": email,
        "password": password,
        "role": role,
        "active": True,
    }

    success, code, response = query_api(POST, "/users/", payload=payload)
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def change_user_password(user_id, old_password, new_password):
    payload = {"old": old_password, "new": new_password}
    success, code, response = query_api(
        PATCH, "/users/{}/password".format(user_id), payload=payload
    )
    if success:
        return True, None
    print("HTTP", code)
    return False, response


@auth_required
def delete_user(user_id):
    success, code, response = query_api(DELETE, "/users/{}".format(user_id))
    if success or code == 404:
        return True, None
    return False, response


@auth_required
def change_user_status(user_id, active):
    payload = {"active": active}

    success, code, response = query_api(
        PATCH, "/users/{}".format(user_id), payload=payload
    )
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def enable_user(user_id):
    return change_user_status(user_id, True)


@auth_required
def disable_user(user_id):
    return change_user_status(user_id, False)


@auth_required
def get_channels_list():
    success, code, response = query_api(GET, "/channels/")
    return success, response


@auth_required
def add_channel(
    slug, name, sender_name, sender_email, sender_address, active=True, private=False
):
    payload = {
        "slug": slug,
        "name": name,
        "active": active,
        "private": private,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_address": sender_address,
    }

    success, code, response = query_api(POST, "/channels/", payload=payload)
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def change_channel_status(channel_id, active):
    payload = {"active": active}

    success, code, response = query_api(
        PATCH, "/channels/{}".format(channel_id), payload=payload
    )
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def enable_channel(channel_id):
    return change_channel_status(channel_id, True)


@auth_required
def disable_channel(channel_id):
    return change_channel_status(channel_id, False)


@auth_required
def get_warehouses_list():
    success, code, response = query_api(GET, "/warehouses/")
    return success, response


@auth_required
def get_warehouse_from(warehouse_slug):
    success, code, response = query_api(GET, "/warehouses/{}".format(warehouse_slug))
    return success, response


@auth_required
def add_warehouse(slug, upload_uri, download_uri, active=True):
    payload = {
        "slug": slug,
        "upload_uri": upload_uri,
        "download_uri": download_uri,
        "active": active,
    }

    success, code, response = query_api(POST, "/warehouses/", payload=payload)
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def change_warehouse_status(warehouse_id, active):
    payload = {"active": active}

    success, code, response = query_api(
        PATCH, "/warehouses/{}".format(warehouse_id), payload=payload
    )
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def enable_warehouse(warehouse_id):
    return change_warehouse_status(warehouse_id, True)


@auth_required
def disable_warehouse(warehouse_id):
    return change_warehouse_status(warehouse_id, False)


@auth_required
def get_orders_list():
    success, code, response = query_api(GET, "/orders/")
    return success, response


@auth_required
def create_order(payload):
    success, code, response = query_api(POST, "/orders/", payload=payload)
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def delete_order(order_id):
    success, code, response = query_api(DELETE, "/orders/{}".format(order_id))
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def get_order(order_id):
    success, code, response = query_api(GET, "/orders/{id}".format(id=order_id))
    return success, response


@auth_required
def add_order_shipment(order_id, shipment_details):
    payload = {"shipment_details": shipment_details}
    success, code, response = query_api(
        PATCH, "/orders/{id}".format(id=order_id), payload=payload
    )
    return success, response


@auth_required
def get_task(task_id):
    success, code, response = query_api(GET, "/tasks/{id}".format(id=task_id))
    return success, response
