#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import subprocess

import requests


def get_token(url, username, password):
    req = requests.post(
        url="{api}/auth/authorize".format(api=url),
        headers={
            "username": username,
            "password": password,
            "Content-type": "application/json",
        },
    )
    req.raise_for_status()
    return req.json().get("access_token"), req.json().get("refresh_token")


def main(api_url, warehouse_uri, username, password, fpath):

    # get token
    access_token, refresh_token = get_token(api_url, username, password)
    print("access_token", access_token)

    args = [
        "curl",
        "--append",
        "--connect-timeout",
        "60",
        "--continue-at",
        "-",
        "--insecure",
        "--ipv4",
        "--retry-connrefused",
        "--retry-delay",
        "60",
        "--retry",
        "20",
        "--stderr",
        "-",
        "--user",
        "{user}:{passwd}".format(user=username, passwd=access_token),
        "--upload-file",
        str(fpath),
        warehouse_uri,
    ]

    subprocess.run(args)


if __name__ == "__main__":
    main(
        api_url="https://api.cardshop.hotspot.kiwix.org",
        warehouse_uri="ftp://download.cardshop.hotspot.kiwix.org:2221",
        username="",
        password="",
        fpath=os.path.abspath(sys.argv[1]),
    )
