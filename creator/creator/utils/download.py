#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import io

import requests

FAILURE_RETRIES = 6


class ReportHook:
    def __init__(self):
        self._current_size = 0
        self.width = 60
        self._last_line = None
        self.reporthook(0, 0, 100)  # display empty bar as we start

    def print(self, text):
        print(text, flush=True)

    def reporthook(self, chunk, chunk_size, total_size):
        if chunk != 0:
            self._current_size += chunk_size

        avail_dots = self.width - 2
        if total_size == -1:
            line = "unknown size"
        elif self._current_size >= total_size:
            line = "[" + "." * avail_dots + "] 100%\n"
        else:
            ratio = min(float(self._current_size) / total_size, 1.)
            shaded_dots = min(int(ratio * avail_dots), avail_dots)
            percent = min(int(ratio * 100), 100)
            line = "[{sd}{sp}] {pc}%\r".format(
                sd="." * shaded_dots, sp=" " * (avail_dots - shaded_dots), pc=percent
            )

        if line != self._last_line:
            self._last_line = line
            self.print(line)


def stream(url, write_to=None, callback=None, block_size=1024):
    """ download an URL without blocking

        - retries download on failure (with increasing wait delay)
        - feeds a callback to provide progress indication """

    # prepare adapter so it retries on failure
    session = requests.Session()
    # retries up-to FAILURE_RETRIES whichever kind of listed error
    retries = requests.packages.urllib3.util.retry.Retry(
        total=FAILURE_RETRIES,  # total number of retries
        connect=FAILURE_RETRIES,  # connection errors
        read=FAILURE_RETRIES,  # read errors
        status=2,  # failure HTTP status (only those bellow)
        redirect=False,  # don't fail on redirections
        backoff_factor=30,  # sleep factor between retries
        status_forcelist=[413, 429, 500, 502, 503, 504],
    )
    retry_adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount("http", retry_adapter)  # tied to http and https
    req = session.get(url, stream=True)
    req.raise_for_status()

    total_size = int(req.headers.get("content-length", 0))
    total_downloaded = 0
    if write_to is not None:
        fd = open(write_to, "wb")
    else:
        fd = io.BytesIO()

    for data in req.iter_content(block_size):
        callback(data, block_size, total_size)
        total_downloaded += len(data)
        if write_to:
            fd.write(data)

    if write_to:
        fd.close()
    else:
        fd.seek(0)

    if total_size != 0 and total_downloaded != total_size:
        raise AssertionError("Downloaded size is different than expected ({} vs {})".format(total_downloaded, total_size))

    return total_downloaded, write_to if write_to else fd


def download_file(url, fpath):
    """ downloads expected URL+sum to file while showing progress """
    hook = ReportHook().reporthook
    try:
        size, path = stream(url, fpath, callback=hook)

    except Exception as exp:
        print(exp)
        return False, exp

    return True, size
