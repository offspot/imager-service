from __future__ import annotations

import datetime
from http import HTTPStatus
import json
import logging
import os
import sys
import tempfile
import zlib
from pathlib import Path

import flask
import pdfkit
import requests
import stripe
from babel.dates import format_datetime
from emailing import send_email
from flask import Blueprint, jsonify, make_response, request
from jinja2 import Environment, FileSystemLoader, select_autoescape
from requests.auth import HTTPBasicAuth
from utils.countries import SWISSPOST_PRIORITYPLUS_SUPPORTED
from utils.mongo import AutoImages, StripeCustomer, StripeSession
from utils.serialnumber import is_valid_serial
from utils.templates import amount_str, b64qrcode, country_name, linebreaksbr, yesno

# envs & secrets
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_PUBLIC_API_KEY = os.getenv("STRIPE_PUBLIC_API_KEY")
SHOP_IS_DISABLED = bool(os.getenv("SHOP_IS_DISABLED"))
CARDSHOP_API_URL = os.getenv("CARDSHOP_API_URL", "https://api.imager.kiwix.org")
SHOP_PUBLIC_URL = os.getenv("SHOP_PUBLIC_URL", "https://kiwix.org/en/kiwix-hotspot/")
MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://imager.kiwix.org")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")
ASSEMBLY_EMAIL = os.getenv("ASSEMBLY_EMAIL")
INVOICE_DIR = (
    Path(os.environ["INVOICE_DIR"])
    if os.getenv("INVOICE_DIR")
    else Path(tempfile.mkdtemp(prefix="invoices_"))
)
TRACKING_URL_TMPL = (
    os.getenv("TRACKING_URL_TMPL") or "https://parcelsapp.com/en/tracking/{number}"
)
# devel only
RUN_HANDLER_ON_SUCCESS = bool(os.getenv("RUN_HANDLER_ON_SUCCESS"))

CRM_USERNAME = os.getenv("CRM_USERNAME") or ""
CRM_PASSWORD = os.getenv("CRM_PASSWORD") or ""


SHIPPING_RATES = {
    # order matters ; first one is auto-selected
    os.environ["SHIPPING_RATE_TRACKING"]: "with-tracking",
    # ATM we are offering a single option
    # os.environ["SHIPPING_RATE_NOTRACKING"]: "without-tracking",
}

TAXES_ENABLED = bool(os.getenv("TAXES_ENABLED") or "")

PLUG_TYPES = {
    "UK": ["GB", "IE", "MT", "CY", "MY", "SG"],
    "US": ["US", "CA", "JP", "MX"],
    "EU": [],  # all the others
}

SHIPPING_TO_COUNTRIES = sorted([*SWISSPOST_PRIORITYPLUS_SUPPORTED, "CH"])

PRODUCTS = {
    # product-id: (stipe-method, stripe-price-id, handler-type, product-name)
    "wikipedia-en": (
        os.environ["STRIPE_METHOD_WP"],
        os.environ["STRIPE_PRICE_WPEN"],
        "image",
        "Wikipedia Hotspot OS only",
    ),
    "preppers": (
        os.environ["STRIPE_METHOD_PP"],
        os.environ["STRIPE_PRICE_PP"],
        "image",
        "Preppers Hotspot OS only",
    ),
    "medical": (
        os.environ["STRIPE_METHOD_MD"],
        os.environ["STRIPE_PRICE_MD"],
        "image",
        "Medical Hotspot OS only",
    ),
    "ted": (
        os.environ["STRIPE_METHOD_TED"],
        os.environ["STRIPE_PRICE_TED"],
        "image",
        "TED Hotspot OS only",
    ),
    "computers": (
        os.environ["STRIPE_METHOD_CS"],
        os.environ["STRIPE_PRICE_CS"],
        "image",
        "Computer Hotspot OS only",
    ),
    "access-1m": (
        os.environ["STRIPE_METHOD_ACCESS1M"],
        os.environ["STRIPE_PRICE_ACCESS1M"],
        "access",
        "One month Imager Access",
    ),
    # "access-1y": (
    #     os.environ["STRIPE_METHOD_ACCESS1Y"],
    #     os.environ["STRIPE_PRICE_ACCESS1Y"],
    #     "access",
    #     "Annual Imager Access",
    # ),
    "wikipedia-en-h1": (
        os.environ["STRIPE_METHOD_WPH1"],
        os.environ["STRIPE_PRICE_WPENH1"],
        "device",
        "Wikipedia Hotspot",
    ),
    "preppers-h1": (
        os.environ["STRIPE_METHOD_PPH1"],
        os.environ["STRIPE_PRICE_PPH1"],
        "device",
        "Preppers Hotspot",
    ),
    "medical-h1": (
        os.environ["STRIPE_METHOD_MDH1"],
        os.environ["STRIPE_PRICE_MDH1"],
        "device",
        "Medical Hotspot",
    ),
    "ted-h1": (
        os.environ["STRIPE_METHOD_TEDH1"],
        os.environ["STRIPE_PRICE_TEDH1"],
        "device",
        "TED Hotspot",
    ),
    "computers-h1": (
        os.environ["STRIPE_METHOD_CSH1"],
        os.environ["STRIPE_PRICE_CSH1"],
        "device",
        "Computer Hotspot",
    ),
}


