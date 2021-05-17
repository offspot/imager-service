#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import logging
import tempfile
import subprocess
from pathlib import Path

import requests

from base import BaseWorker
from utils import download_file
from utils.setting import Setting
from tasks.create import CreateTask, free_space


logger = logging.getLogger(__name__)


class CreatorWorker(BaseWorker):

    worker_type = "creator"
    job_cls = CreateTask

    def check_kiwix_hotspot(self):
        """ check latest version of kiwix-hotspot and download if different """

        # guess latest version
        req = requests.get(
            "https://api.github.com/repos/kiwix/kiwix-hotspot/git/refs/tags"
        )
        try:
            version = req.json()[-1]["ref"].replace("refs/tags/", "")[1:]  # default
            for item in reversed(req.json()):
                tag = item["ref"].replace("refs/tags/", "")
                if tag.startswith("v"):
                    version = tag[1:]  # remote version (tag) has an extra v at char 0
                    break
        except Exception as exp:
            logger.info("Could not guess latest version, skipping: {}".format(exp))
            return

        # retrieve local version ()
        try:
            local_version = (
                subprocess.run(
                    args=[str(Setting.installer_binary_path), "--version"],
                    universal_newlines=True,
                    capture_output=True,
                    check=True,
                )
                .stdout.strip()
                .split(": ")[-1]
            )
        except Exception as exp:
            logger.error(exp)
            local_version = "unknown"

        if version == local_version:
            logger.info("Already using latest ({}) version, skipping.".format(version))
            return
        else:
            logger.info(
                "Using {local} instead of {remote}".format(
                    remote=version, local=local_version
                )
            )

        if bool(os.getenv("DONT_UPDATE_INSTALLER", False)):
            logger.info("not updating… as requested")
            return

        # download new version
        url = (
            "http://mirror.download.kiwix.org/release/kiwix-hotspot/v{version}/"
            "kiwix-hotspot-linux.tar.gz".format(version=version)
        )
        logger.info("Downloading new Kiwix-hotspot {}".format(version))
        with tempfile.NamedTemporaryFile() as tmpf:
            success, size_or_exp = download_file(url, tmpf.name)
            if not success:
                logger.info("Failed to download {}".format(url))
                return

            # extract and move kiwix release
            proc = subprocess.run(["/bin/tar", "-C", "/tmp", "-x", "-f", tmpf.name])
            if not proc.returncode == 0:
                logger.info("Failed to extract {}, skipping.".format(tmpf.name))
                return

            Path("/tmp/kiwix-hotspot").rename(Setting.installer_binary_path)

        logger.info("Installed {} at {}".format(version, Setting.installer_binary_path))

    def start(self):
        super().start(run_loop=False)
        self.check_kiwix_hotspot()
        free_space()
        self.run_loop()
