import logging
import os
import pathlib
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Optional

import pdfkit
import requests
import yagmail
import yaml
from babel.dates import format_datetime
from babel.support import Translations
from jinja2 import Environment, FileSystemLoader, select_autoescape
from utils.mongo import Acknowlegments, Channels, Orders, Users, WriterTasks
from utils.templates import (
    b64qrcode,
    country_name,
    get_add_shipment_url,
    get_id,
    get_insert_card_url,
    get_pub_url,
    get_public_download_torrent_url,
    get_public_download_url,
    language_name,
    linebreaksbr,
    public_download_url_has_torrent,
    yesno,
)
from werkzeug.datastructures import MultiDict

try:
    from yaml import CDumper as Dumper
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    # we don't NEED cython ext but it's faster so use it if avail.
    from yaml import Dumper, SafeLoader

logger = logging.getLogger(__name__)


locale_dir = pathlib.Path(__file__).parent.joinpath("locale")
jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml", "txt"]),
    extensions=["jinja2.ext.i18n", "jinja2.ext.autoescape", "jinja2.ext.with_"],
)


def format_dt(date, fmt="long", locale=None):
    return format_datetime(
        date, fmt, locale=locale or getattr(jinja_env, "_locale", "en_GB")
    )


jinja_env.filters["id"] = get_id
jinja_env.filters["yesno"] = yesno
jinja_env.filters["qrcode"] = b64qrcode
jinja_env.filters["pub_url"] = get_pub_url
jinja_env.filters["insert_card_url"] = get_insert_card_url
jinja_env.filters["add_shipment_url"] = get_add_shipment_url
jinja_env.filters["public_download_url"] = get_public_download_url
jinja_env.filters["public_download_torrent_url"] = get_public_download_torrent_url
jinja_env.filters["public_download_url_has_torrent"] = public_download_url_has_torrent
jinja_env.filters["country"] = country_name
jinja_env.filters["language"] = language_name
jinja_env.filters["linebreaksbr"] = linebreaksbr
jinja_env.filters["date"] = format_dt


CLIENT_EMAIL_STATUSES = [
    Orders.created,
    Orders.creation_failed,
    Orders.pending_writer,
    Orders.writing,
    Orders.write_failed,
    Orders.shipped,
    Orders.canceled,
    Orders.failed,
]

RECIPIENT_EMAIL_STATUSES = [Orders.shipped]

FAILED_ORDER_EMAIL = os.getenv("FAILED_ORDER_EMAIL")


@contextmanager
def localized_for(lang, *args, **kwargs):
    translations = Translations.load(locale_dir, [lang])
    if lang == "en":
        lang == "en_GB"
    try:
        jinja_env._locale = lang
        yield jinja_env.install_gettext_translations(translations)
    finally:
        jinja_env.uninstall_gettext_translations(translations)
        jinja_env._locale = "en_GB"


def get_sender():
    enctype = os.getenv("SMTP_ENCTYPE", "tls").lower()
    port = os.getenv("SMTP_PORT", "auto").lower()
    return yagmail.SMTP(
        user=os.getenv("SMTP_USERNAME"),
        password=os.getenv("SMTP_PASSWORD"),
        host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        port=None if port == "auto" else int(port),
        smtp_starttls=enctype in ("tls", "auto"),
        smtp_ssl=enctype == "ssl",
        smtp_set_debuglevel=0,
        smtp_skip_login=bool(os.getenv("SMTP_SKIP_LOGIN", False)),
    )


def send_email_via_smtp(
    to,
    subject,
    contents,
    cc: Optional[Sequence] = None,
    bcc: Optional[Sequence] = None,
    headers: Optional[dict] = None,
    attachments: Optional[Sequence] = None,
):
    yag = get_sender()
    if attachments:
        if not isinstance(contents, list):
            contents = [contents]
        contents += attachments
    yag.send(to=to, cc=cc, bcc=bcc, headers=headers, subject=subject, contents=contents)