def format_dt(date, fmt="d MMMM yyyy, HH:mm", locale="en_GB"):
    """format datetime using babel. Format optional"""
    return format_datetime(date, fmt, locale=locale)


def get_plug_type(country_code):
    """plug type (UK, US, EU) from country code"""
    for kind, countries in PLUG_TYPES.items():
        if country_code in countries:
            return kind
    return "EU"


def short_stripe_id(session_id) -> str:
    """a short version of the Stripe CheckoutSession ID. Non reversible"""
    return str(zlib.adler32(session_id.encode("ASCII")))


def nonone(value, replacement: str = "") -> str:
    """a default-like filter that also works with value None"""
    return value or replacement


def get_tracking_url(tracking_number: str) -> str:
    """Tracking URL for a tracking number"""
    return TRACKING_URL_TMPL.replace("{number}", tracking_number)


def get_product_name(product: str) -> str:
    """Name of a product from its code"""
    return PRODUCTS[product][3]


def get_handler(product: str):
    """the handler (email/post-processing) for a given product)"""
    return getattr(sys.modules[__name__], f"handle_{PRODUCTS[product][2]}_order")


blueprint = Blueprint("stripe", __name__, url_prefix="/shop/stripe")
logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_API_KEY
email_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "txt"]),
)
email_env.filters["amount"] = amount_str
email_env.filters["date"] = format_dt
email_env.filters["country"] = country_name
email_env.filters["plug"] = get_plug_type
email_env.filters["yesno"] = yesno
email_env.filters["qrcode"] = b64qrcode
email_env.filters["linebreaksbr"] = linebreaksbr
email_env.filters["shortstripe"] = short_stripe_id
email_env.filters["nonone"] = nonone
email_env.filters["tracking_url"] = get_tracking_url


def get_paid_email_content_for(
    kind, email, name, timestamp, product, product_name, price, **kwargs
):
    return email_env.get_template(f"stripe/email_success_{kind}.html").render(
        kind=kind,
        email=email,
        name=name,
        timestamp=timestamp,
        product=product,
        product_name=product_name,
        price=price,
        **kwargs,
    )


def send_paid_order_email(
    kind,
    email,
    name,
    timestamp,
    product,
    product_name,
    price,
    *,
    cc=None,
    attachments=None,
    **kwargs,
):
    """Sends email receipt to customer. Calls `prepare_order`."""
    subject = "Your Kiwix receipt"
    session = kwargs.get("session")
    if session:
        subject += f" ({short_stripe_id(session.id)})"
    content = get_paid_email_content_for(
        kind=kind,
        email=email,
        name=name,
        timestamp=timestamp,
        product=product,
        product_name=product_name,
        price=price,
        **kwargs,
    )

    return send_email(
        to=email,
        cc=cc or [],
        subject=subject,
        contents=content,
        copy_support=False,
        attachments=attachments,
    )


