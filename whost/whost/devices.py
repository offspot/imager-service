#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

"""
SD-card readers are presented and used (in docker calls) as block devices
Examples: /dev/sda, /dev/mmcblk0
block_name is file name of the block device (sda for instance)
Whenever card reader is present, the block device is present.
If a card is in the reader, then device has a geometry that fdisk can read.

/sys/class/block/<block_name> is a symlink to the /sys/devices path
representing the device.

/sys/devices path does not change so we store it in our config.

find_device(): returns <block_name> for the sole SD-card present
get_device_id(block_name): USB device ID, 2:0:0:0
get_block_name(device_id): block_name from stored device path, sdb
"""

import os
import re
import subprocess
from pathlib import Path

from whost.common import getLogger, read_conf, update_conf

logger = getLogger(__name__)
BLOCK_PREFIX = Path("/sys/class/block")
DEVICES_PREFIX = Path("/sys/devices")


def get_writer(slot, device_id):
    """ shortcut to retrieve device, slot and name when reading config """
    device = get_block_name(device_id)
    if device is None:
        return None
    return {
        "device": device,
        "name": get_display_name(device),
        "slot": slot,
        "device_id": device_id,
    }


def get_writers():
    """ list of get_writer() for all writers in conf """
    config = read_conf()
    writers = []
    for slot, w in config.get("writers", {}).items():
        writer = get_writer(slot, w)
        if writer:
            writers.append(writer)
    return writers


def reset_writers():
    return update_conf({"writers": {}})


def get_block_devices_list():
    """ ["sdb", "sdc", ..] returning all block devices """
    return [
        fname
        for fname in os.listdir(BLOCK_PREFIX)
        if re.search("^sd[a-z]+$", fname) or re.search("^mmcblk[0-9]+$", fname)
    ]


def get_removable_usb_blocks():
    return filter(lambda x: is_removable(x), get_block_devices_list())


def find_device():
    """ return block_name (sdX) of the first found removable block dev with geometry """
    try:
        return next(
            filter(
                lambda x: get_block_size(x) is not None,
                [block_name for block_name in get_removable_usb_blocks()],
            )
        )
    except Exception:
        return None


def _block_path(block_name):
    return BLOCK_PREFIX.joinpath(block_name)


# def _device_path(device_path):
#     return DEVICES_PREFIX.joinpath(device_path)


# def get_device_path(block_name):
#     """ hardware path to this block device """
#     parts = _block_path(block_name).resolve().parts
#     return _device_path("/".join(parts[3:-2]))


def get_device_id(block_name):
    """ USB id to this block device (2:0:0:1) """
    parts = _block_path(block_name).resolve().parts
    device_id = parts[-3]
    if device_id == "class":
        raise OSError("Unable to find device ID for {}".format(block_name))
    return device_id


def get_block_name(device_id):
    """ current block device name for this hardware ID """
    try:
        block_path = Path(
            subprocess.run(
                [
                    "find",
                    "/sys/devices/pci0000:00/",
                    "-wholename",
                    "*/{}/block".format(device_id),
                ],
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ).stdout.splitlines()[0]
        )
        bn = [
            fname
            for fname in os.listdir(block_path)
            if fname.startswith("sd") or fname.startswith("mmcblk")
        ][0]
    except Exception as exp:
        logger.error(exp)
        return None
    return block_path.joinpath(bn).name


# def get_block_name_dp(device_path):
#     """ current block device name for this hardware path """
#     try:
#         bn = [
#             fname
#             for fname in os.listdir(device_path.joinpath("block"))
#             if fname.startswith("sd") or fname.startswith("mmcblk")
#         ][0]
#     except Exception as exp:
#         logger.error(exp)
#         return None
#     return device_path.joinpath("block", bn).name


def get_display_name(block_name):
    """ string from info in block/device/<name>|<vendor>|<model> """
    parts = []
    for prop in ("vendor", "model", "name"):
        pp = _block_path(block_name).joinpath("device", prop)
        if pp.exists():
            parts.append(open(str(pp), "r").read().strip())
    return " ".join(parts)


def is_removable(block_name):
    # internal memory card readers are non-removable yet medias are
    if block_name.startswith("mmcblk"):
        return True
    try:
        removable_p = _block_path(block_name).joinpath("removable")
        with open(str(removable_p), "r") as fp:
            return bool(int(fp.read().strip()))
    except Exception:
        return False


def get_block_size(block_name):
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
