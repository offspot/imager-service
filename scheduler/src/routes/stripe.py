#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import json
import logging
import datetime

import stripe
import requests
import flask
from flask import Blueprint, request, jsonify
from jinja2 import Environment, FileSystemLoader, select_autoescape

from emailing import send_email
from utils.mongo import StripeCustomer, AutoImages, StripeSession
from utils.templates import amount_str, strftime


# envs & secrets
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_PUBLIC_API_KEY = os.getenv("STRIPE_PUBLIC_API_KEY")
CARDSHOP_API_URL = os.getenv(
    "CARDSHOP_API_URL", "https://api.cardshop.hotspot.kiwix.org"
)
SHOP_PUBLIC_URL = os.getenv(
    "SHOP_PUBLIC_URL", "https://www.kiwix.org/en/cardshop-access/"
)
MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://cardshop.hotspot.kiwix.org")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")

# i18n
LANG_STRINGS = {
    "en": {
        "product_wikipedia": "Wikipedia Hotspot English",
        "product_access_1m": "One month Cardshop Access",
        "product_access_1y": "Annual Cardshop Access",
    },
    "de": {
        "product_wikipedia": "Wikipedia Hotspot auf Deutsch",
        "product_access_1m": "One month Cardshop Access",
        "product_access_1y": "Annual Cardshop Access",
    },
    "es": {
        "product_wikipedia": "Wikipedia Hotspot en español",
        "product_access_1m": "One month Cardshop Access",
        "product_access_1y": "Annual Cardshop Access",
    },
    "fr": {
        "product_wikipedia": "Wikipedia Hotspot Français",
        "product_access_1m": "Accès Cardshop 1 mois",
        "product_access_1y": "Accès Cardshop annuel",
    },
}

blueprint = Blueprint("stripe", __name__, url_prefix="/shop/stripe")
logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_API_KEY
email_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "txt"]),
)
email_env.filters["amount"] = amount_str
email_env.filters["date"] = strftime


def send_paid_order_email(
    kind,
    email,
    name,
    timestamp,
    product,
    product_name,
    price,
    http_url=None,
    torrent_url=None,
    username=None,
    password=None,
    expire_on=None,
    recurring=False,
):
    """ Sends email receipt to customer. Calls `prepare_order`. """
    context = {
        "email": email,
        "name": name,
        "timestamp": timestamp,
        "product": product,
        "product_name": product_name,
        "price": price,
        "http_url": http_url,
        "torrent_url": torrent_url,
        "username": username,
        "password": password,
        "expire_on": expire_on,
        "recurring": recurring,
    }
    subject = "Your Kiwix receipt"
    content = email_env.get_template(f"stripe/email_success_{kind}.html").render(
        **context
    )
    send_email(
        to=email,
        subject=subject,
        contents=content,
        copy_support=False,
    )


def get_links_for(product):
    """ (http, torrent, magnet) URLs for a product-ID """
    # currently, product-ids matches the auto-images slugs
    image = AutoImages.get(product)
    return image["http_url"], image["torrent_url"], image["magnet_url"]


def create_manager_account(email, expire_on):
    """ create a user account on manager for email and expire datetime using API """
    resp = requests.post(
        f"{MANAGER_API_URL}/accounts/create",
        headers={"Token": MANAGER_ACCOUNTS_API_TOKEN},
        json={"email": email, "expire_on": expire_on.isoformat()},
        timeout=10,
    )
    # existing cardshop account with this email
    if resp.status_code == 409:
        return True, {
            "name": email,
            "email": email,
            "username": email,
            "password": "<your-existing-password>",
            "existing": True,
        }
    if resp.status_code not in (200, 201):
        return False, {"status": resp.status_code}
    return True, resp.json()