def get_order_kind_for(product):
    if product.endswith("-h1"):
        return "device"
    elif product.startswith("wikipedia-") or product in (
        "preppers",
        "computers",
        "ted",
        "medical",
    ):
        return "image"
    elif product.startswith("access"):
        return "access"

    return "unknown"


def get_links_for(product):
    """(http, torrent, magnet) URLs for a product-ID"""
    # currently, product-ids matches the auto-images slugs
    image = AutoImages.get(product)
    return image["http_url"], image["torrent_url"], image["magnet_url"]


def create_manager_account(email, expire_on):
    """create a user account on manager for email and expire datetime using API"""
    resp = requests.post(
        f"{MANAGER_API_URL}/accounts/create",
        headers={"Token": MANAGER_ACCOUNTS_API_TOKEN},
        json={"email": email, "expire_on": expire_on.isoformat(), "limited": False},
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
    # HTTP 200 is not expected and would only occur while manager is in maintenance mode
    # but then it is an error; there is no JSON response.
    if resp.status_code != 201:
        return False, {"status": resp.status_code}
    return True, resp.json()


def handle_credentials_creation(session, customer):
    # return if already handled and recorded
    session_record = StripeSession.get_or_create(
        customer_id=customer.id,
        session_id=session.id,
        product=session.metadata["product"],
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
        record_id=session_record["_id"],
        username=credentials.get("username"),
        password=credentials.get("password"),
        existing_account=credentials.get("existing", False),
        expiry=expire_on,
        recurring=recurring,
    )
    return StripeSession.get_or_none(session.id)


def handle_device_order(session, customer):
    product = session.metadata.get("product")

    session_record = StripeSession.get_or_create(
        customer_id=customer.id,
        session_id=session.id,
        product=session.metadata["product"],
    )
    # record device-order specific info into DB
    shipping_rate = session.shipping_cost.shipping_rate
    shipping_option = SHIPPING_RATES[shipping_rate]
    shipping_option_name = stripe.ShippingRate.retrieve(shipping_rate).display_name
    shipping_with_tracking = SHIPPING_RATES[shipping_rate] == "with-tracking"

    StripeSession.update(
        record_id=session_record["_id"],
        received_on=datetime.datetime.now(),
        email=customer.email,
        invoice_num=short_stripe_id(session.id),
        billing={
            "name": session.customer_details.name,
            "phone": session.customer_details.phone,
            "line1": session.customer_details.address.line1,
            "line2": session.customer_details.address.line2,
            "city": session.customer_details.address.city,
            "postal_code": session.customer_details.address.postal_code,
            "state": session.customer_details.address.state,
            "country_code": session.customer_details.address.country,
            "tax_exempt": session.customer_details.tax_exempt,
            "tax_ids": session.customer_details.tax_ids,
        },
        shipping={
            "name": session.shipping_details.name,
            "phone": session.shipping_details.phone,
            "line1": session.shipping_details.address.line1,
            "line2": session.shipping_details.address.line2,
            "city": session.shipping_details.address.city,
            "postal_code": session.shipping_details.address.postal_code,
            "state": session.shipping_details.address.state,
            "country_code": session.shipping_details.address.country,
            "with_tracking": shipping_with_tracking,
            "option": shipping_option,
            "option_name": shipping_option_name,
            "plug": get_plug_type(session.shipping_details.address.country),
        },
        amount={
            "product": session.amount_subtotal,
            "discount": getattr(session, "amount_discount", 0),
            "shipping": session.total_details.amount_shipping,
            "tax": session.total_details.amount_tax,
            "total": session.amount_total,
        },
    )

    # sould this now be ran exactly at payment time, we need the date to be
    # close to the payment time. We assume session + 5mn in this case.
    # this is only applied if running 24h+ after the session creation
    now = datetime.datetime.now()
    session_on = datetime.datetime.fromtimestamp(session.created)
    invoice_date = (
        session_on + datetime.timedelta(minutes=5)
        if (now - session_on).days >= 1
        else now
    )

    # send receipt email
    email_id = send_paid_order_email(
        kind="device",
        email=customer.email,
        cc=ASSEMBLY_EMAIL,
        name=customer.name,
        timestamp=invoice_date,
        product=product,
        product_name=get_product_name(product),
        price=session.amount_total,
        session=session,
        shipping_option=shipping_option,
        shipping_option_name=shipping_option_name,
        shipping_with_tracking=shipping_with_tracking,
        attachments=[build_invoice(session_id=session.id, force=True)],
    )

    StripeSession.update(
        record_id=session_record["_id"], receipt_sent=True, email_id=email_id
    )


def handle_image_order(session, customer):
    product = session.metadata.get("product")
    http_url, torrent_url, _ = get_links_for(product)

    email_id = send_paid_order_email(
        kind="image",
        email=customer.email,
        name=customer.name,
        timestamp=datetime.datetime.now(),
        product=product,
        product_name=get_product_name(product),
        price=session.amount_total,
        http_url=http_url,
        torrent_url=torrent_url,
    )
    StripeSession.get_or_create(
        customer_id=customer.id,
        session_id=session.id,
        product=product,
        receipt_sent=True,
        email_id=email_id,
        http_url=http_url,
    )


def handle_access_order(session, customer):
    now = datetime.datetime.now()
    record = handle_credentials_creation(session=session, customer=customer)

    # send email receipt
    email_id = send_paid_order_email(
        kind="access",
        email=customer.email,
        name=customer.name,
        timestamp=now,
        product=session.metadata["product"],
        product_name=get_product_name(session.metadata["product"]),
        price=session.amount_total,
        username=record.get("username", "Unavailable – please contact us"),
        password=record.get("password", "Unavailable – please contact us"),
        existing_account=record.get("existing_account", False),
        expire_on=record.get("expiry"),
        recurring=record.get("recurring"),
    )
    StripeSession.update(record_id=record["_id"], receipt_sent=True, email_id=email_id)


def involves_shipping(product: str) -> bool:
    return product.endswith("-h1")


def update_cutomer(customer, session):
    """update Customer object on Stripe with name if we have it in session"""
    if not customer.name and session.metadata.get("name"):
        stripe.Customer.modify(customer.id, name=session.metadata.get("name"))
        customer.name = session.metadata.get("name")

    db_customer = StripeCustomer.get_or_none(customer.email)
    if not db_customer:
        StripeCustomer.create(email=customer.email, customer_id=customer.id)

    if not StripeSession.get_or_none(session.id):
        StripeSession.create(
            session_id=session.id,
            customer_id=customer.id,
            product=session.metadata.get("product"),
        )


@blueprint.route("/", methods=["GET"])
def home():
    """rediret to configured SHOP URL"""
    return flask.redirect(SHOP_PUBLIC_URL)


@blueprint.route("/widget/", methods=["GET"])
@blueprint.route("/widget/<string:lang>", methods=["GET"])
def widget(lang="en"):
    """iframe-able shop UI to select product and be redirected to Stripe"""

    if lang not in ["en", "de", "es", "fr"]:
        return flask.Response("Invalid lang"), 404

    context = {
        "api_url": CARDSHOP_API_URL,
        "stripe_public_key": STRIPE_PUBLIC_API_KEY,
    }
    if SHOP_IS_DISABLED:
        return flask.render_template("stripe/disabled_shop.html", **context)
    return flask.render_template("stripe/shop.html", **context)


@blueprint.route("/create-session", methods=["POST"])
def create_checkout_session():
    """create a Stripe session for an order and return its id as json"""
    name = request.form.get("name")
    email = request.form.get("email")
    product = request.form.get("product")
    if product not in PRODUCTS.keys():
        return jsonify(error="Unknown product"), 404
    mode = PRODUCTS[product][0]
    price = PRODUCTS[product][1]

    customer = StripeCustomer.get_or_none(email)
    shipping_details = {}
    tax_details = {}

    if TAXES_ENABLED:
        tax_details = {
            "automatic_tax": {"enabled": True, "liability": {"type": "self"}},
            "tax_id_collection": {"enabled": True},
        }

    try:
        if involves_shipping(product):
            shipping_details = {
                "billing_address_collection": "required",
                "shipping_address_collection": {
                    "allowed_countries": SHIPPING_TO_COUNTRIES
                },
                "shipping_options": [
                    {"shipping_rate": rate} for rate in SHIPPING_RATES.keys()
                ],
            }

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price, "quantity": 1}],
            mode=mode,
            success_url=CARDSHOP_API_URL
            + "/shop/stripe/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=SHOP_PUBLIC_URL,
            customer=customer,
            customer_email=email if customer is None else None,
            customer_creation="always",
            metadata={"name": name, "product": product, "mode": mode, "price": price},
            allow_promotion_codes=True,
            **tax_details,
            **shipping_details,
        )
        return jsonify({"id": session.id})
    except Exception as exc:
        print(exc)
        return jsonify(error=str(exc)), 403


