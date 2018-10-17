#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import base64
from pathlib import Path

import humanfriendly
from django import template

from manager.pibox.util import human_readable_size
from manager.pibox.packages import get_parsed_package, PACKAGES_BY_LANG

register = template.Library()


def human_size(value, binary=True):
    return human_readable_size(value, binary).replace(" ", " ")


register.filter("human_size", human_size)


def human_number(value, decimals=0):
    return humanfriendly.format_number(value, num_decimals=decimals)


register.filter("human_number", human_number)


def parsed_sname(package):
    return get_parsed_package(package)["sname"]


register.filter("parsed_sname", parsed_sname)


def decodeb64(value):
    return base64.b64decode(value).decode("UTF-8")


register.filter("decodeb64", decodeb64)


def fname(value):
    return Path(value).name.split("_")[-1]


register.filter("fname", fname)


def as_packages(value):
    return [
        PACKAGES_BY_LANG[pid.rsplit(".", 1)[-1]].get(pid)
        for pid in json.loads(value) or []
    ]


register.filter("as_packages", as_packages)


def as_widget(field):
    if not hasattr(field, 'as_widget'):
        return field
    our_classes = ["form-control"]
    if getattr(field, 'errors', False):
        our_classes += ["alert-danger"]
    return field.as_widget(attrs={"class": field.css_classes(" ".join(our_classes))})


register.filter("as_widget", as_widget)
