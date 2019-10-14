#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import string
import base64
import zipfile
import hashlib
import tempfile
from pathlib import Path

import pytz
import humanfriendly

from manager.pibox import data


ONE_MiB = 2 ** 20
ONE_GiB = 2 ** 30
ONE_GB = int(1e9)
EXFAT_FORBIDDEN_CHARS = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]


def human_readable_size(size, binary=True):
    if isinstance(size, (int, float)):
        num_bytes = size
    else:
        try:
            num_bytes = humanfriendly.parse_size(size)
        except Exception:
            return "NaN"
    is_neg = num_bytes < 0
    if is_neg:
        num_bytes = abs(num_bytes)
    output = humanfriendly.format_size(num_bytes, binary=binary)
    if is_neg:
        return "- {}".format(output)
    return output


def get_checksum(fpath, func=hashlib.sha256):
    h = func()
    with open(fpath, "rb") as f:
        for chunk in iter(lambda: f.read(ONE_MiB * 8), b""):
            h.update(chunk)
    return h.hexdigest()


def get_cache(build_folder):
    fpath = os.path.join(build_folder, "cache")
    os.makedirs(fpath, exist_ok=True)
    return fpath


def get_temp_folder(in_path):
    os.makedirs(in_path, exist_ok=True)
    return tempfile.mkdtemp(dir=in_path)


def relpathto(dest, root=None):
    ''' relative path to an absolute one '''
    if dest is None:
        return None
    return str(Path(dest).relative_to(root))


def b64encode(fpath):
    ''' base64 string of a binary file '''
    with open(fpath, "rb") as fp:
        return base64.b64encode(fp.read()).decode('utf-8')


def b64decode(fname, data, to):
    ''' write back a binary file from its fname and base64 string '''
    fpath = os.path.join(to, fname)
    with open(fpath, 'wb') as fp:
        fp.write(base64.b64decode(data))
    return fpath


def exfat_fnames_filter(fname):
    """ whether supplied fname is valid exfat fname or not """
    # TODO: check for chars U+0000 to U+001F
    return sum([1 for x in EXFAT_FORBIDDEN_CHARS if x in fname]) == 0


def ensure_zip_exfat_compatible(fpath):
    """ wether supplied ZIP archive at fpath contains exfat-OK file names

        boolean, [erroneous, file, names]"""
    bad_fnames = []
    try:
        with zipfile.ZipFile(fpath, "r") as zipf:
            # loop over all file names in the ZIP
            for path in zipf.namelist():
                # loop over all parts (folder, subfolder(s), fname)
                for part in Path(path).splitall():
                    if not exfat_fnames_filter(part) and part not in bad_fnames:
                        bad_fnames.append(part)
    except Exception as exp:
        return False, [str(exp)]
    return len(bad_fnames) == 0, bad_fnames


def check_user_inputs(
    project_name, language, timezone, admin_login, admin_pwd, wifi_pwd=None
):

    allowed_chars = set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + " "
    )
    valid_project_name = (
        len(project_name) >= 1
        and len(project_name) <= 64
        and set(project_name) <= allowed_chars
    )

    valid_language = language in dict(data.hotspot_languages).keys()

    valid_timezone = timezone in pytz.common_timezones

    valid_wifi_pwd = (
        len(wifi_pwd) <= 31
        and set(wifi_pwd)
        <= set(
            string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
        )
        if wifi_pwd is not None
        else True
    )

    valid_admin_login = len(admin_login) <= 31 and set(admin_login) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )
    valid_admin_pwd = len(admin_pwd) <= 31 and set(admin_pwd) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )

    return (
        valid_project_name,
        valid_language,
        valid_timezone,
        valid_wifi_pwd,
        valid_admin_login,
        valid_admin_pwd,
    )


def get_adjusted_image_size(size):
    """ save some space to accomodate real SD card sizes

        the larger the SD card, the larger the loss space is """

    # if size is not a rounded GB multiple, assume it's OK
    if not size % ONE_GB == 0:
        return size

    rate = .97 if size / ONE_GB <= 16 else .96
    return int(size * rate)
