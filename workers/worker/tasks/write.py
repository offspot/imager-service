#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import time
import subprocess

import humanfriendly

from tasks.base import BaseTask
from utils.setting import Setting
from utils import get_sdcard_bytes
from utils.scheduler import get_task


class WriteTask(BaseTask):
    @property
    def img_path(self):
        return Setting.working_dir.joinpath(self.task["image_fname"])

    @property
    def log_path(self):
        return self.file_path("txt")

    @property
    def wipe_log_path(self):
        return self.file_path("log")

    def run(self):
        super().run()

        states = [
            ("await_sdcard", "waiting_for_card", "card_inserted", "failed_to_insert"),
            ("wipe_sdcard", "wiping_sdcard", "card_wiped", "failed_to_wipe"),
            ("write_image", "writing", "written", "failed_to_write"),
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

    def await_sdcard(self):

        self.logger.info("Starting await_sdcard on slot {}".format(Setting.usb_slot))
        while get_task(self.task["_id"])[1]["status"] == "received":
            self.logger.info("Waiting for the SD-card to be inserterd...")
            time.sleep(60)

        self.logger.info("SD-card inserted. Checking size")
        sd_card_size = get_sdcard_bytes(Setting.usb_path)
        img_size = self.img_path.stat().st_size
        if img_size > sd_card_size:
            raise IOError(
                "Inserted SD-card is not large enough for image ({sd} vs {img})".format(
                    sd=humanfriendly.format_size(sd_card_size, binary=True),
                    img=humanfriendly.format_size(img_size, binary=True),
                )
            )
        else:
            self.logger.info(
                "SD-card size is sufficient ({})".format(
                    humanfriendly.format_size(sd_card_size, binary=True)
                )
            )

    def wipe_sdcard(self):

        args = [
            str(Setting.installer_binary_path),
            "wipe",
            "--sdcard",
            str(Setting.usb_path),
        ]

        self.logger.info("Starting {args}\n".format(args=" ".join(args)))

        log_fd = open(str(self.wipe_log_path), "w")
        ps = subprocess.run(
            args=args,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            close_fds=True,
        )

        if ps.returncode == 0:
            self.logger.info("wipe ran successfuly.")
        else:
            self.logger.error("wipe failed: {}".format(ps.returncode))

        self.logger.info("collecting full terminated log")
        self.logs["wipe_log"] = self.read_log(self.wipe_log_path)

        if ps.returncode != 0:
            raise subprocess.SubprocessError("wipe rc: {}".format(ps.returncode))

    def write_image(self):
        self.logger.info("Starting image writing")

        # Setting.working_dir.joinpath(self.task["image_fname"])

        args = [
            str(Setting.etcher_binary_path),
            "--unmount",
            "--yes",
            "--check",
            "--drive",
            str(Setting.usb_path),
            str(self.img_path),
        ]
        self.logger.info("Starting {args}\n".format(args=" ".join(args)))

        log_fd = open(str(self.log_path), "w")
        ps = subprocess.Popen(
            args=args,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            close_fds=True,
        )

        self.logger.info("etcher started: {}".format(ps))
        while ps.poll() is None:
            self.logs["writer_log"] = self.read_log(self.log_path)

            # kill upon request
            if self.canceled:
                self.logger.info("terminating etcher…")
                ps.terminate()
                ps.wait(10)
                ps.kill()
                ps.wait(10)
                break

        ps.wait(10)

        if ps.returncode == 0:
            self.logger.info("etcher ran successfuly.")
        else:
            self.logger.error("etcher failed: {}".format(ps.returncode))

        self.logger.info("collecting full terminated log")
        self.logs["writer_log"] = self.read_log(self.log_path)

        if ps.returncode != 0:
            raise subprocess.SubprocessError("etcher rc: {}".format(ps.returncode))
