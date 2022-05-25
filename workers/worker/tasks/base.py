#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import threading
import subprocess


from utils.setting import Setting
from utils.scheduler import update_task_status

ONE_KiB = 2**10


class BaseTask(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.exception: Exception = None  # exception to be re-raised by caller
        self.task: dict = {}
        self.logs = {}

        self._should_stop: bool = False  # stop flag

        self.extra = {}  # extra data to populate and send

        self.logger = logging.getLogger(__name__)  # to be overwritten

    def stop(self):
        self.logger.info("stopping thread")
        self._should_stop = True

    @property
    def canceled(self):
        return self._should_stop

    def report_status(self, status, status_log=None):
        self.logger.info(
            "updating task #{} status to: {}".format(self.task["_id"], status)
        )
        success, tid = update_task_status(
            self.task["_id"], status, status_log, extra=self.extra
        )
        return success

    def file_path(self, ext):
        return Setting.working_dir.joinpath(self.task["fname"]).with_suffix(f".{ext}")

    def read_log(self, path):
        cat = subprocess.run(["cat", str(path)], text=True, capture_output=True)
        return "{stdout}\n{stderr}".format(
            stdout=cat.stdout or "", stderr=cat.stderr or ""
        )

    def run(self):
        self.task, self.logger = self._args