def register_user_on_crm(
    email: str, first_name: str | None, last_name: str | None, product: str
):
    auth = HTTPBasicAuth(CRM_USERNAME, CRM_PASSWORD)
    crm_url = "https://kiwix.org/wp-json/fluent-crm/v2/subscribers"

    def get_user_id(email: str) -> int | None:
        resp = requests.get(
            f"{crm_url}/0",
            auth=auth,
            params={"get_by_email": email},
            timeout=3,
            allow_redirects=True,
        )
        if resp.status_code != HTTPStatus.OK:
            return None
        try:
            return int(resp.json()["subscriber"]["id"])
        except Exception as exc:
            logger.error(f"Failed to query CRM status for {email}")
            logger.exception(exc)
            return None

    def create_user(email: str, first_name: str | None, last_name: str | None) -> int:
        payload: dict[str, str | list[str]] = {"email": email, "status": "subscribed"}
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        resp = requests.post(f"{crm_url}", auth=auth, json=payload, timeout=3)
        resp.raise_for_status()
        return resp.json()["contact"]["id"]

    def update_user(
        user_id: int,
        first_name: str | None,
        last_name: str | None,
        lists: list[str],
        tags: list[str],
    ):
        payload: dict[str, str | list[str]] = {
            "attach_lists": lists,
            "attach_tags": tags,
        }
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        resp = requests.put(
            f"{crm_url}/{user_id!s}", auth=auth, json=payload, timeout=3
        )
        resp.raise_for_status()

    lists = ["customers"]
    tags = []

    if product.endswith("-h1"):
        tags.append("h1-customer")
    elif "access" in product:
        tags.append("imager-customer")
    else:
        tags.append("os-only-customer")

    for tag in ("wikipedia", "prepper", "medical", "ted", "computer"):
        if tag in product:
            tags.append(tag)

    user_id = get_user_id(email)
    if not user_id:
        user_id = create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        logger.debug(f"Created CRM UID={user_id} for {email}")
    update_user(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        lists=lists,
        tags=tags,
    )
    logger.debug(f"Updated {email} with {lists[0]} and {', '.join(tags)}")


