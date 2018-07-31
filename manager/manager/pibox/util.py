#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import base64
import hashlib

import humanfriendly


ONE_MiB = 2 ** 20
ONE_GiB = 2 ** 30
ONE_GB = int(1e9)


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


def relpathto(dest):
    ''' relative path to an absolute one '''
    if dest is None:
        return None
    return str(Path(dest).relpath())


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
