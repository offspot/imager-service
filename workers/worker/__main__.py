#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import signal
import logging

from writer import WriterWorker
from creator import CreatorWorker
from downloader import DownloaderWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


WORKERS = {
    "creator": CreatorWorker,
    "downloader": DownloaderWorker,
    "writer": WriterWorker,
}


def main(worker_cls):
    worker = worker_cls()

    def signal_handler(sig, frame):
        logger.error("requesting quit via {}".format(sig))
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)

    try:
        worker.start()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    try:
        worker_type = os.getenv("WORKER_TYPE", sys.argv[-1])
        worker_cls = WORKERS.get(worker_type)
        if not worker_cls:
            raise NotImplementedError("{} worker does not exists".format(worker_type))
    except (KeyError, NotImplementedError):
        logger.error("Unspecified worker type: --{}--".format(sys.argv))
    else:
        main(worker_cls)
