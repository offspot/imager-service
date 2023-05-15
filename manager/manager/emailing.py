#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
from typing import Optional, Sequence
import logging

import requests
from django.conf import settings
from werkzeug.datastructures import MultiDict

logger = logging.getLogger(__name__)


def send_mailgun_email(
    to,
    subject,
    contents,
    cc: Optional[Sequence] = None,
    bcc: Optional[Sequence] = None,
    headers: Optional[dict] = None,
    attachments: Optional[Sequence] = None,
):
    values = [
        ("from", settings.MAIL_FROM),
        ("subject", subject),
        ("html", contents),
    ]
    values += [("to", to if isinstance(to, (list, tuple)) else [to])]
    values += [("cc", cc if isinstance(cc, (list, tuple)) else [cc])]
    values += [("bcc", bcc if isinstance(bcc, (list, tuple)) else [bcc])]
    data = MultiDict(values)

    resp = requests.post(
        url=f"{settings.MAILGUN_API_URL}/messages",
        auth=("api", settings.MAILGUN_API_KEY),
        data=data,
        files=[
            ("attachment", (os.path.basename(fpath), open(fpath, "rb").read()))
            for fpath in attachments
        ]
        if attachments
        else [],
    )
    resp.raise_for_status()
    return resp.json().get("id")
