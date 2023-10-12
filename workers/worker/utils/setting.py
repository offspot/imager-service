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
    cache_dir: Path = None

    imager_binary_path: Path = None
    curl_binary_path: Path = None

    poll_interval = 60  # 1mn
    log_upload_interval = 60 * 2  # 2mn

    s3_access_key = None
    s3_secret_key = None

    @classmethod
    def get_timer(cls, interval):
        return list(range(0, interval))

    @classmethod
    def read_from_env(cls):
        cls.imager_binary_path = Path(
            os.getenv("IMAGER_BIN_PATH", "/usr/loca/bin/image-creator")
        )
        cls.curl_binary_path = Path(os.getenv("CURL_BIN_PATH", "/usr/bin/curl"))
        cls.working_dir = Path(os.getenv("WORKING_DIR", "data")).resolve(strict=True)
        cls.cache_dir = Path(os.getenv("CACHE_DIR", "cache")).resolve(strict=True)
        cls.username = os.getenv("USERNAME", "")
        cls.password = os.getenv("PASSWORD", "")
        cls.api_url = os.getenv(
            "CARDSHOP_API_URL", "https://api.cardshop.hotspot.kiwix.org"
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
