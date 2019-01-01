#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import time
from collections import OrderedDict

import humanfriendly

from whost.ui import cli, display_menu, display_success, display_error, pause
from whost.common import getLogger, get_next_slot, read_conf, update_conf, disable_host
from whost.devices import get_writers, get_name_for, find_device, get_size, get_metadata, reset_writers

logger = getLogger(__name__)


def reset_devices():
    cli.info_2("Reseting devices configuration")
    ready = cli.ask_yes_no("Sure you want to remove all devices conf?", default=False)
    if not ready:
        return

    if reset_writers():
        display_success("Devices configuration removed.")
    else:
        display_error("Failed to reset devices configuration.")
    pause()


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
    cli.info_3("waiting for card", end="")
    device = None
    while device is None:
        time.sleep(1)
        cli.dot()
        device = find_device()
    cli.info("FOUND")

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

    pause()


def configure_devices():
    cli.info_1("Already configured writer devices")
    try:
        writers = get_writers()
    except Exception as exp:
        logger.error(exp)
        display_error("Configured devices are not present! "
                      "Reseting devices conf and disabling host.\n"
                      "Please configure devices and re-enable it.")
        reset_writers()
        disable_host()
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
