#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import subprocess
from urllib.parse import urlparse

from tasks.base import BaseTask
from utils.setting import Setting
from utils.scheduler import authenticate, get_access_token


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

        states = [("download_image", "downloading", "downloaded", "failed_to_download")]

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
        self.logger.info("Starting image download")

        checksum_type, checksum_digest = self.task["image_checksum"].split(":", 1)
        max_connection = 5

        self.logger.info("re-authenticate to ensure token is still valid")
        authenticate(force=True)

        url = "{dl}/{fn}".format(
            dl=self.task["download_uri"], fn=self.task["image_fname"]
        )
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
            "--max-connection-per-server={}".format(max_connection),
            "--split={}".format(max_connection),
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