@blueprint.route("/webhook/checkout_succeeded", methods=["POST"])
def on_checkout_suceeded():
    """webhook inited on payment completed"""
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
        customer = (
            stripe.Customer.retrieve(session.customer)
            if session.get("customer")
            else None
        )
        try:
            update_cutomer(customer=customer, session=session)
        except Exception as exc:
            logger.error("Unable to update customer")
            logger.exception(exc)

        try:
            handler = get_handler(session["metadata"]["product"])
            handler(session=session, customer=customer)
        except Exception as exc:
            logger.critical("Unable to process handler")
            logger.exception(exc)
            return jsonify(success=False), 500

        try:
            register_user_on_crm(
                email=customer.email,
                first_name=customer.name,
                last_name=None,
                product=session["metadata"]["product"],
            )
        except Exception as exc:
            logger.error("Failed to add client to CRM")
            logger.exception(exc)
    else:
        print("Unhandled event type {}".format(event["type"]))
    return jsonify(success=True)


@blueprint.route("/success_email", methods=["GET"])
def success_email():
    """confirmation webpage on payment successful"""
    session_id = request.args.get("session_id")
    if not session_id:
        return flask.Response("No Session ID", 404)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer = (
            stripe.Customer.retrieve(session.customer)
            if session.get("customer")
            else None
        )
    except Exception as exc:
        logger.error(f"Unable to retrieve session & customer from Stripe: {exc}")
        logger.exception(exc)
        return flask.Response("Invalid Session ID", 400)

    product = session.metadata["product"]

    # record device-order specific info into DB
    shipping_rate = session.shipping_cost.shipping_rate
    if shipping_rate:
        shipping_option = SHIPPING_RATES[shipping_rate]
        shipping_option_name = stripe.ShippingRate.retrieve(shipping_rate).display_name
        shipping_with_tracking = SHIPPING_RATES[shipping_rate] == "with-tracking"
    else:
        shipping_option = shipping_option_name = shipping_with_tracking = None

    content = get_paid_email_content_for(
        kind=get_order_kind_for(product),
        email=customer.email,
        name=customer.name,
        timestamp=datetime.datetime.now(),
        product=product,
        product_name=get_product_name(product),
        price=session.amount_total,
        session=session,
        shipping_rate=shipping_rate,
        shipping_option=shipping_option,
        shipping_option_name=shipping_option_name,
        shipping_with_tracking=shipping_with_tracking,
    )

    return flask.Response(content)


