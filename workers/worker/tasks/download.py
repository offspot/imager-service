#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import io
import time
import urllib
import logging
import datetime
import subprocess
from urllib.parse import urlparse

from kiwixstorage import KiwixStorage

from tasks.base import BaseTask
from utils.setting import Setting
from utils.s3 import ImageTransferHook
from utils.scheduler import authenticate, get_access_token, get_task


class DownloadTask(BaseTask):
    @property
    def img_path(self):
        return self.file_path("img")

    @property
    def log_path(self):
        return self.file_path("txt")

    def run(self):
        super().run()

        # make sure warehouse URI is OK before we start
        try:
            urlparse(self.task["download_uri"])
        except Exception as exp:
            self.logger.error("Error: Warehouse URI could not be parsed")
            self.logger.exception(exp)
            self.exception = exp
            self.report_status("failed", str(exp))
            return

        states = [
            ("download_image", "downloading", "downloaded", "failed_to_download"),
            (
                "idle",
                "pending_end_of_writes",
                "pending_image_removal",
                "downloaded_failed_to_remove",
            ),
            (
                "remove_image",
                "pending_image_removal",
                "downloaded_and_removed",
                "downloaded_failed_to_remove",
            ),
        ]

        for method, working_status, success_status, failed_status in states:
            try:
                self.report_status(working_status)
                getattr(self, method)()
            except Exception as exp:
                self.logger.exception(exp)
                self.exception = exp
                if self.canceled:
                    self.report_status("canceled")
                else:
                    self.report_status(failed_status, str(exp))
                return
            else:
                self.report_status(success_status)

    def download_image(self):
        if self.task["download_uri"].startswith("s3://"):
            return self.download_image_s3()

        return self.download_image_with_aria2()

    def download_image_s3(self):
        self.logger.info("Starting s3 image download")

        # add credentials to URL
        url = urllib.parse.urlparse(self.task["download_uri"])
        qs = urllib.parse.parse_qs(url.query)
        qs["keyId"] = Setting.s3_access_key
        qs["secretAccessKey"] = Setting.s3_secret_key

        # setup download logging
        downloader_log = io.StringIO()
        downloader_logger = logging.getLogger("downloader_log")
        downloader_logger.propagate = True
        downloader_logger.setLevel(logging.DEBUG)
        downloader_logger.addHandler(logging.StreamHandler(stream=downloader_log))

        # init and test storage
        downloader_logger.info("initializing S3")
        s3_storage = KiwixStorage(
            urllib.parse.SplitResult(
                "https",
                url.netloc,
                url.path,
                urllib.parse.urlencode(qs, doseq=True),
                url.fragment,
            ).geturl()
        )
        downloader_logger.debug(
            f"S3 initialized for {s3_storage.url.netloc}/{s3_storage.bucket_name}"
        )

        # download
        downloader_logger.info(f"Downloading from {self.img_path.name}")
        try:
            hook = ImageTransferHook(
                output=downloader_log,
                size=s3_storage.get_object_stat(key=self.img_path.name).size,
                name=self.img_path.name,
            )
            s3_storage.download_file(
                key=self.img_path.name, fpath=str(self.img_path), Callback=hook
            )
            downloaded = True
        except Exception as exc:
            downloaded = False
            downloader_logger.error(f"downloader failed: {exc}")
            downloader_logger.exception(exc)
        else:
            downloader_logger.info("downloader ran successfuly.")

        if downloaded:
            # image downloaded, mark for autodeletion
            try:
                autodelete_on = datetime.datetime.now() + datetime.timedelta(days=1)
                downloader_logger.info(f"Setting autodelete to now ({autodelete_on})")
                s3_storage.set_object_autodelete_on(
                    key=self.img_path.name, on=autodelete_on
                )
            except Exception as exc:
                downloader_logger.error(
                    "Failed to set autodelete (normal if before bucket retention)"
                )
                downloader_logger.exception(exc)

        self.logger.info("collecting downloader log")
        try:
            self.logs["downloader_log"] = downloader_log.getvalue()
            downloader_log.close()
        except Exception as exc:
            self.logger.error(f"Failed to collect logs: {exc}")

        if not downloaded:
            raise subprocess.SubprocessError("S3 download failed")

    def download_image_with_aria2(self):
        self.logger.info("Starting image download with aria2")

        checksum_type, checksum_digest = self.task["image_checksum"].split(":", 1)

        self.logger.info("re-authenticate to ensure token is still valid")
        authenticate(force=True)

        url = "{dl}/{fn}".format(
            dl=self.task["download_uri"], fn=self.task["image_fname"]
        )

        if bool(os.getenv("FAKE_DOWNLOAD", False)):
            url = "https://github.com/kiwix/kiwix-hotspot/raw/master/mbr.img"

        args = [
            str(Setting.aria2_binary_path),
            "--dir",
            str(Setting.working_dir),
            "--log",
            str(self.log_path),
            "--log-level=info",
            "--out={}".format(self.task["image_fname"]),
            "--continue",
            "--checksum={type}={digest}".format(
                type=checksum_type, digest=checksum_digest
            ),
            "--max-connection-per-server={}".format(Setting.download_max_connections),
            "--split={}".format(Setting.download_max_connections),
            "--max-tries={}".format(20),
            "--retry-wait={sec}".format(sec=60),
            "--timeout={}".format(60 * 5),
            "--check-certificate=false",
            "--allow-overwrite=true",
            "--always-resume=true",
            "--allow-piece-length-change=true",
            "--auto-file-renaming=false",
            "--disable-ipv6=true",
            "--http-user={}".format(Setting.username),
            "--http-passwd={}".format(get_access_token()),
            "--ftp-user={}".format(Setting.username),
            "--ftp-passwd={}".format(get_access_token()),
            url,
        ]

        if Setting.proxy:
            args = args[0:1] + ["--all-proxy={}".format(Setting.proxy)] + args[1:]

        log_args = (
            args[0:-4]
            + ["http-passwd=xxxx"]
            + args[-3:-2]
            + ["ftp-passwd=xxxx"]
            + args[-1:]
        )
        self.logger.info("Starting {args}\n".format(args=" ".join(args)))

        self.logs["downloader_log"] = "{args}\n".format(args=" ".join(log_args))
        log_fd = open(str(self.log_path), "a")
        ps = subprocess.Popen(
            args=args,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            close_fds=True,
        )

        self.logger.info("installer started: {}".format(ps))
        while ps.poll() is None:
            self.logs["downloader_log"] = self.read_log(self.log_path)

            # kill upon request
            if self.canceled:
                self.logger.info("terminating installer…")
                ps.terminate()
                ps.wait(10)
                ps.kill()
                ps.wait(10)
                break

        ps.wait(10)

        if ps.returncode == 0:
            self.logger.info("installer ran successfuly.")
        else:
            self.logger.error("installer failed: {}".format(ps.returncode))

        self.logger.info("collecting full terminated log")
        self.logs["downloader_log"] = self.read_log(self.log_path)

        if ps.returncode != 0:
            raise subprocess.SubprocessError("installer rc: {}".format(ps.returncode))

    def idle(self):
        self.logger.info("idleing until all cards have been written")
        while (
            not self.canceled
            and get_task(self.task["_id"])[1]["status"] == "pending_end_of_writes"
        ):
            self.logger.info("Idleing...")
            time.sleep(2 * 60)

        self.logger.info("All SD-cards written !")

    def remove_image(self):
        self.logger.info("removing image file at {}".format(str(self.img_path)))
        self.img_path.unlink()
        self.logger.info("image file removed !")
