#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import requests

from whost.common import getLogger, read_conf, DEFAULT_API_URL, update_conf
from whost.ui import cli, get_valid_string, nonempty_validator

logger = getLogger(__name__)


def is_authenticated():
    """ boolean if in-config credentials could authenticate """
    config = read_conf()
    try:
        req = requests.post(
            url="{}/auth/authorize".format(config.get("api_url")),
            headers={
                "username": config.get("username"),
                "password": config.get("password"),
                "Content-type": "application/json",
            },
        )
        req.raise_for_status()
    except Exception as exp:
        logger.error(exp)
        return False
    else:
        return True


def configure_credentials():
    """ get username/password/api_url from user and save to config file """
    cli.info_2("Credentials")
    config = read_conf()

    username = get_valid_string("Username", nonempty_validator, config.get("username"))
    password = get_valid_string("Password", nonempty_validator, config.get("password"))
    api_url = get_valid_string(
        "API URL – use `reset` to use default",
        nonempty_validator,
        config.get("api_url", DEFAULT_API_URL),
    )
    if api_url == "reset":
        api_url = DEFAULT_API_URL

    update_conf({"username": username, "password": password, "api_url": api_url})
    cli.info_2(
        "Saved crentials as",
        cli.bold,
        username,
        cli.reset,
        "/",
        cli.bold,
        password,
        cli.reset,
        "for",
        cli.bold,
        api_url,
    )
