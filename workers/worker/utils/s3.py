#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import threading

from kiwixstorage import TransferHook


class ImageTransferHook(TransferHook):

    def __init__(self, output, fpath=None, size=None, name=""):
        if fpath is None and size is None:
            raise ValueError("either size or fpath must be set")

        if not name and fpath:
            name = fpath.name

        # use fpath to set size
        if size is None:
            size = float(fpath.stat().st_size)

        super().__init__(
            size=size,
            output=output,
            flush=True,
            fmt="[{on}] {name} {progress} / {total} ({percentage:.2f}%)\n",
        )
        self.name = name
        self.lock = threading.Lock()

        # will print every <interval> bytes
        self.printed = 0
        self.print_interval = int(size / 100)

    def __call__(self, bytes_amount):
        # only print if we've seen the interval bytes since last print
        if self.seen_so_far + bytes_amount >= self.printed + self.print_interval:
            with self.lock:
                super().__call__(bytes_amount)
            self.printed = self.seen_so_far
        else:
            self.seen_so_far += bytes_amount
