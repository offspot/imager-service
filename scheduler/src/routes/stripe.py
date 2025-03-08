import datetime
import json
import logging
import os

import flask
import requests
import stripe
from babel.dates import format_datetime
from emailing import send_email
from flask import Blueprint, jsonify, request
from jinja2 import Environment, FileSystemLoader, select_autoescape
from utils.mongo import AutoImages, StripeCustomer, StripeSession
from utils.templates import amount_str, country_name, strftime

# envs & secrets
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_PUBLIC_API_KEY = os.getenv("STRIPE_PUBLIC_API_KEY")
CARDSHOP_API_URL = os.getenv("CARDSHOP_API_URL", "https://api.imager.kiwix.org")
SHOP_PUBLIC_URL = os.getenv("SHOP_PUBLIC_URL", "https://kiwix.org/en/wifi-hotspot/")
MANAGER_API_URL = os.getenv("MANAGER_API_URL", "https://imager.kiwix.org")
MANAGER_ACCOUNTS_API_TOKEN = os.getenv("MANAGER_ACCOUNTS_API_TOKEN")

RUN_HANDLER_ON_SUCCESS = bool(os.getenv("RUN_HANDLER_ON_SUCCESS"))

SHIPPING_RATES = {
    # order matters ; first one is auto-selected
    os.environ["SHIPPING_RATE_NOTRACKING"]: "without-tracking",
    os.environ["SHIPPING_RATE_TRACKING"]: "with-tracking",
}

TAXES_ENABLED = bool(os.getenv("TAXES_ENABLED") or "")

PLUG_TYPES = {
    "UK": ["GB", "IE", "MT", "CY", "MY", "SG"],
    "US": ["US", "CA", "JP", "MX"],
}

SHIPPING_TO_COUNTRIES = [
    "AD",
    "AE",
    "AF",
    "AG",
    "AI",
    "AL",
    "AM",
    "AO",
    "AQ",
    "AR",
    "AT",
    "AU",
    "AW",
    "AX",
    "AZ",
    "BA",
    "BB",
    "BD",
    "BE",
    "BF",
    "BG",
    "BH",
    "BI",
    "BJ",
    "BL",
    "BM",
    "BN",
    "BO",
    "BQ",
    "BR",
    "BS",
    "BT",
    "BV",
    "BW",
    "BY",
    "BZ",
    "CA",
    "CD",
    "CF",
    "CG",
    "CH",
    "CI",
    "CK",
    "CL",
    "CM",
    "CN",
    "CO",
    "CR",
    "CV",
    "CW",
    "CY",
    "CZ",
    "DE",
    "DJ",
    "DK",
    "DM",
    "DO",
    "DZ",
    "EC",
    "EE",
    "EG",
    "EH",
    "ER",
    "ES",
    "ET",
    "FI",
    "FJ",
    "FK",
    "FO",
    "FR",
    "GA",
    "GB",
    "GD",
    "GE",
    "GF",
    "GG",
    "GH",
    "GI",
    "GL",
    "GM",
    "GN",
    "GP",
    "GQ",
    "GR",
    "GS",
    "GT",
    "GU",
    "GW",
    "GY",
    "HK",
    "HN",
    "HR",
    "HT",
    "HU",
    "ID",
    "IE",
    "IL",
    "IM",
    "IN",
    "IO",
    "IQ",
    "IS",
    "IT",
    "JE",
    "JM",
    "JO",
    "JP",
    "KE",
    "KG",
    "KH",
    "KI",
    "KM",
    "KN",
    "KR",
    "KW",
    "KY",
    "KZ",
    "LA",
    "LB",
    "LC",
    "LI",
    "LK",
    "LR",
    "LS",
    "LT",
    "LU",
    "LV",
    "LY",
    "MA",
    "MC",
    "MD",
    "ME",
    "MF",
    "MG",
    "MK",
    "ML",
    "MM",
    "MN",
    "MO",
    "MQ",
    "MR",
    "MS",
    "MT",
    "MU",
    "MV",
    "MW",
    "MX",
    "MY",
    "MZ",
    "NA",
    "NC",
    "NE",
    "NG",
    "NI",
    "NL",
    "NO",
    "NP",
    "NR",
    "NU",
    "NZ",
    "OM",
    "PA",
    "PE",
    "PF",
    "PG",
    "PH",
    "PK",
    "PL",
    "PM",
    "PN",
    "PR",
    "PS",
    "PT",
    "PY",
    "QA",
    "RE",
    "RO",
    "RS",
    "RU",
    "RW",
    "SA",
    "SB",
    "SC",
    "SD",
    "SE",
    "SG",
    "SH",
    "SI",
    "SJ",
    "SK",
    "SL",
    "SM",
    "SN",
    "SO",
    "SR",
    "SS",
    "ST",
    "SV",
    "SX",
    "SZ",
    "TC",
    "TD",
    "TF",
    "TG",
    "TH",
    "TJ",
    "TK",
    "TL",
    "TM",
    "TN",
    "TO",
    "TR",
    "TT",
    "TV",
    "TW",
    "TZ",
    "UA",
    "UG",
    "US",
    "UY",
    "UZ",
    "VA",
    "VC",
    "VE",
    "VG",
    "VN",
    "VU",
    "WF",
    "WS",
    "YE",
    "YT",
    "ZA",
    "ZM",
    "ZW",
]

