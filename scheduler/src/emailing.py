#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import logging

import yagmail
import requests
from werkzeug.datastructures import MultiDict
from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils.mongo import Orders

logger = logging.getLogger(__name__)
jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml", "txt"]),
)


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


def send_email_via_smtp(to, subject, contents, cc=None, bcc=None, headers=None):
    yag = get_sender()
    yag.send(to=to, cc=cc, bcc=bcc, headers=headers, subject=subject, contents=contents)


def send_email_via_api(to, subject, contents, cc=None, bcc=None, headers={}):
    values = [
        ("from", os.getenv("MAIL_FROM", "cardshop@kiwix.org")),
        ("subject", subject),
        ("text", contents),
    ]
    tos = to if isinstance(to, (list, tuple)) else [to]
    values += [("to", value) for value in tos]
    values += [("cc", value) for value in cc] if cc is not None else []
    values += [("bcc", value) for value in bcc] if bcc is not None else []
    data = MultiDict(values)

    req = requests.post(
        url=os.getenv("MAILGUN_API_URL") + "/messages",
        auth=("api", os.getenv("MAILGUN_API_KEY")),
        data=data,
    )
    req.raise_for_status()


def send_email(to, subject, contents, cc=None, bcc=None, headers=None):
    func = (
        send_email_via_api
        if os.getenv("MAILGUN_API_KEY", False)
        else send_email_via_smtp
    )
    try:
        return func(to, subject, contents, cc, bcc, headers)
    except Exception as exp:
        logger.error("Unable to send email: {}".format(exp))
        logger.exception(exp)


def contextualize_order(order):
    order.update({"id": order.get("_id"), "status": order.get("statuses")[-1]})
    return order


def get_order_status_update_template(status):
    return "email_order_{}.html".format(status)


def send_order_created_email(order_id):
    order = Orders().find_one({"_id": order_id}, {"logs": 0})
    context = {"order": contextualize_order(order)}
    to = [order["client"]["email"], order["recipient"]["email"]]
    subject_tmpl = jinja_env.get_template("subject_order_new.txt")
    subject = subject_tmpl.render(**context)
    content_tmpl = jinja_env.get_template("email_order_created.html")
    content = content_tmpl.render(**context)

    send_email(to=to, subject=subject, contents=content)


def send_order_update_email(order_id):
    order = Orders().find_one({"_id": order_id}, {"logs": 0})
    status = order.get("statuses")[-1]
    context = {"order": contextualize_order(order)}
    to = order["client"]["email"]
    subject_tmpl = jinja_env.get_template("subject_order_status-changed.txt")
    subject = subject_tmpl.render(**context)
    content_tmpl = jinja_env.get_template(get_order_status_update_template(status))
    content = content_tmpl.render(**context)

    send_email(to=to, subject=subject, contents=content)
