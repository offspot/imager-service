#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import logging

from jinja2 import Environment, PackageLoader, select_autoescape
import yagmail

from utils.mongo import Orders

logger = logging.getLogger(__name__)
jinja_env = Environment(
    loader=PackageLoader("templates"), autoescape=select_autoescape(["html", "xml"])
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
    enctype = os.environ.get("SMTP_ENCTYPE", "tls").lower()
    port = os.environ.get("SMTP_PORT", "auto").lower()
    return yagmail.SMTP(
        user=os.environ.get("SMTP_USERNAME"),
        password=os.environ.get("SMTP_PASSWORD"),
        host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        port=None if port == "auto" else int(port),
        smtp_starttls=enctype in ("tls", "auto"),
        smtp_ssl=enctype == "ssl",
        smtp_set_debuglevel=0,
        smtp_skip_login=bool(os.environ.get("SMTP_SKIP_LOGIN", False)),
    )


def send_email(to, subject, contents, cc=None, bcc=None, headers=None):
    yag = get_sender()
    yag.send(to=to, cc=cc, bcc=bcc, headers=headers, subject=subject, contents=contents)


def get_short_id(mongo_id):
    return "XXX"


def contextualize_order(order):
    order.update(
        {
            "id": order.get("_id"),
            "short_id": get_short_id(order.get("_id")),
            "status": order.get("statuses")[-1],
        }
    )
    return order


def get_order_status_update_template(status):
    return "email_order_{}.html".format(status)


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
