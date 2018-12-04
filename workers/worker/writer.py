#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from base import BaseWorker
from tasks.write import WriteTask


logger = logging.getLogger(__name__)


class WriterWorker(BaseWorker):

    worker_type = "writer"
    job_cls = WriteTask