# i18n
LANG_STRINGS = {
    "en": {
        "product_wikipedia": "Wikipedia Hotspot Image English",
        "product_ted": "TED Hotspot Image",
        "product_preppers": "Preppers Hotspot Image",
        "product_medical": "Medical Hotspot Image",
        "product_computers": "Computer Hotspot Image",
        "product_access_1m": "One month Imager Access",
        "product_access_1y": "Annual Imager Access",
        "product_wikipedia-h1": "Wikipedia Hotspot English",
        "product_ted-h1": "TED Hotspot",
        "product_preppers-h1": "Preppers Hotspot",
        "product_medical-h1": "Medical Hotspot",
        "product_computers-h1": "Computer Hotspot",
    },
    "de": {
        "product_wikipedia": "Wikipedia Hotspot auf Deutsch",
        "product_ted": "TED Hotspot",
        "product_preppers": "Preppers Hotspot",
        "product_medical": "Medical Hotspot",
        "product_computers": "Computer Hotspot",
        "product_access_1m": "One month Imager Access",
        "product_access_1y": "Annual Imager Access",
        "product_wikipedia-h1": "Wikipedia Hotspot English",
        "product_ted-h1": "TED Hotspot",
        "product_preppers-h1": "Preppers Hotspot",
        "product_medical-h1": "Medical Hotspot",
        "product_computers-h1": "Computer Hotspot",
    },
    "es": {
        "product_wikipedia": "Wikipedia Hotspot en español",
        "product_ted": "TED Hotspot",
        "product_preppers": "Preppers Hotspot",
        "product_medical": "Medical Hotspot",
        "product_computers": "Computer Hotspot",
        "product_access_1m": "One month Imager Access",
        "product_access_1y": "Annual Imager Access",
        "product_wikipedia-h1": "Wikipedia Hotspot English",
        "product_ted-h1": "TED Hotspot",
        "product_preppers-h1": "Preppers Hotspot",
        "product_medical-h1": "Medical Hotspot",
        "product_computers-h1": "Computer Hotspot",
    },
    "fr": {
        "product_wikipedia": "Wikipedia Hotspot Français",
        "product_ted": "TED Hotspot",
        "product_preppers": "Preppers Hotspot",
        "product_medical": "Medical Hotspot",
        "product_computers": "Computer Hotspot",
        "product_access_1m": "Accès Imager 1 mois",
        "product_access_1y": "Accès Imager annuel",
        "product_wikipedia-h1": "Wikipedia Hotspot English",
        "product_ted-h1": "TED Hotspot",
        "product_preppers-h1": "Preppers Hotspot",
        "product_medical-h1": "Medical Hotspot",
        "product_computers-h1": "Computer Hotspot",
    },
}


def format_dt(date, fmt="d MMMM yyyy, H:m", locale=None):
    return format_datetime(date, fmt, locale="en")


def get_plug_type(country_code):
    for kind, countries in PLUG_TYPES.items():
        if country_code in countries:
            return kind
    return "EU"


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
    **kwargs,
):
    """Sends email receipt to customer. Calls `prepare_order`."""
    subject = "Your Kiwix receipt"
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
        subject=subject,
        contents=content,
        copy_support=False,
    )


def get_order_kind_for(product):
    if product.startswith("wikipedia-") or product in (
        "preppers",
        "computers",
        "ted",
        "medical",
    ):
        return "image"
    elif product.startswith("access"):
        return "access"
    elif product.endswith("-h1"):
        return "device"

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
    product_lang = "en"

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
        },
        amount={
            "product": session.amount_subtotal,
            "shipping": session.total_details.amount_shipping,
            "tax": session.total_details.amount_tax,
            "total": session.amount_total,
        },
    )

    # send receipt email
    email_id = send_paid_order_email(
        kind="device",
        email=customer.email,
        name=customer.name,
        timestamp=datetime.datetime.now(),
        product=product,
        product_name=LANG_STRINGS[product_lang][f"product_{product}"],
        price=session.amount_total,
        session=session,
        shipping_option=shipping_option,
        shipping_option_name=shipping_option_name,
        shipping_with_tracking=shipping_with_tracking,
    )

    StripeSession.update(
        record_id=session_record["_id"], receipt_sent=True, email_id=email_id
    )


def handle_image_order(session, customer):
    product = session.metadata.get("product")
    http_url, torrent_url, _ = get_links_for(product)
    product_lang = product.split("-")[-1]

    email_id = send_paid_order_email(
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
        customer_id=customer.id,
        session_id=session.id,
        product=product,
        receipt_sent=True,
        email_id=email_id,
        http_url=http_url,
    )


