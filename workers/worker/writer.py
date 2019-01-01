#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from base import BaseWorker
from tasks.write import WriteTask
from utils.setting import Setting
from utils.scheduler import send_sos


logger = logging.getLogger(__name__)


class WriterWorker(BaseWorker):

    worker_type = "writer"
    job_cls = WriteTask

    def check_device(self):
        if not Setting.usb_path.exists():
            send_sos(
                "{usb} does not exists ({hostdev} on host)".format(
                    usb=str(Setting.usb_path), hostdev=Setting.host_device
                )
            )
            raise OSError(
                "USB device ({}) does not exists. hara-kiri.".format(
                    str(Setting.usb_path)
                )
            )

    def start(self):
        super().start(run_loop=False)
        self.check_device()
        self.run_loop()
