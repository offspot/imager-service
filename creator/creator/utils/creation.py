#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import logging
import threading
import subprocess
import ftplib
from urllib.parse import urlparse

from .setting import Setting
from .scheduler import update_task_status, authenticate, REFRESH_TOKEN

ONE_KiB = 2 ** 10
logger = logging.getLogger(__name__)


class CreationTask(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.exception: Exception = None  # exception to be re-raised by caller
        self.installer_log: str = None

        self.task: dict = {}
        self.warehouse_host: str = None
        self.warehouse_port: int = None

        self._should_stop: bool = False  # stop flag

    def stop(self):
        logger.info("stopping thread")
        self._should_stop = True

    @property
    def canceled(self):
        return self._should_stop

    def report_status(self, status, log=None):
        logger.info("updating task #{} status to: {}".format(self.task["_id"], status))
        success, tid = update_task_status(self.task["_id"], status, log)
        return success

    def remove_files(self, only_errorneous=True):
        suffixes = [".ERROR.img", ".BUILDING.img"]
        if not only_errorneous:
            suffixes.append(".img")

        for suffix in suffixes:
            path = Setting.working_dir.joinpath(str(self.task["_id"]) + suffix)
            if path.is_file():
                logger.info("removing {}".format(path.name))
                path.unlink()

        # delete config and log
        for path in (self.log_path, self.config_path):
            if path.is_file():
                path.unlink()

    def file_path(self, ext):
        return Setting.working_dir.joinpath(
            "{id}.{ext}".format(id=str(self.task["_id"]), ext=ext)
        )

    @property
    def img_path(self):
        return self.file_path("img")

    @property
    def log_path(self):
        return self.file_path("txt")

    @property
    def config_path(self):
        return self.file_path("json")

    def run(self):
        self.task, = self._args

        # make sure warehouse URI is OK before we start
        try:
            url = urlparse(self.task["upload_uri"])
            self.warehouse_host = url.hostname
            self.warehouse_port = url.port
        except Exception as exp:
            logger.error("Error: Warehouse URI could not be parsed")
            logger.exception(exp)
            self.exception = exp
            self.report_status("failed", str(exp))
            return

        states = [
            ("build_image", "building", "built", "failed_to_build"),
            ("upload_image", "uploading", "uploaded", "failed_to_upload"),
        ]

        for method, working_status, success_status, failed_status in states:
            try:
                self.report_status(working_status)
                getattr(self, method)()
            except Exception as exp:
                logger.exception(exp)
                self.exception = exp
                if self.canceled:
                    self.report_status("canceled")
                else:
                    self.report_status(failed_status, str(exp))
                return
            else:
                self.report_status(success_status)

    def read_log(self):
        cat = subprocess.run(
            ["cat", str(self.log_path)], text=True, capture_output=True
        )
        return "{stdout}\n{stderr}".format(
            stdout=cat.stdout or "", stderr=cat.stderr or ""
        )

    def build_image(self):
        logger.info("Starting image creation")

        # write config to a file
        with open(str(self.config_path), "w") as fd:
            json.dump(self.task.get("config"), fd, indent=4)

        args = [
            str(Setting.installer_binary_path),
            "cli",
            "--filename",
            self.img_path.name,
            "--build-dir",
            str(Setting.working_dir),
            "--config",
            str(self.config_path),
            "--size",
            "{}GB".format(self.task.get("size")),
        ]
        # args = ["touch", str(self.img_path)]
        self.installer_log = "{args}\n".format(args=" ".join(args))
        logger.info("Starting {args}\n".format(args=" ".join(args)))

        log_fd = open(str(self.log_path), "w")
        ps = subprocess.Popen(
            args=args,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            close_fds=True,
        )

        logger.info("installer started: {}".format(ps))
        while ps.poll() is None:
            self.installer_log = self.read_log()

            # kill upon request
            if self.canceled:
                logger.info("terminating installer…")
                ps.terminate()
                ps.wait(10)
                ps.kill()
                ps.wait(10)
                break

        ps.wait(10)

        if ps.returncode == 0:
            logger.info("installer ran successfuly.")
        else:
            logger.error("installer failed: {}".format(ps.returncode))

        logger.info("collecting full terminated log")
        self.installer_log = self.read_log()

        # clean up working folder
        self.remove_files()

        if ps.returncode != 0:
            raise subprocess.SubprocessError("installer rc: {}".format(ps.returncode))

    def upload_image(self):
        logger.info("Starting upload")

        logger.info("re-authenticate to ensure token is still valid")
        authenticate(force=True)

        with ftplib.FTP() as ftp:
            logger.info(
                "connecting to {host}:{port}".format(
                    host=self.warehouse_host, port=self.warehouse_port
                )
            )
            ftp.connect(self.warehouse_host, self.warehouse_port, timeout=30)
            logger.info("Authenticating via FTP for user: {}".format(Setting.username))
            ftp.login(Setting.username, REFRESH_TOKEN)
            with open(self.img_path, "rb") as file:
                logger.info("starting FTP upload of {}".format(self.img_path.name))
                ftp.storbinary("STOR {}".format(self.img_path.name), file)
            logger.info("FTP upload complete")

        # retries = 3
        # while retries > 0:
        #     try:
        #         break
        #     except ConnectionRefusedError as error:
        #         retries -= 1
        #         time.sleep(5)
        # else:
        #     raise error