def handle_access_order(session, customer):
    now = datetime.datetime.now()
    product_dc = session.metadata["product"].split("-")[-1]
    record = handle_credentials_creation(session=session, customer=customer)

    # send email receipt
    email_id = send_paid_order_email(
        kind="access",
        email=customer.email,
        name=customer.name,
        timestamp=now,
        product=session.metadata["product"],
        product_name=LANG_STRINGS["en"].get(
            f"product_access_{product_dc}", "Imager Access"
        ),
        price=session.amount_total,
        username=record.get("username", "Unavailable – please contact us"),
        password=record.get("password", "Unavailable – please contact us"),
        existing_account=record.get("existing_account", False),
        expire_on=record.get("expiry"),
        recurring=record.get("recurring"),
    )
    StripeSession.update(record_id=record["_id"], receipt_sent=True, email_id=email_id)


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
    "preppers": (
        os.getenv("STRIPE_METHOD_PP"),
        os.getenv("STRIPE_PRICE_PP"),
        handle_image_order,
    ),
    "medical": (
        os.getenv("STRIPE_METHOD_MD"),
        os.getenv("STRIPE_PRICE_MD"),
        handle_image_order,
    ),
    "ted": (
        os.getenv("STRIPE_METHOD_TED"),
        os.getenv("STRIPE_PRICE_TED"),
        handle_image_order,
    ),
    "computers": (
        os.getenv("STRIPE_METHOD_CS"),
        os.getenv("STRIPE_PRICE_CS"),
        handle_image_order,
    ),
    "access-1m": (
        os.getenv("STRIPE_METHOD_ACCESS1M"),
        os.getenv("STRIPE_PRICE_ACCESS1M"),
        handle_access_order,
    ),
    # "access-1y": (
    #     os.getenv("STRIPE_METHOD_ACCESS1Y"),
    #     os.getenv("STRIPE_PRICE_ACCESS1Y"),
    #     handle_access_order,
    # ),
    "wikipedia-en-h1": (
        os.getenv("STRIPE_METHOD_WPH1"),
        os.getenv("STRIPE_PRICE_WPENH1"),
        handle_device_order,
    ),
    "preppers-h1": (
        os.getenv("STRIPE_METHOD_PPH1"),
        os.getenv("STRIPE_PRICE_PPH1"),
        handle_device_order,
    ),
    "medical-h1": (
        os.getenv("STRIPE_METHOD_MDH1"),
        os.getenv("STRIPE_PRICE_MDH1"),
        handle_device_order,
    ),
    "ted-h1": (
        os.getenv("STRIPE_METHOD_TEDH1"),
        os.getenv("STRIPE_PRICE_TEDH1"),
        handle_device_order,
    ),
    "computers-h1": (
        os.getenv("STRIPE_METHOD_CSH1"),
        os.getenv("STRIPE_PRICE_CSH1"),
        handle_device_order,
    ),
}


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
        "lang": lang,
        "api_url": CARDSHOP_API_URL,
        "translation": LANG_STRINGS.get(lang),
        "stripe_public_key": STRIPE_PUBLIC_API_KEY,
    }
    return flask.render_template("stripe/shop.html", **context)


@blueprint.route("/create-session", methods=["POST"])
def create_checkout_session():
    """create a Stripe session for an order and return its id as json"""
    name = request.form.get("name")
    email = request.form.get("email")
    product = request.form.get("product")
    if product not in PRODUCTS.keys():
        return jsonify(error="Unknown product"), 404
    mode, price, _ = PRODUCTS.get(product)

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
            metadata={"name": name, "product": product, "mode": mode, "price": price},
            **tax_details,
            **shipping_details,
        )
        return jsonify({"id": session.id})
    except Exception as exc:
        print(exc)
        return jsonify(error=str(exc)), 403


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
        customer = stripe.Customer.retrieve(session["customer"])
        try:
            update_cutomer(customer=customer, session=session)
        except Exception as exc:
            logger.error("Unable to update customer")
            logger.exception(exc)

        try:
            handler = PRODUCTS[session["metadata"]["product"]][2]
            handler(session=session, customer=customer)
        except Exception as exc:
            logger.critical("Unable to process handler")
            logger.exception(exc)
            return jsonify(success=False), 500
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
        customer = stripe.Customer.retrieve(session.get("customer"))
    except Exception as exc:
        logger.error(f"Unable to retrieve session & customer from Stripe: {exc}")
        logger.exception(exc)
        return flask.Response("Invalid Session ID", 400)

    product = session.metadata.get("product")
    product_lang = "en"

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
        product_name=LANG_STRINGS[product_lang][f"product_{product}"],
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
        customer = stripe.Customer.retrieve(session.get("customer"))
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
    product = session.metadata.get("product")
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

    context.update(
        {
            "kind": kind,
            "product": session.metadata["product"],
            "product_name": LANG_STRINGS["en"].get(f"product_{product}", "Unknown"),
            "price": session.amount_total,
        }
    )

    # debug only, execute handler on success to bypass stripe for
    # email testing
    if RUN_HANDLER_ON_SUCCESS:
        try:
            handler = PRODUCTS[product][2]
            handler(session=session, customer=customer)
        except Exception as exc:
            logger.critical("Unable to process handler")
            logger.exception(exc)
            return jsonify(success=False), 500

    return flask.render_template(f"stripe/success_{kind}.html", **context)
