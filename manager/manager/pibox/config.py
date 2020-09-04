#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import uuid
import logging
import tempfile

import magic

from manager.pibox.util import b64decode

logger = logging.getLogger(__name__)


def get_uuid():
    """ shortcut to get a human-friendly UUID """
    return uuid.uuid4().urn[9:]


def get_if_str(data, default=None):
    """ return data if it is a string, otherwise the default """
    if isinstance(data, str):
        return data
    return default


def get_if_str_in(data, values, default=None):
    """ return data if it is a str in a list of values otherwise the default """
    if isinstance(data, str) and data in values:
        return data
    return default


def get_list_if_values_match(data, values, default=[]):
    """ return only the items from data which are part of values. If not a list [] """
    if not isinstance(data, list):
        return default
    return [item for item in data if item in values]


def get_nested_key(data, keys):
    """ return value for a nested key inside a dict specified as ["first", "second"] """
    if isinstance(keys, str):
        keys = [keys]
    if not len(keys):
        return None
    val = data
    try:
        for key in keys:
            val = val[key]
    except Exception:
        val = None
    return val


def is_expected_mime(fname, data, mimes):
    """ whether an fname, base64-encoded matches the supplied mime type (unsecure) """
    fpath = b64decode(fname, data, tempfile.mkdtemp())
    mime = magic.Magic(mime=True)
    return mime.from_file(fpath) in mimes


def extract_branding(config, key, mimes):
    """ verified fname config dict (fname, data) from a supplied config and key """
    fname = os.path.basename(
        get_if_str(get_nested_key(config, ["branding", key, "fname"]), "styles.css")
    )
    data = get_if_str(get_nested_key(config, ["branding", key, "data"]), "-")
    if is_expected_mime(fname, data, mimes):
        return {"fname": fname, "data": data}
    return None
