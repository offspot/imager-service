#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import logging

import pdfkit
import yagmail
import requests
from werkzeug.datastructures import MultiDict
from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils.mongo import Orders, Users, Channels, WriterTasks
from utils.templates import (
    get_id,
    country_name,
    linebreaksbr,
    yesno,
    language_name,
    b64qrcode,
    get_pub_url,
    get_insert_card_url,
    get_add_shipment_url,
)

logger = logging.getLogger(__name__)
jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml", "txt"]),
)
jinja_env.filters["id"] = get_id
jinja_env.filters["yesno"] = yesno
jinja_env.filters["qrcode"] = b64qrcode
jinja_env.filters["pub_url"] = get_pub_url
jinja_env.filters["insert_card_url"] = get_insert_card_url
jinja_env.filters["add_shipment_url"] = get_add_shipment_url
jinja_env.filters["country"] = country_name
jinja_env.filters["language"] = language_name
jinja_env.filters["linebreaksbr"] = linebreaksbr


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
    to, subject, contents, cc=[], bcc=[], headers={}, attachments=[]
):
    yag = get_sender()
    if attachments:
        if not isinstance(contents, list):
            contents = [contents]
        contents += attachments
    yag.send(to=to, cc=cc, bcc=bcc, headers=headers, subject=subject, contents=contents)


def send_email_via_api(
    to, subject, contents, cc=[], bcc=[], headers={}, attachments=[]
):
    values = [
        ("from", os.getenv("MAIL_FROM", "cardshop@kiwix.org")),
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
    print(attachments)

    req = requests.post(
        url=os.getenv("MAILGUN_API_URL") + "/messages",
        auth=("api", os.getenv("MAILGUN_API_KEY")),
        data=data,
        files=[
            ("attachment", (os.path.basename(fpath), open(fpath, "rb").read()))
            for fpath in attachments
        ],
    )
    req.raise_for_status()


def send_email(to, subject, contents, cc=[], bcc=[], headers={}, attachments=[]):
    logger.info("sending --{}-- to --{}--/--{}".format(subject, to, attachments))
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
            headers=headers,
            attachments=attachments,
        )
    except Exception as exp:
        logger.error("Unable to send email: {}".format(exp))
        logger.exception(exp)


def get_full_context(order_id, extra={}):
    order = Orders().get_with_tasks(order_id, {"logs": 0})
    order.update(
        {
            "id": order_id,
            "status": order["statuses"][-1],
            "min_id": order_id[:8] + order_id[-3:],
        }
    )
    context = {"order": order}
    context.update(extra)
    return context


def get_order_status_update_template(status):
    return "email_order_{}.html".format(status)


def get_email_for(order_id, kind, formatted=True):
    def _fmt(name, email):
        return "{name} <{email}>".format(name=name, email=email)

    if kind not in ("client", "recipient", "operator"):
        return None

    order = Orders.get_with_tasks(order_id, {"logs": 0})
    if kind == "client":
        return _fmt(order["client"]["name"], order["client"]["email"])

    if kind == "recipient":
        return _fmt(order["recipient"]["name"], order["recipient"]["email"])

    if kind == "operator":
        worker = Users().by_username(order["tasks"]["download"]["worker"])
        return worker["email"]


def send_order_email_for(
    order_id,
    subject_tmpl,
    content_tmpl,
    to,
    cc=None,
    bcc=None,
    attachments=[],
    extra={},
):
    context = get_full_context(str(order_id), extra=extra)

    subject = jinja_env.get_template("{}.txt".format(subject_tmpl)).render(**context)
    content = jinja_env.get_template("{}.html".format(content_tmpl)).render(**context)
    send_email(
        to=get_email_for(order_id, kind=to),
        subject=subject,
        contents=content,
        cc=get_email_for(order_id, kind=cc),
        bcc=get_email_for(order_id, kind=bcc),
        attachments=attachments,
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