@blueprint.route("/success", methods=["GET"])
def success():
    """confirmation webpage on payment successful"""
    session_id = request.args.get("session_id")
    if not session_id:
        return flask.Response("No Session ID", 404)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer = (
            stripe.Customer.retrieve(session.customer)
            if session.get("customer")
            else None
        )
    except Exception as exc:
        logger.error(f"Unable to retrieve session & customer from Stripe: {exc}")
        logger.exception(exc)
        return flask.Response("Invalid Session ID", 400)

    try:
        update_cutomer(customer=customer, session=session)
    except Exception as exc:
        logger.error("Unable to update customer")
        logger.exception(exc)

    if session.payment_status != "paid":
        logger.error(f"Session {session.id} is not paid: {session.payment_status}")
        return flask.Response("ERROR !!! not paid")

    context = {"customer": customer, "session": session, "shop_url": SHOP_PUBLIC_URL}
    product = session.metadata["product"]
    kind = get_order_kind_for(product)
    if kind == "image":
        http_url, torrent_url, _ = get_links_for(product)
        context.update({"http_url": http_url, "torrent_url": torrent_url})
    elif kind == "access":
        record = handle_credentials_creation(session=session, customer=customer)

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
    elif kind == "device":
        context.update(
            {
                "plug": get_plug_type(session.shipping_details.address.country),
                "invoice_num": short_stripe_id(session.id),
            }
        )

    context.update(
        {
            "kind": kind,
            "product": session.metadata["product"],
            "product_name": get_product_name(product),
            "price": session.amount_total,
        }
    )

    # debug only, execute handler on success to bypass stripe for
    # email testing
    if RUN_HANDLER_ON_SUCCESS:
        try:
            handler = get_handler(product)
            handler(session=session, customer=customer)
        except Exception as exc:
            logger.critical("Unable to process handler")
            logger.exception(exc)
            return jsonify(success=False), 500

    return flask.render_template(f"stripe/success_{kind}.html", **context)


@blueprint.route("/invoice.pdf", methods=["GET"])
def get_invoice():
    """confirmation webpage on payment successful"""
    session_id = request.args.get("session_id")
    if not session_id:
        return flask.Response("No Session ID", 404)

    invoice_path = build_invoice(session_id)
    resp = make_response(invoice_path.read_bytes(), 200)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{invoice_path.name}"'
    return resp


