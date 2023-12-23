#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import io
import time
import logging

from utils.setting import Setting
from utils.scheduler import (
    get_available_tasks,
    request_task,
    get_task,
    upload_logs,
    set_worker_type,
)
from tasks.base import BaseTask


logger = logging.getLogger(__name__)


class BaseWorker:

    worker_type: str = None  # creator, downloader, writer
    job_cls: BaseTask = None

    def __init__(self):
        self.running: bool = True

        self.task: dict = None
        self.job: self.job_cls = None
        self.log_stream: io.StringIO = None  # stores worker log during job
        self.log_handler: logging.Handler = None  # handles logging during job

        set_worker_type(self.worker_type)

    def read_setting(self):
        Setting.read_from_env()

    def start(self, run_loop=True):
        """starts the worker (initialization)"""
        logger.info("Welcome to Imager {} worker:".format(self.worker_type))
        self.read_setting()
        if run_loop:
            self.run_loop()

    def stop(self):
        """stops worker completely"""
        logger.info("received stop request ; shutting down (please wait).")
        # cancelling job and marking as failed
        if self.busy and self.job is not None and self.job.is_alive():
            self.job.stop()
            self.job.join(timeout=30)
            self.cleanup_task()

        self.running = False

    @property
    def busy(self):
        return self.task is not None

    def start_task(self, task):
        self._attach_logger()
        self.task = task

        logger.info("Starting to work on {}".format(self.task["_id"]))
        self.job = self.job_cls(args=(self.task, logger))
        self.job.start()

    def stop_task(self):
        if not self.busy:
            return

        if self.job is not None and self.job.is_alive():
            self.job.stop()
            self.job.join(timeout=30)

        self.cleanup_task()

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

    def upload_worker_logs(self, logs):
        logger.info("sending logs for task #{}.".format(self.task["_id"]))
        success, tid = upload_logs(task_id=self.task["_id"], logs=logs)

    def send_ack(self):
        logger.info("sending ACK to scheduler. working on #{}".format(self.task["_id"]))

    def read_worker_log(self):
        """returns worker log for seld.task"""
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
        logs = {"worker_log": self.read_worker_log()}
        if self.job:
            logs.update(self.job.logs)
        self.upload_worker_logs(logs)
        # clean-up
        self.job = None
        self.task = None

    @property
    def has_been_canceled(self):
        if not self.busy:
            return False
        success, task = get_task(self.task["_id"])
        if success:
            return task.get("status") == "canceled"
        return False

    def run_loop(self):
        logger.info("Starting...")

        url = "{api}/tasks/{type}".format(api=Setting.api_url, type=self.worker_type)
        logger.info("Working off {}".format(url))

        poll_timer, log_upload_timer = [0], [0]
        while self.running:
            if self.busy:
                # send ack to scheduler. we're working on self.task
                # self.send_ack()

                if not log_upload_timer.pop():
                    logger.info("periodic log upload..................")
                    self.upload_worker_logs(self.job.logs)
                    log_upload_timer = Setting.get_timer(Setting.log_upload_interval)

                if self.has_been_canceled:
                    logger.info("task cancelation requested. stopping task")
                    self.stop_task()
                    continue

                if not self.job.is_alive():
                    logger.info("job is not alive")
                    if self.job.exception:
                        logger.error("job crashed: {}".format(self.job.exception))
                    else:
                        logger.info("job successful")

                    self.cleanup_task()
            else:
                if not poll_timer.pop():
                    # fetch tasks on scheduler
                    for task in self.get_available_tasks():
                        # skip tasks that are scheduled for other workers
                        try:
                            if (
                                task["worker"] is not None
                                and task["worker"] != Setting.username
                            ):
                                continue
                            # TODO: remove
                            if not task["upload_uri"].startswith("s3://"):
                                continue
                            if task.get("config_yaml", ""):
                                continue
                        except Exception:
                            pass

                        # notify scheduler we want to take it
                        if self.request_task(task["_id"]):
                            self.start_task(task)
                            break
                    poll_timer = Setting.get_timer(Setting.poll_interval)

            time.sleep(1)

        logger.info("exiting gracefuly.")
