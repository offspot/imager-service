#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from base import BaseWorker
from tasks.download import DownloadTask


logger = logging.getLogger(__name__)


class DownloaderWorker(BaseWorker):

    worker_type = "downloader"
    job_cls = DownloadTask
