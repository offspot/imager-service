#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import datetime

from django.conf import settings

import requests

GET = "GET"
POST = "POST"
PATCH = "PATCH"
DELETE = "DELETE"
# URL = "https://api.demo.plug.kiwix.org"
URL = settings.CARDSHOP_API_URL
USERNAME = "manager"
PASSSWORD = settings.MANAGER_API_KEY
TOKEN = None
TOKEN_EXPIRY = None
REFRESH_TOKEN = None
REFRESH_TOKEN_EXPIRY = None


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


def authenticate():
    global TOKEN, REFRESH_TOKEN, TOKEN_EXPIRY, REFRESH_TOKEN_EXPIRY

    if TOKEN is not None and TOKEN_EXPIRY > datetime.datetime.now() + datetime.timedelta(
        minutes=2
    ):
        return

    try:
        token, access_token = get_token(username=USERNAME, password=PASSSWORD)
    except Exception as exp:
        TOKEN, REFRESH_TOKEN, TOKEN_EXPIRY = None
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
    req = getattr(requests, method.lower(), "get")(
        url=get_url(path), headers=get_token_headers(), json=payload
    )
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
    return query_api(GET, "/users/")


def fix_id(item):
    if not isinstance(item, dict):
        return item
    if "id" in item.keys():
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
        "scope": {"role": role, "task": {"create": True, "delete": True}},
    }
    if is_admin:
        payload["scope"]["users"] = {
            "read": True,
            "create": True,
            "delete": True,
            "update": True,
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
def get_channels_list():
    success, code, response = query_api(GET, "/channels/")
    return success, response


@auth_required
def add_channel(slug, name, active=True, private=False):
    payload = {"slug": slug, "name": name, "active": active, "private": private}

    success, code, response = query_api(POST, "/channels/", payload=payload)
    if not success or "_id" not in response:
        return False, response
    return True, response.get("_id")


@auth_required
def get_orders_list():
    success, code, response = query_api(GET, "/orders/")
    return success, response


def test():
    from pprint import pprint as pp

    # user = get_user_detail(users[0]["_id"])
    # pp(user)

    # print("adding user")
    # ret = add_user("rgaudin3", "rgaudin3@gmail.com", "renaud", "simple-user")
    # pp(ret)

    # print("delete user")
    # ret = delete_user("5ba3d304db414d00212e42bd")
    # pp(ret)

    # print("changing password")
    # ret = change_user_password("5ba3d334db414d00212e42c8", "renaud", "rgaudin3")
    # pp(ret)

    authenticate()

    # print("list users")
    # users = get_users_list()
    # pp(users)

    print("list channels")
    ret = get_channels_list()
    pp(ret)

    # print("add channels")
    # ret = add_channel("kiwix", "Kiwix", active=True, private=False)
    # pp(ret)

    # ret = add_channel("orange", "Orange", active=True, private=True)
    # pp(ret)


if __name__ == "__main__":
    test()
