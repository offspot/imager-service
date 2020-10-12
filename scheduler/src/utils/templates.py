#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import os
import io
import base64
import logging
import tempfile
import urllib.parse

import torf
import qrcode
import requests
import langcodes
import pycountry
from jinja2 import Markup
from qrcode.image.pure import PymagingImage

logger = logging.getLogger(__name__)
re_newlines = re.compile(r"\r\n|\r")  # Used in normalize_newlines


def get_id(an_object):
    """ return the _id prop of the mongo object/dict """
    return an_object["_id"]


def get_pub_url(order):
    """ full URL if order detail on public website """
    return "{pub_url}/orders/f/{id}".format(
        pub_url=os.getenv("PUBLIC_URL"), id=order["_id"]
    )


def get_insert_card_url(task):
    return "{api_url}/tasks/writer/{id}/confirm_inserted".format(
        api_url=os.getenv("CARDSHOP_API_URL"), id=task["_id"]
    )


def get_add_shipment_url(order):
    return "{api_url}/orders/{id}/add_shipment".format(
        api_url=os.getenv("CARDSHOP_API_URL"), id=order["_id"]
    )


def get_public_download_url(order):
    url = urllib.parse.urlparse(order["warehouse"]["download_uri"])
    fname = f"{order['_id']}.img"
    if "torrent" in url.scheme:
        parts = list(urllib.parse.urlsplit(url.geturl()))
        parts[0] = parts[0].replace("+torrent", "")
        url = urllib.parse.urlparse(urllib.parse.urlunsplit(parts))
        fname = f"{fname}.torrent"
    return urllib.parse.urljoin(url.geturl(), fname)


def public_download_url_is_torrent(order):
    return (
        "1"
        if "torrent" in urllib.parse.urlparse(order["warehouse"]["download_uri"]).scheme
        else ""
    )


def get_public_download_magnet_url(order):
    if not public_download_url_is_torrent(order):
        return
    try:
        res = requests.get(get_public_download_url(order))
        torrent = torf.Torrent.read_stream(io.BytesIO(res.content))
        return torrent.magnet()
    except Exception as exc:
        logger.error("Unable to retrieve torrent file")
        logger.exception(exc)
    return get_public_download_url(order)


def yesno(value):
    """ yes or no string from bool value """
    return "yes" if bool(value) else "no"


def language_name(language_code):
    """ languane name of language_code """
    return langcodes.Language.get(language_code).language_name()


def country_name(country_code):
    try:
        return pycountry.countries.get(alpha_2=country_code).name
    except Exception:
        return None


def normalize_newlines(text):
    """Normalize CRLF and CR newlines to just LF."""
    return re_newlines.sub("\n", str(text))


def linebreaksbr(value, autoescape=True):
    """ convert all newlines to <br /> tags """
    value = normalize_newlines(value)
    return Markup(value.replace("\n", "<br />"))


def b64qrcode(text):
    """ encodes the text in PNG QRCode then return its base64 repr """
    img = qrcode.make(text, image_factory=PymagingImage)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as qfile:
        img.save(qfile)
        qfile.seek(0)
        return base64.b64encode(qfile.read()).decode("utf-8")