def send_email_via_api(
    to,
    subject,
    contents,
    cc: Optional[Sequence] = None,
    bcc: Optional[Sequence] = None,
    headers: Optional[dict] = None,
    attachments: Optional[Sequence] = None,
):
    values = [
        ("from", os.getenv("MAIL_FROM", "imager@kiwix.org")),
        ("subject", subject),
        ("html", contents),
    ]
    values += [
        ("to", value) for value in (to if isinstance(to, (list, tuple)) else [to])
    ]
    values += [
        ("cc", value) for value in (cc if isinstance(cc, (list, tuple)) else [cc])
    ]
    values += [
        ("bcc", value) for value in (bcc if isinstance(bcc, (list, tuple)) else [bcc])
    ]
    data = MultiDict(values)

    resp = requests.post(
        url=os.getenv("MAILGUN_API_URL") + "/messages",
        auth=("api", os.getenv("MAILGUN_API_KEY")),
        data=data,
        files=(
            [
                ("attachment", (os.path.basename(fpath), open(fpath, "rb").read()))
                for fpath in attachments
            ]
            if attachments
            else []
        ),
    )
    resp.raise_for_status()
    return resp.json().get("id")


def send_email(
    to,
    subject,
    contents,
    cc: Optional[Sequence] = None,
    bcc: Optional[Sequence] = None,
    headers: Optional[dict] = None,
    attachments: Optional[Sequence] = None,
    copy_support=True,
):

    to = [to] if isinstance(to, str) else to
    cc = ([cc] if isinstance(cc, str) else cc) or []
    bcc = ([bcc] if isinstance(bcc, str) else bcc) or []

    # bcc SUPPORT_EMAIL to every message
    if copy_support and os.getenv("SUPPORT_EMAIL"):
        bcc.append(os.getenv("SUPPORT_EMAIL"))

    logger.info(f"sending --{subject}-- to --{to}--/--{attachments}")
    func = (
        send_email_via_api
        if os.getenv("MAILGUN_API_KEY", False)
        else send_email_via_smtp
    )
    # make sure we don't send message to same address twice
    cc = [a for a in cc if a not in to]
    bcc = [a for a in bcc if a not in to and a not in cc]
    try:
        return func(
            to=to,
            subject=subject,
            contents=contents,
            cc=cc,
            bcc=bcc,
            headers=headers or {},
            attachments=attachments or [],
        )
    except Exception as exp:
        logger.error("Unable to send email: {}".format(exp))
        logger.exception(exp)


def get_full_context(order_id, extra: Optional[dict] = None):
    order = Orders().get_with_tasks(order_id, {"logs": 0})
    order.update(
        {
            "id": order_id,
            "status": order["statuses"][-1],
            "min_id": order_id[:8] + order_id[-3:],
        }
    )
    context = {"order": order}
    if extra:
        context.update(extra)
    return context


def get_order_status_update_template(status):
    return "email_order_{}.html".format(status)


def get_email_for(order_id, kind, formatted=True):
    def _fmt(name, email):
        return "{name} <{email}>".format(name=name, email=email)

    if kind not in ("client", "recipient", "operator", "error-manager"):
        return None, "en_GB"

    if kind == "error-manager" and FAILED_ORDER_EMAIL:
        return _fmt("Imager Error Manager", FAILED_ORDER_EMAIL), "en_GB"

    order = Orders.get_with_tasks(order_id, {"logs": 0})
    if kind == "client":
        return (
            _fmt(order["client"]["name"], order["client"]["email"]),
            order["client"]["language"],
        )

    if kind == "recipient":
        return (
            _fmt(order["recipient"]["name"], order["recipient"]["email"]),
            order["recipient"]["language"],
        )

    if kind == "operator":
        worker = Users().by_username(order["tasks"]["download"]["worker"])
        return worker["email"], "en_GB"
    return None, "en_GB"


def get_dashboard_entries(yaml_text):

    payload = yaml.load(yaml_text, Loader=SafeLoader)
    content = {}
    for file in payload.get("files", []):
        if not isinstance(file, dict):
            continue
        if file.get("to", "") == "/data/contents/dashboard.yaml":
            content = yaml.load(file["content"], Loader=SafeLoader)
            break

    return [
        (package["title"], package["description"])
        for package in content.get("packages", [])
    ]


def send_order_email_for(
    order_id,
    subject_tmpl,
    content_tmpl,
    to,
    cc: Optional[Sequence] = None,
    bcc: Optional[Sequence] = None,
    attachments: Optional[Sequence] = None,
    extra: Optional[dict] = None,
):
    to, lang = get_email_for(order_id, kind=to)
    with localized_for(lang):
        context = get_full_context(str(order_id), extra=extra)
        try:
            context["order_entries"] = get_dashboard_entries(
                context["order"]["config_yaml"]
            )
        except:
            context["order_entries"] = context["order"]["config"]["content"]["zims"]

        subject = jinja_env.get_template("{}.txt".format(subject_tmpl)).render(
            **context
        )
        content = jinja_env.get_template("{}.html".format(content_tmpl)).render(
            **context
        )

    cc = ([cc] if isinstance(cc, str) else cc) or []
    bcc = ([bcc] if isinstance(bcc, str) else bcc) or []
    send_email(
        to=to,
        subject=subject,
        contents=content,
        cc=[get_email_for(order_id, kind=item)[0] for item in cc],
        bcc=[get_email_for(order_id, kind=item)[0] for item in bcc],
        attachments=attachments or {},
    )


