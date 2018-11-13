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
    warehouse_url: str = None

    working_dir: Path = None

    installer_binary_path: Path = None

    poll_interval = 20  # 60 * 2  # 2mn
    log_upload_interval = 30  # 60 * 2  # 2mn

    @classmethod
    def get_timer(cls, interval):
        return list(range(0, interval))

    @classmethod
    def read_from_env(cls):
        cls.installer_binary_path = Path(
            os.getenv("INSTALLER_BIN_PATH", "/usr/bin/kiwix-hotspot")
        )
        cls.working_dir = Path(os.getenv("WORKING_DIR", "")).resolve(strict=True)
        cls.username = os.getenv("USERNAME", None)
        cls.password = os.getenv("PASSWORD", None)
        cls.api_url = os.getenv(
            "CARDSHOP_API_URL", "https://api.cardshop.hotspot.kiwix.org"
        )
        cls.warehouse_url = os.getenv(
            "CARDSHOP_WAREHOUSE_URL", "ftp://warehouse.cardshop.hotspot.kiwix.org:21"
        )

        logger.info("Checking Settings...")

        if Setting.username is None:
            logger.error("Error: USERNAME environmental variable is required.")
            sys.exit(1)

        if Setting.password is None:
            logger.error("Error: PASSWORD environmental variable is required.")
            sys.exit(1)
