#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import io
import os
import time
import logging
import tempfile
import subprocess
from pathlib import Path

import requests

from utils.setting import Setting
from utils.download import download_file
from utils.scheduler import (
    get_available_tasks,
    request_task,
    update_task_status,
    upload_logs,
)
from utils.creation import CreationTask


logger = logging.getLogger(__name__)


class CreatorWorker:
    def __init__(self):
        self.running: bool = True

        self.task: dict = None
        self.job: CreationTask = None
        self.log_stream: io.StringIO = None  # stores worker log during job
        self.log_handler: logging.Handler = None  # handles logging during job

    def read_setting(self):
        Setting.read_from_env()

    def check_kiwix_hotspot(self):
        """ check latest version of kiwix-hotspot and download if different """

        # guess latest version
        req = requests.get(
            "https://api.github.com/repos/ideascube/pibox-installer/git/refs/tags"
        )
        try:
            version = req.json()[-1]["ref"].replace("refs/tags/", "")
            version = version[1:]  # remote version (tag) has an extra v at char 0
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
        url = "http://download.kiwix.org/release/kiwix-hotspot/v{version}/kiwix-hotspot-linux.tar.gz".format(
            version=version
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
        """ starts the worker (initialization) """
        logger.info("Welcome to Cardshop Creator worker:")
        self.read_setting()
        self.check_kiwix_hotspot()
        self.free_space()
        self.run_loop()

    def stop(self):
        """ stops worker completely """
        logger.info("received stop request ; shutting down (please wait).")
        # cancelling job and marking as failed
        if self.busy and self.job is not None and self.job.is_alive():
            self.job.stop()
            self.job.join(timeout=30)
            self.mark_task_failed("worker shutdown: {id}".format(id=Setting.username))
            self.cleanup_task()

        self.running = False

    def free_space(self):
        """ clean up cache folder """
        logger.info("clean-up cache folder to free space")
        clean_cache_output = subprocess.run(
            args=[
                Setting.installer_binary_path,
                "cache",
                "--build",
                Setting.working_dir,
                "reset",
            ],
            universal_newlines=True,
            capture_output=True,
            check=True,
        ).stdout
        logger.info(clean_cache_output)

    @property
    def busy(self):
        return self.task is not None

    def start_task(self, task):
        self._attach_logger()
        self.task = task

        # clean up cache
        self.free_space()

        logger.info("Starting to work on {}".format(self.task["_id"]))
        self.job = CreationTask(args=(self.task,))
        self.job.start()

    def _attach_logger(self):
        # plug dedicated stream to logger
        self.log_stream = io.StringIO("")
        self.log_handler = logging.StreamHandler(self.log_stream)
        logger.addHandler(self.log_handler)

    def get_available_tasks(self):
        logger.info("requesting list of tasks for worker {}".format(Setting.username))
        success, tasks = get_available_tasks()
        if not success:
            logger.error("ERROR getting tasks: {}".format(tasks))
            return []
        return tasks

    def request_task(self, task_id):
        logger.info("requesting task #{} to scheduler.".format(task_id))
        success, tid = request_task(task_id)
        return success

    def mark_task_complete(self, output):
        logger.info(
            "informing task #{} completed successfuly.".format(self.task["_id"])
        )
        success, tid = update_task_status(self.task["_id"], "built", output)
        return success

    def mark_task_failed(self, output):
        logger.info("informing task #{} failed.".format(self.task["_id"]))
        success, tid = update_task_status(self.task["_id"], "failed_to_build", output)
        return success

    def upload_creator_log(self, worker_log=None, installer_log=None):
        logger.info("sending logs for task #{}.".format(self.task["_id"]))
        success, tid = upload_logs(
            task_id=self.task["_id"], worker_log=worker_log, installer_log=installer_log
        )

    def send_ack(self):
        logger.info("sending ACK to scheduler. working on #{}".format(self.task["_id"]))

    def read_worker_log(self):
        """ returns worker log for seld.task """
        if self.log_handler is None or self.log_stream is None:
            return None
        logger.removeHandler(self.log_handler)
        self.log_handler.flush()
        self.log_handler.close()
        self.log_handler = None
        self.log_stream.seek(0)
        content = self.log_stream.read()
        self.log_stream.close()
        self.log_stream = None
        return content

    def cleanup_task(self):
        self.upload_creator_log(
            worker_log=self.read_worker_log(), installer_log=self.job.installer_log
        )
        # clean-up
        self.job = None
        self.task = None

    def run_loop(self):
        logger.info("Starting...")

        url = "{api}/tasks".format(api=Setting.api_url)
        logger.info("Working off {}".format(url))

        poll_timer, log_upload_timer = [0], [0]
        while self.running:
            logger.info("running", self.running)
            if self.busy:
                # send ack to scheduler. we're working on self.task
                # self.send_ack()

                if not log_upload_timer.pop():
                    logger.info("periodic log upload..................")
                    self.upload_creator_log(
                        worker_log=None, installer_log=self.job.installer_log
                    )
                    log_upload_timer = Setting.get_timer(Setting.log_upload_interval)

                if not self.job.is_alive():
                    logger.info("job is not alive")
                    if self.job.exception:
                        logger.error("job crashed: {}".format(self.job.exception))
                        # self.mark_task_failed(str(self.job.exception))
                    else:
                        logger.info("job successful")
                        # self.mark_task_complete("ALL GOOD")

                    self.cleanup_task()
            else:
                if not poll_timer.pop():
                    # fetch tasks on scheduler
                    for task in self.get_available_tasks():
                        # notify scheduler we want to take it
                        if not self.request_task(task["_id"]):
                            continue
                        self.start_task(task)
                    poll_timer = Setting.get_timer(Setting.poll_interval)

            # logger.info("ideling for {}s...".format(Setting.idle_interval))
            # time.sleep(Setting.idle_interval)
            time.sleep(1)

        logger.info("exiting gracefuly.")
