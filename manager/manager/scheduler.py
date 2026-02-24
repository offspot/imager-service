#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
import http
import json
import logging

import requests
from django.conf import settings

GET = "GET"
POST = "POST"
PATCH = "PATCH"
PUT = "PUT"
DELETE = "DELETE"
URL = settings.CARDSHOP_API_URL
USERNAME = settings.MANAGER_API_USERNAME
PASSWORD = settings.MANAGER_API_KEY
ROLES = {
    "manager": "Manager (WebUI)",
    "creator": "Creator Worker",
    "writer": "Writer Worker",
}
logger = logging.getLogger(__name__)


class Tokens:
    access = ""
    access_expiry = datetime.datetime(1970, 1, 1)
    refresh = ""
    refresh_expiry = datetime.datetime(1970, 1, 1)

    @classmethod
    def reset(cls):
        cls.access = cls.refresh = ""
        cls.access_expiry = cls.refresh_expiry = datetime.datetime(1970, 1, 1)


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
        timeout=10,
    )
    req.raise_for_status()
    return req.json().get("access_token"), req.json().get("refresh_token")


def authenticate(*, force=False):
    if (
        not force
        and Tokens.access
        and Tokens.access_expiry
        and Tokens.access_expiry
        > datetime.datetime.now() + datetime.timedelta(minutes=2)
    ):
        return

    logger.debug(f"authenticate() with force={force}")

    try:
        access_token, refresh_token = get_token(username=USERNAME, password=PASSWORD)
    except Exception:
        Tokens.reset()
    else:
        now = datetime.datetime.now()
        Tokens.access, Tokens.refresh = access_token, refresh_token
        Tokens.access_expiry = now + datetime.timedelta(minutes=59)
        Tokens.refresh_expiry = now + datetime.timedelta(days=29)


def auth_required(func):
    def wrapper(*args, **kwargs):
        authenticate()
        return func(*args, **kwargs)

    return wrapper


def get_token_headers():
    return {"token": Tokens.access, "Content-type": "application/json"}


@auth_required
def query_api(method, path, payload=None, params=None):
    try:
        req = getattr(requests, method.lower(), requests.get)(
            url=get_url(path), headers=get_token_headers(), json=payload, params=params
        )
    except Exception as exp:
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

    if req.status_code in (http.HTTPStatus.OK, http.HTTPStatus.CREATED):
        return True, req.status_code, resp

    # Unauthorised error: attempt to re-auth as scheduler might have restarted?
    if req.status_code == http.HTTPStatus.UNAUTHORIZED:
        authenticate(force=True)

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
    success, code, response = query_api(GET, f"/users/{user_id}")
    return success, response


@auth_required
def add_user(
    username, email, password, role, channel, *, is_admin=False  # noqa: ARG001
):
    payload = {
        "username": username,
        "email": email,
        "password": password,
        "role": role,
        "channel": channel,
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
        PATCH, f"/users/{user_id}/password", payload=payload
    )
    if success:
        return True, None
    return False, response


@auth_required
def delete_user(user_id):
    success, code, response = query_api(DELETE, f"/users/{user_id}")
    if success or code == http.HTTPStatus.NOT_FOUND:
        return True, None
    return False, response


@auth_required
def change_user_status(user_id, active):
    payload = {"active": active}

    success, code, response = query_api(PATCH, f"/users/{user_id}", payload=payload)
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
def get_workers_list():
    success, code, response = query_api(GET, "/workers/")
    return success, response


@auth_required
def get_channels_list():
    success, code, response = query_api(GET, "/channels/")
    return success, response


@auth_required
def get_autoimages_list():
    success, code, response = query_api(
        GET,
        "/auto-images/",
        params={"with_config": "1"},
    )
    return success, response


@auth_required
def add_channel(
    slug, name, sender_name, sender_email, sender_address, *, active=True, private=False
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
        PATCH, f"/channels/{channel_id}", payload=payload
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
    success, code, response = query_api(GET, f"/warehouses/{warehouse_slug}")
    return success, response


@auth_required
def add_warehouse(slug, upload_uri, download_uri, *, active=True):
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
        PATCH, f"/warehouses/{warehouse_id}", payload=payload
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
    success, code, response = query_api(DELETE, f"/orders/{order_id}")
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def get_order(order_id, *, with_logs=False):
    success, code, response = query_api(
        GET, f"/orders/{order_id}", params={"with_logs": with_logs}
    )
    return success, response


@auth_required
def add_order_shipment(order_id, shipment_details):
    payload = {"shipment_details": shipment_details}
    success, code, response = query_api(PATCH, f"/orders/{order_id}", payload=payload)
    return success, response


@auth_required
def cancel_order(order_id):
    success, code, response = query_api(PATCH, f"/orders/{order_id}/cancel")
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def anonymize_orders(order_ids):
    success, code, response = query_api(
        PATCH, "/orders/anonymize", payload={"order_ids": order_ids}
    )
    if not success or "_ids" not in response:
        return False, response
    return True, response.get("_ids")


@auth_required
def get_task(task_id):
    success, code, response = query_api(GET, f"/tasks/{task_id}")
    return success, response


def get_channel_choices():
    from manager.scheduler import as_items_or_none, get_channels_list

    channels = as_items_or_none(*get_channels_list())
    if channels is None:
        return [("kiwix", "Kiwix")]
    return [
        (
            channel.get("slug"),
            "{name} ({pub})".format(
                name=channel.get("name"),
                pub="Private" if channel.get("private") else "Public",
            ),
        )
        for channel in channels
        if channel.get("active", False)
    ]


def get_warehouse_choices():
    from manager.scheduler import as_items_or_none, get_warehouses_list

    warehouses = as_items_or_none(*get_warehouses_list())
    if warehouses is None:
        return [("kiwix", "download")]
    return [
        (warehouse.get("slug"), warehouse.get("slug"))
        for warehouse in warehouses
        if warehouse.get("active", False)
    ]


@auth_required
def add_autoimage(
    slug,
    woo_id,
    config,
    config_yaml,
    contact_email,
    periodicity,
    warehouse,
    channel,
    private,
):
    payload = {
        "slug": slug,
        "woo_id": woo_id,
        "config": config,
        "config_yaml": config_yaml,
        "contact_email": contact_email,
        "periodicity": periodicity,
        "warehouse": warehouse,
        "channel": channel,
        "private": private,
    }

    success, code, response = query_api(POST, "/auto-images/", payload=payload)
    if not success or "slug" not in response:
        return False, response
    return True, response.get("slug")


@auth_required
def delete_autoimage(autoimage_slug):
    success, code, response = query_api(DELETE, f"/auto-images/{autoimage_slug}")
    if success or code == http.HTTPStatus.NOT_FOUND:
        return True, None
    return False, response


@auth_required
def update_autoimage(
    slug,
    woo_id,
    config,
    config_yaml,
    contact_email,
    periodicity,
    warehouse,
    channel,
    private,
):
    payload = {
        "slug": slug,
        "woo_id": woo_id,
        "config": config,
        "config_yaml": config_yaml,
        "contact_email": contact_email,
        "periodicity": periodicity,
        "warehouse": warehouse,
        "channel": channel,
        "private": private,
    }

    success, code, response = query_api(PUT, f"/auto-images/{slug}", payload=payload)
    if not success or "slug" not in response:
        return False, response
    return True, response.get("slug")
