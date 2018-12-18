#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import time
from collections import OrderedDict

import humanfriendly

from whost.ui import cli, display_menu, display_success, display_error
from whost.common import getLogger, get_next_slot, read_conf, update_conf
from whost.devices import get_writers, get_name_for, find_device, get_size, get_metadata

logger = getLogger(__name__)


def reset_devices():
    pass


def add_device():
    cli.info_2("Please remove all SD-cards from all writers.")
    ready = cli.ask_yes_no("Ready?", default=False)
    if not ready:
        return

    cli.info(
        "Great! Now please insert",
        cli.bold,
        "one",
        cli.reset,
        "SD-card into the writer you want to configure.",
    )
    print(" waiting for card", end="")
    device = None
    while device is None:
        time.sleep(1)
        print(".", end="", flush=True)
        device = find_device()
    print("FOUND")

    # we now have a new DEVICE.
    hw = get_metadata(device)
    slot = get_next_slot()

    # update configured writers list
    writers = read_conf().get("writers", {})
    writers.update({slot: hw})
    if update_conf({"writers": writers}):
        display_success(
            "Found your",
            humanfriendly.format_size(get_size(device), binary=True),
            "card on",
            cli.bold,
            device,
            cli.reset,
            "({})".format(get_name_for(device)),
            ".\n",
            "Assigned slot:",
            cli.bold,
            slot,
        )
    else:
        display_error("Failed to configure a slot for", cli.bold, device)


def configure_devices():
    cli.info_1("Already configured writer devices")
    writers = get_writers()
    for writer in writers:
        cli.info(
            cli.blue,
            " *",
            cli.reset,
            cli.bold,
            "{slot}:/dev/{device}".format(**writer),
            cli.reset,
            "({name} at {pci}/{usb}/{host})".format(**writer),
        )
    cli.info("")

    menu = OrderedDict(
        [
            ("reset-writers", ("Reset writers config (remove ALL)", reset_devices)),
            ("add-device", ("Add one device", add_device)),
        ]
    )

    display_menu("Choose:", menu=menu, with_cancel=True)