def handle_credentials_creation(session, customer):
    # return if already handled and recorded
    session_record = StripeSession.get_or_create(
        customer.id, session.id, session.metadata["product"]
    )
    if session_record.get("username"):
        return session_record

    now = datetime.datetime.now()
    product_dc = session.metadata["product"].split("-")[-1]
    expire_on = now + datetime.timedelta(days=365 if product_dc == "1y" else 31)
    recurring = product_dc == "1y"

    # create user account on manager
    attempt = 1
    credentials = {}
    while attempt <= 3:
        try:
            success, credentials = create_manager_account(customer.email, expire_on)
            if not success:
                raise ValueError(f"HTTP {credentials.get('status')}")
        except Exception as exc:
            logger.critical(f"Unable to create manager account: {exc}")
            logger.exception(exc)
            attempt += 1
        else:
            break

    StripeSession.update(
        session_record["_id"],
        username=credentials.get("username"),
        password=credentials.get("password"),
        existing_account=credentials.get("existing", False),
        expiry=expire_on,
        recurring=recurring,
    )
    return StripeSession.get_or_none(session.id)


def handle_image_order(session, customer):
    product = session.metadata.get("product")

    http_url, torrent_url, _ = get_links_for(product)
    product_lang = product.split("-")[-1]

    send_paid_order_email(
        kind="image",
        email=customer.email,
        name=customer.name,
        timestamp=datetime.datetime.now(),
        product=product,
        product_name=LANG_STRINGS.get(product_lang, {}).get(
            "product_wikipedia", "Wikipedia Image"
        ),
        price=session.amount_total,
        http_url=http_url,
        torrent_url=torrent_url,
    )
    StripeSession.get_or_create(
        customer.id,
        session.id,
        session.metadata["product"],
        receipt_sent=True,
        http_url=http_url,
    )


def handle_access_order(session, customer):
    now = datetime.datetime.now()
    product_dc = session.metadata["product"].split("-")[-1]
    record = handle_credentials_creation(session, customer)

    # send email receipt
    send_paid_order_email(
        kind="access",
        email=customer.email,
        name=customer.name,
        timestamp=now,
        product=session.metadata["product"],
        product_name=LANG_STRINGS["en"].get(
            f"product_access_{product_dc}", "Cardshop Access"
        ),
        price=session.amount_total,
        username=record.get("username", "Unavailable – please contact us"),
        password=record.get("password", "Unavailable – please contact us"),
        existing_account=record.get("existing_account", False),
        expire_on=record.get("expiry"),
        recurring=record.get("recurring"),
    )
    StripeSession.update(record["_id"], receipt_sent=True)


PRODUCTS = {
    # product-id: (stipe-method, stripe-price-id, email-handler)
    "wikipedia-en": (
        os.getenv("STRIPE_METHOD_WP"),
        os.getenv("STRIPE_PRICE_WPEN"),
        handle_image_order,
    ),
    "wikipedia-es": (
        os.getenv("STRIPE_METHOD_WP"),
        os.getenv("STRIPE_PRICE_WPES"),
        handle_image_order,
    ),
    "wikipedia-de": (
        os.getenv("STRIPE_METHOD_WP"),
        os.getenv("STRIPE_PRICE_WPDE"),
        handle_image_order,
    ),
    "wikipedia-fr": (
        os.getenv("STRIPE_METHOD_WP"),
        os.getenv("STRIPE_PRICE_WPFR"),
        handle_image_order,
    ),
    "access-1m": (
        os.getenv("STRIPE_METHOD_ACCESS1M"),
        os.getenv("STRIPE_PRICE_ACCESS1M"),
        handle_access_order,
    ),
    "access-1y": (
        os.getenv("STRIPE_METHOD_ACCESS1Y"),
        os.getenv("STRIPE_PRICE_ACCESS1Y"),
        handle_access_order,
    ),
}


def update_cutomer(customer, session):
    """ update Customer object on Stripe with name if we have it in session """
    if not customer.name and session.metadata.get("name"):
        stripe.Customer.modify(customer.id, name=session.metadata.get("name"))
        customer.name = session.metadata.get("name")

    db_customer = StripeCustomer.get_or_none(customer.email)
    if not db_customer:
        StripeCustomer.create(customer.email, customer.id)

    if not StripeSession.get_or_none(session.id):
        StripeSession.create(session.id, customer.id, session.metadata.get("product"))


@blueprint.route("/", methods=["GET"])
def home():
    """ rediret to configured SHOP URL """
    return flask.redirect(SHOP_PUBLIC_URL)


