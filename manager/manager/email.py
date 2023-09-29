#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import os
from collections.abc import Sequence

import requests
from django.conf import settings
from werkzeug.datastructures import MultiDict

logger = logging.getLogger(__name__)


def send_mailgun_email(
    to,
    subject,
    contents,
    cc: Sequence | None = None,
    bcc: Sequence | None = None,
    headers: dict | None = None,  # noqa: ARG001
    attachments: Sequence | None = None,
):
    values = [
        ("from", settings.MAIL_FROM),
        ("subject", subject),
        ("html", contents),
    ]
    values += [("to", to if isinstance(to, list | tuple) else [to])]
    values += [("cc", cc if isinstance(cc, list | tuple) else [cc])]
    values += [("bcc", bcc if isinstance(bcc, list | tuple) else [bcc])]
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
        timeout=6,
    )
    resp.raise_for_status()
    return resp.json().get("id")
