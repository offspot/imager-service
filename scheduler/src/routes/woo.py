from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
from http import HTTPStatus

import flask
import requests
from flask import Blueprint, jsonify, request
from woocommerce import API

from routes.errors import HTTPError


SHOP_WOO_API_URL = os.getenv("SHOP_WOO_API_URL", "https://get.kiwix.org/")
SHOP_WOO_CONSUMER_KEY = os.getenv("SHOP_WOO_CONSUMER_KEY", "not-set")
SHOP_WOO_CONSUMER_SECRET = os.getenv("SHOP_WOO_CONSUMER_SECRET", "not-set")
SHOP_PUBLIC_URL = os.getenv("SHOP_PUBLIC_URL", "https://get.kiwix.org/shop/")
MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://imager.kiwix.org")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")
WOOCOMMERCE_ACCESS_HOOK_SECRET = os.getenv("WOOCOMMERCE_ACCESS_HOOK_SECRET", "not-set")

blueprint = Blueprint("woo", __name__, url_prefix="/shop/woo")
logger = logging.getLogger(__name__)


def get_wc_api():
    return API(
        url=SHOP_WOO_API_URL,
        consumer_key=SHOP_WOO_CONSUMER_KEY,
        consumer_secret=SHOP_WOO_CONSUMER_SECRET,
        version="wc/v3",
    )


def create_manager_account(email: str, expire_on: datetime.datetime):
    """create a user account on manager for email and expire datetime using API"""
    resp = requests.post(
        f"{MANAGER_API_URL}/accounts/create",
        headers={"Token": MANAGER_ACCOUNTS_API_TOKEN},
        json={"email": email, "expire_on": expire_on.isoformat(), "limited": False},
        timeout=10,
    )
    # existing cardshop account with this email
    if resp.status_code == HTTPStatus.CONFLICT:
        return True, {
            "name": email,
            "email": email,
            "username": email,
            "password": "<your-existing-password>",
            "existing": True,
        }
    # HTTP 200 is not expected and would only occur while manager is in maintenance mode
    # but then it is an error; there is no JSON response.
    if resp.status_code != HTTPStatus.CREATED:
        return False, {"status": resp.status_code}
    return True, resp.json()


def handle_credentials_creation(email: str):
    now = datetime.datetime.now()
    product_dc = "1m"
    expire_on = now + datetime.timedelta(days=365 if product_dc == "1y" else 31)

    # create user account on manager
    attempt = 1
    credentials = {}
    while attempt <= 3:
        try:
            success, credentials = create_manager_account(email, expire_on)
            if not success:
                raise ValueError(f"HTTP {credentials.get('status')}")
        except Exception as exc:
            logger.critical(f"Unable to create manager account: {exc}")
            logger.exception(exc)
            attempt += 1
        else:
            break

    credentials["expire_on"] = expire_on
    return credentials


def add_customer_note(order_id: int, credentials):
    wc_api = get_wc_api()
    username = credentials.get("username")
    password = credentials.get("password")
    if credentials.get("existing"):
        content = (
            f"You already have an account (Username: <code style='font-family:monospace;'>{username or 'n/a'}</code>). "
            "Password remains unchanged. "
            'To reset your password <a href="https://imager.kiwix.org/reset-password">click here</a>.'
        )
    elif username and password:
        content = f"Username <code style='font-family:monospace;'>{username}</code>. Password: <code style='font-family:monospace;'>{password}</code>."
    else:
        content = (
            f"Username: <code style='font-family:monospace;'>{username or 'n/a'}</code>. "
            f"Password: <code style='font-family:monospace;'>{password or 'n/a'}</code>. "
            "Something unexpected happened. Please contact us."
        )

    attempt = 1
    while attempt <= 3:
        try:
            resp = wc_api.post(
                f"orders/{order_id}/notes",
                {
                    "note": content,
                    "customer_note": True,
                    "author": "imager-service API",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload["id"] or payload["note"] != content:
                raise OSError("Error creating note")
            return payload
        except Exception as exc:
            logger.critical(f"Unable to create order note for {order_id=}: {exc}")
            logger.exception(exc)
            attempt += 1

    raise OSError(f"Error creating note for {order_id=}")


def mark_order_as_completed(order_id: int):
    new_status = "completed"
    wc_api = get_wc_api()
    attempt = 1
    while attempt <= 3:
        try:
            resp = wc_api.put(f"orders/{order_id}", {"status": new_status})
            resp.raise_for_status()
            payload = resp.json()
            if not payload["id"] or payload["status"] != new_status:
                raise OSError(f"Error marking order {new_status}")
            return payload
        except Exception as exc:
            logger.critical(f"Unable to mark order {new_status} for {order_id=}: {exc}")
            logger.exception(exc)
            attempt += 1

    raise OSError(f"Error marking order {new_status} for {order_id=}")


@blueprint.route("/webhook/imager_access_order", methods=["POST"])
def on_imager_access_order():
    """webhook inited on payment completed"""

    event = request.headers.get("X-WC-Webhook-Event")
    resource = request.headers.get("X-WC-Webhook-Resource")
    topic = request.headers.get("X-WC-Webhook-Topic")
    source = request.headers.get("X-Wc-Webhook-Source")
    if (
        event != "created"
        or resource != "order"
        or topic != "order.created"
        or not source.startswith(SHOP_WOO_API_URL)
    ):
        return jsonify(ignored=True)

    signature = base64.b64decode(request.headers.get("X-WC-Webhook-Signature"))
    comp_sig = hmac.digest(
        WOOCOMMERCE_ACCESS_HOOK_SECRET.encode(), request.data, hashlib.sha256
    )

    if not hmac.compare_digest(signature, comp_sig):
        raise HTTPError(HTTPStatus.UNAUTHORIZED, "Invalid signature")
    payload = json.loads(request.data)

    # check online that order is
    status = payload.get("status", "unknown")
    if status != "processing":
        return jsonify(ignored=True)

    order_id = payload.get("id")
    if not order_id:
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Missing Order ID")
    number = payload.get("number", "unknown")
    email = payload.get("billing", {}).get("email")

    logger.info(f"RECEIVED imager-access order via #{number}/{order_id} from {email}")

    # let it run unwrapped so we raise a 500 on exception and woo can automatically
    # inform admin, retry or disable
    credentials = handle_credentials_creation(email=email)
    add_customer_note(order_id=order_id, credentials=credentials)
    mark_order_as_completed(order_id=order_id)
    return jsonify(success=True)


@blueprint.route("/", methods=["GET"])
def home():
    """rediret to configured SHOP URL"""
    return flask.redirect(SHOP_PUBLIC_URL)