def send_order_created_email(order_id):
    # recipient, client (cc): order accepted ; you'll be notified of shipment
    send_order_email_for(
        order_id, "subject_order_new", "recipient_order_created", "recipient", "client"
    )


def send_order_failed_email(order_id):
    # recipient: order failed. you'll be refunded and contacted by client
    send_order_email_for(
        order_id,
        "subject_order_failed",
        "recipient_order_failed",
        "recipient",
        "client",
        "error-manager",
    )

    # operator: download/write failed, please check conn and SD and contact client
    order = Orders().get_with_tasks(order_id, {"logs": 0})
    if order["tasks"].get("write") and order["tasks"]["write"]["status"] in (
        WriterTasks.failed_to_download,
        WriterTasks.failed_to_write,
    ):

        send_order_email_for(
            order_id, "subject_order_failed", "operator_order_failed", "operator"
        )


def send_image_uploaded_email(order_id):
    # client: image creation successful.
    send_order_email_for(
        order_id, "subject_image_uploaded", "client_image_uploaded", "client"
    )


def send_image_uploaded_public_email(order_id):
    # client: image creation successful.
    send_order_email_for(
        order_id,
        "subject_image_uploaded_public",
        "recipient_image_uploaded_public",
        "recipient",
        "client",
    )


def send_insert_card_email(order_id, task_id):
    # operator: please insert XXGB SD card onto
    write_task = WriterTasks.get(task_id)
    send_order_email_for(
        order_id,
        "subject_insert_card",
        "operator_insert_card",
        "operator",
        extra={"task": write_task},
    )


def send_image_writing_email(order_id, task_id):
    # operator: thank you ; write started
    write_task = WriterTasks.get(task_id)
    send_order_email_for(
        order_id,
        "subject_card_inserted",
        "operator_card_inserted",
        "operator",
        extra={"task": write_task},
    )


def send_image_written_email(order_id, task_id):
    # client: image writing successful.
    write_task = WriterTasks.get(task_id)
    send_order_email_for(
        order_id,
        "subject_image_written",
        "operator_image_written",
        "operator",
        extra={"task": write_task},
    )


def send_order_pending_shipment_email(order_id):
    # operator: please ship SD card from X to YY
    attachments = [build_shipping_document(order_id)]
    send_order_email_for(
        order_id,
        "subject_ship_card",
        "operator_ship_card",
        "operator",
        attachments=attachments,
    )


def send_order_shipped_email(order_id):
    # recipient, client (cc): SD card shipped.
    send_order_email_for(
        order_id,
        "subject_order_shipped",
        "recipient_order_shipped",
        "recipient",
        "client",
    )


def send_worker_sos_email(ack_id):
    # client: image writing successful.
    ack = Acknowlegments.get(ack_id)
    context = {"ack": ack}
    subject = jinja_env.get_template("subject_worker_sos.txt").render(**context)
    content = jinja_env.get_template("operator_worker_sos.html").render(**context)
    send_email(
        to=Users().by_username(ack["username"])["email"],
        subject=subject,
        contents=content,
    )


def build_shipping_document(order_id):
    order = Orders().get(order_id, {"logs": 0})
    channel = Channels().get(order["channel"])
    context = get_full_context(str(order_id), extra={"channel": channel})
    context.update({"cwd": os.path.abspath(".")})

    fname = "Shipping_{oid}.pdf".format(oid=context["order"]["min_id"])
    fpath = os.path.join(os.getenv("TMP_DIR", "/tmp"), fname)

    content = jinja_env.get_template("shipping.html").render(**context)
    options = {
        "page-size": "A4",
        "encoding": "UTF-8",
        "custom-header": [("Accept-Encoding", "gzip")],
        "no-outline": None,
        "viewport-size": "1280x1024",
    }
    pdfkit.from_string(content, fpath, options=options)
    return fpath
