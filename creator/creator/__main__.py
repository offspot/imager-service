#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import signal
import logging

from worker import CreatorWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    worker = CreatorWorker()

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
