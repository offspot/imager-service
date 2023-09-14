#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import math
import string
import base64
import zipfile
import hashlib
import tempfile
from pathlib import Path

import humanfriendly

from manager.pibox import data


ONE_MB = 10**6
ONE_MiB = 2**20
ONE_GiB = 2**30
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
    """relative path to an absolute one"""
    if dest is None:
        return None
    return str(Path(dest).relative_to(root))


def b64encode(fpath):
    """base64 string of a binary file"""
    with open(fpath, "rb") as fp:
        return base64.b64encode(fp.read()).decode("utf-8")


def b64decode(fname, data, to):
    """write back a binary file from its fname and base64 string"""
    fpath = os.path.join(to, fname)
    with open(fpath, "wb") as fp:
        fp.write(base64.b64decode(data))
    return fpath


def exfat_fnames_filter(fname):
    """whether supplied fname is valid exfat fname or not"""
    # TODO: check for chars U+0000 to U+001F
    return sum([1 for x in EXFAT_FORBIDDEN_CHARS if x in fname]) == 0


def ensure_zip_exfat_compatible(fpath):
    """wether supplied ZIP archive at fpath contains exfat-OK file names

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


def is_valid_language(language):
    return language in dict(data.hotspot_languages).keys()


def is_valid_admin_login(admin_login):
    return len(admin_login) <= 31 and set(admin_login) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )


def is_valid_admin_pwd(admin_pwd):
    return len(admin_pwd) <= 31 and set(admin_pwd) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )


def as_power_of_2(size):
    """round to the next nearest power of 2"""
    return 2 ** math.ceil(math.log(size, 2))


def get_hardware_margin(size: int):
    """number of bytes we must keep free as the HW might not support it"""
    return size * 0.03 if size / ONE_GB <= 16 else 0.04


def get_hardware_adjusted_image_size(size: int):
    """number of bytes we can safely write on an SD card of such size

    to accomodate difference between marketed size and available space"""
    return int(size - get_hardware_margin(size))


def get_qemu_adjusted_image_size(size):
    """number of bytes to resize image file to to accomodate Qemu

    which expects it to be a power of 2 (integer)"""

    # if size is not a rounded GiB multiple, round it to next power of 2
    return size if size % ONE_GiB == 0 else as_power_of_2(size)
