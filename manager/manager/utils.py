#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def cache_set(key, data):
    logger.debug("setting data for `{}`".format(key))
    cache.set(key, json.dumps(data))


def cache_get(key, default=None):
    logger.debug("fetching data for `{}`".format(key))
    try:
        return json.loads(cache.get(key))
    except Exception:
        return default