@blueprint.route("/widget/", methods=["GET"])
@blueprint.route("/widget/<string:lang>", methods=["GET"])
def widget(lang="en"):
    """ iframe-able shop UI to select product and be redirected to Stripe """
    if lang not in ["en", "de", "es", "fr"]:
        return flask.Response("Invalid lang"), 404

    context = {
        "lang": lang,
        "api_url": CARDSHOP_API_URL,
        "translation": LANG_STRINGS.get(lang),
        "stripe_public_key": STRIPE_PUBLIC_API_KEY,
    }
    return flask.render_template("stripe/shop.html", **context)


@blueprint.route("/create-session", methods=["POST"])
def create_checkout_session():
    """ create a Stripe session for an order and return its id as json """
    name = request.form.get("name")
    email = request.form.get("email")
    product = request.form.get("product")
    if product not in PRODUCTS.keys():
        return jsonify(error="Unknown product"), 404
    mode, price, _ = PRODUCTS.get(product)

    customer = StripeCustomer.get_or_none(email)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price, "quantity": 1}],
            mode=mode,
            success_url=CARDSHOP_API_URL
            + "/shop/stripe/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=SHOP_PUBLIC_URL,
            customer=customer,
            customer_email=email if customer is None else None,
            metadata={"name": name, "product": product, "mode": mode, "price": price},
        )
        return jsonify({"id": session.id})
    except Exception as exc:
        print(exc)
        return jsonify(error=str(exc)), 403


@blueprint.route("/webhook/checkout_succeeded", methods=["POST"])
def on_checkout_suceeded():
    """ webhook inited on payment completed """
    event = None
    payload = request.data
    try:
        event = json.loads(payload)
    except Exception as exc:
        print("⚠️  Webhook error while parsing basic request." + str(exc))
        return jsonify(success=True)

    # Handle the event
    if event and event["type"] == "checkout.session.completed":
        session = stripe.checkout.Session.retrieve(event["data"]["object"]["id"])
        customer = stripe.customer.Customer.retrieve(session["customer"])

        try:
            update_cutomer(customer, session)
        except Exception as exc:
            logger.error("Unable to update customer")
            logger.exception(exc)

        try:
            handler = PRODUCTS.get(session["metadata"]["product"])[2]
            handler(session, customer)
        except Exception as exc:
            logger.critical("Unable to process handler")
            logger.exception(exc)
            return jsonify(success=False), 500
    else:
        print("Unhandled event type {}".format(event["type"]))
    return jsonify(success=True)


@blueprint.route("/success", methods=["GET"])
def success():
    """ confirmation webpage on payment successful """
    session_id = request.args.get("session_id")
    if not session_id:
        return flask.Response("No Session ID", 404)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer = stripe.customer.Customer.retrieve(session.get("customer"))
    except Exception as exc:
        logger.error(f"Unable to retrieve session & customer from Stripe: {exc}")
        logger.exception(exc)
        return flask.Response("Invalid Session ID", 400)

    try:
        update_cutomer(customer, session)
    except Exception as exc:
        logger.error("Unable to update customer")
        logger.exception(exc)

    if session.payment_status != "paid":
        logger.error(f"Session {session.id} is not paid: {session.payment_status}")
        return flask.Response("ERROR !!! not paid")

    context = {"customer": customer, "session": session, "shop_url": SHOP_PUBLIC_URL}
    product = session.metadata.get("product")
    if product.startswith("wikipedia-"):
        kind = "image"
        http_url, torrent_url, _ = get_links_for(product)
        context.update({"http_url": http_url, "torrent_url": torrent_url})
    elif product.startswith("access"):
        kind = "access"
        record = handle_credentials_creation(session, customer)

        if not record or not record.get("username"):
            record = {}
        context.update(
            {
                "username": record.get("username"),
                "password": record.get("password"),
                "expire_on": record.get("expiry"),
                "recurring": record.get("recurring"),
                "existing_account": record.get("existing_account", False),
            }
        )
    else:
        kind = "unknown"

    context.update(
        {
            "kind": kind,
            "product": session.metadata["product"],
            "product_name": LANG_STRINGS["en"].get(product, "Unknown"),
            "price": session.amount_total,
        }
    )
    return flask.render_template(f"stripe/success_{kind}.html", **context)