def build_invoice(session_id, *, as_html: bool = False, force: bool = False) -> Path:

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer = (
            stripe.Customer.retrieve(session.customer)
            if session.get("customer")
            else None
        )
    except Exception as exc:
        logger.error(f"Unable to retrieve session & customer from Stripe: {exc}")
        logger.exception(exc)
        return flask.Response("Invalid Session ID", 400)

    uid = short_stripe_id(session.id)
    ext = "html" if as_html else "pdf"
    fname = f"Invoice_{uid}.{ext}"
    fpath = INVOICE_DIR.joinpath(fname)

    if fpath.exists() and not force:
        return fpath

    product = session.metadata["product"]

    # record device-order specific info into DB
    shipping_rate = session.shipping_cost.shipping_rate
    if shipping_rate:
        shipping_option = SHIPPING_RATES[shipping_rate]
        shipping_option_name = stripe.ShippingRate.retrieve(shipping_rate).display_name
        shipping_with_tracking = SHIPPING_RATES[shipping_rate] == "with-tracking"
    else:
        shipping_option = shipping_option_name = shipping_with_tracking = None

    context = {
        "kind": get_order_kind_for(product),
        "timestamp": datetime.datetime.now(),
        "product": product,
        "product_name": get_product_name(product),
        "session": session,
        "shipping_rate": shipping_rate,
        "shipping_option": shipping_option,
        "shipping_option_name": shipping_option_name,
        "shipping_with_tracking": shipping_with_tracking,
        "shop_url": SHOP_PUBLIC_URL,
        "order": {
            "quantity": 1,
            "units": 1,
            "statuses": [],
            "recipient": {},
            "client": {},
            "sd_card": {},
            "config": {"branding": {}, "content": {}, "admin_account": {}},
        },
        "channel": {},
    }

    content = email_env.get_template("invoice.html").render(**context)

    if as_html:
        fpath.write_text(content)
        return fpath

    options = {
        "page-size": "A4",
        "encoding": "UTF-8",
        "custom-header": [("Accept-Encoding", "gzip")],
        "no-outline": None,
        "viewport-size": "1280x1024",
    }
    pdfkit.from_string(content, fpath, options=options)
    return fpath


@blueprint.route("/shipment", methods=["GET", "POST"])
def get_shipment():
    """WebUI to record shipping details"""

    if request.method == "GET":
        invoice_num = request.args.get("invoice_num")
        session_id = session = customer = session_record = None
        if invoice_num:
            session_record = StripeSession.get_or_none_from_inv(invoice_num)
            if session_record:
                session_id = session_record["session_id"]

        return flask.render_template(
            "assembly_add_shipment.html",
            invoice_num=invoice_num,
            session_id=session_id,
            session=session,
            customer=customer,
            url_template=TRACKING_URL_TMPL,
            record=session_record,
            plug_types=PLUG_TYPES.keys(),
        )

    if request.method == "POST":
        session_id = request.form.get("session_id")
        tracking_number = request.form.get("tracking_number")
        power_plug = request.form.get("power_plug")
        serial_number = request.form.get("serial_number")
        if not session_id:
            return flask.Response("No Session ID", 400)
        if not tracking_number or not tracking_number.strip():
            return flask.Response("No Tracking number", 400)
        if not power_plug:
            return flask.Response("No Power Plug", 400)
        if not serial_number:
            return flask.Response("No Serial Number", 400)
        if not is_valid_serial(serial_number):
            return flask.Response("Invalid Serial Number", 400)

        session_record = StripeSession.get_or_none(session_id)
        if not session_record:
            return flask.Response("Invalid Session ID", 400)
        if power_plug not in PLUG_TYPES:
            return flask.Response("Invalid Power Plug", 400)

        tracking_url = get_tracking_url(tracking_number)
        shipped_on = datetime.datetime.now()

        StripeSession.update(
            record_id=session_record["_id"],
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            shipped_on=shipped_on,
            shipped_plug=power_plug,
            serial_number=serial_number,
        )

        # refresh record from DB
        session_record = StripeSession.get_or_none(session_id)

        # send recipient an email
        product = session_record["product"]
        subject = f"Your Kiwix Hotspot is on its way! ({session_record['invoice_num']})"
        content = email_env.get_template("stripe/shipped_device.html").render(
            record=session_record,
            product=session_record["product"],
            product_name=get_product_name(product),
        )

        # dev to work on email design
        # return flask.Response(content)

        email_id = send_email(
            to=session_record["email"],
            subject=subject,
            contents=content,
            copy_support=False,
            on=datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(days=1),
        )

        StripeSession.update(
            record_id=session_record["_id"], shipping_email_id=email_id
        )

        return flask.redirect(
            f"{flask.url_for('stripe.get_shipment')}"
            f"?invoice_num={session_record['invoice_num']}"
        )
