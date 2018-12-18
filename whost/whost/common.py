#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import string
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
CONFIG_PATH = Path("/etc/cardshop-host.config")
NETPLAN_CONF = Path("/etc/netplan/50-cloud-init.yaml")
DEFAULT_API_URL = "https://api.cardshop.hotspot.kiwix.org"
UPDATE_SCRIPT = Path(__file__).parent.resolve().joinpath("update.sh")
ALL_SLOTS = list(string.ascii_uppercase)


def getLogger(name):
    return logging.getLogger(name)


logger = getLogger(__name__)


def read_conf():
    """ read cardshop config file (json) """
    try:
        with open(str(CONFIG_PATH), "r") as fd:
            return json.load(fd)
    except Exception as exp:
        logger.error(exp)
        return {}


def save_conf(config):
    """ save cardshop config to file (json) """
    with open(str(CONFIG_PATH), "w") as fd:
        json.dump(config, fd, indent=4)
    return True


def update_conf(data):
    """ update values into cardshop config file """
    config = read_conf()
    config.update(data)
    return save_conf(config)


def get_next_slot():
    config = read_conf()
    for slot in ALL_SLOTS:
        if slot in config.get("writers", {}).keys():
            continue
        return slot


# make sure we have a config
if not CONFIG_PATH.exists():
    save_conf(
        {{"username": "", "password": "", "enabled": False, "api_url": DEFAULT_API_URL}}
    )
