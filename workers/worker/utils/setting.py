#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class Setting:
    username: str = None
    password: str = None

    api_url: str = None

    working_dir: Path = None

    installer_binary_path: Path = None
    aria2_binary_path: Path = None
    etcher_binary_path: Path = None
    curl_binary_path: Path = None

    usb_slot: str = None
    usb_path: Path = None

    proxy: str = None

    poll_interval = 60  # 1mn
    log_upload_interval = 60 * 2  # 2mn

    download_max_connections = 5

    s3_access_key = None
    s3_secret_key = None

    @classmethod
    def get_timer(cls, interval):
        return list(range(0, interval))

    @classmethod
    def read_from_env(cls):
        cls.installer_binary_path = Path(
            os.getenv("INSTALLER_BIN_PATH", "/usr/bin/kiwix-hotspot")
        )
        cls.aria2_binary_path = Path(os.getenv("ARIA2_BIN_PATH", "/usr/bin/aria2c"))
        cls.etcher_binary_path = Path(
            os.getenv("ETCHER_BIN_PATH", "/usr/local/etcher/balena-etcher")
        )
        cls.curl_binary_path = Path(os.getenv("CURL_BIN_PATH", "/usr/bin/curl"))
        cls.working_dir = Path(os.getenv("WORKING_DIR", "")).resolve(strict=True)
        cls.username = os.getenv("USERNAME", None)
        cls.password = os.getenv("PASSWORD", None)
        cls.api_url = os.getenv(
            "CARDSHOP_API_URL", "https://api.cardshop.hotspot.kiwix.org"
        )
        cls.usb_slot = Path(os.getenv("USB_SLOT", "no_slot"))
        cls.usb_path = Path(os.getenv("USB_PATH", "/dev/sdcard") or "/dev/sdcard")
        cls.host_device = os.getenv("HOST_DEVICE", "unknown")
        cls.proxy = os.getenv("PROXY", None)

        cls.download_max_connections = int(
            os.getenv("MAX_CONNECTIONS", cls.download_max_connections)
        )

        cls.s3_access_key = os.getenv("S3_ACCESS_KEY", cls.s3_access_key)
        cls.s3_secret_key = os.getenv("S3_SECRET_KEY", cls.s3_secret_key)

        logger.info("Checking Settings...")

        if Setting.username is None:
            logger.error("Error: USERNAME environmental variable is required.")
            sys.exit(1)

        if Setting.password is None:
            logger.error("Error: PASSWORD environmental variable is required.")
            sys.exit(1)
