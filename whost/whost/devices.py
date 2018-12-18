#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import subprocess
from pathlib import Path

from whost.common import getLogger, read_conf

logger = getLogger(__name__)
BLOCK_PREFIX = Path("/sys/class/block")
DEVICES_PREFIX = Path("/sys/devices")


def get_writer(slot, writer_conf):
    device = get_device_from(
        pci_ident=writer_conf["pci"],
        usb_ident=writer_conf["usb"],
        host_ident=writer_conf["host"],
    )
    writer_conf.update({"device": device, "name": get_name_for(device), "slot": slot})
    return writer_conf


def get_writers():
    config = read_conf()
    return [
        get_writer(slot, writer) for slot, writer in config.get("writers", {}).items()
    ]


def get_block_devices_list():
    """ ["sdb", "sdc", ..] returning all block devices """
    return [
        fname for fname in os.listdir(BLOCK_PREFIX) if re.search("^sd[a-z]+$", fname)
    ]


def get_removable_usb_blocks():
    return filter(lambda x: is_removable(x), get_block_devices_list())


def find_device():
    """ return block_name (sdX) of the first found removable block dev with geometry """
    try:
        return next(
            filter(
                lambda x: get_size(x) is not None,
                [block_name for block_name in get_removable_usb_blocks()],
            )
        )
    except Exception:
        return None


def _block_path(block_name):
    return BLOCK_PREFIX.joinpath(block_name)


def get_metadata(block_name):
    """ return PCI/USB/HOST unique identifier for a block_name """
    parts = _block_path(block_name).resolve().parts
    return {"pci": parts[4], "usb": parts[8], "host": parts[11]}


def get_device_path(pci_ident, usb_ident, host_ident):
    """ full /sys/devices path for a PCI/USB/HOST combination """

    # /sys/devices/pci0000:00/0000:00:14.0
    pci_paths = ["pci{}".format(":".join(pci_ident.split(":")[0:2])), pci_ident]

    # usb4/4-1/4-1.2/4-1.2:1.0
    usb_paths = [
        "usb{}".format(usb_ident.split("-", 1)[0]),
        usb_ident.split(".", 1)[0],
        usb_ident.split(":", 1)[0],
        usb_ident,
    ]

    # host6/target6:0:0/6:0:0:1
    host_paths = [
        "host{}".format(host_ident.split(":", 1)[0]),
        "target{}".format(host_ident.rsplit(":", 1)[0]),
        host_ident,
    ]

    return DEVICES_PREFIX.joinpath(*pci_paths + usb_paths + host_paths)


def get_block_for(device_path):
    try:
        bn = [
            fname
            for fname in os.listdir(device_path.joinpath("block"))
            if fname.startswith("sd")
        ][0]
    except Exception as exp:
        logger.error(exp)
        return None
    return device_path.joinpath("block", bn).name


def get_device_from(pci_ident, usb_ident, host_ident):
    return get_block_for(get_device_path(pci_ident, usb_ident, host_ident))


def get_name_for(block_name):
    vendor_p = _block_path(block_name).joinpath("device", "vendor")
    model_p = _block_path(block_name).joinpath("device", "model")
    with open(str(vendor_p), "r") as vfp, open(str(model_p), "r") as mfp:
        return "{vendor}{model}".format(
            vendor=vfp.read().strip(), model=mfp.read().strip()
        )


def is_removable(block_name):
    try:
        removable_p = _block_path(block_name).joinpath("removable")
        with open(str(removable_p), "r") as fp:
            return bool(int(fp.read().strip()))
    except Exception:
        return False


def get_size(block_name):
    ps = subprocess.run(
        ["/sbin/fdisk", "-l", "/dev/{}".format(block_name)],
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if not ps.returncode == 0:
        return None

    try:
        return int(re.search(", ([0-9]+) bytes", ps.stdout.splitlines()[0]).groups()[0])
    except Exception as exp:
        logger.error(exp)
        return 1
