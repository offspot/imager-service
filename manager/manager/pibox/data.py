#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import collections

import yaml
import requests

from manager.utils import cache_get, cache_set

logger = logging.getLogger(__name__)

CATALOGS = [
    {
        "name": "Kiwix",
        "description": "Kiwix ZIM Content",
        "url": "http://mirror.download.kiwix.org/library/ideascube.yml",
    }
]

YAML_CATALOGS = cache_get("YAML_CATALOGS", [])
if not len(YAML_CATALOGS):
    logger.info("Downloading catalogs online")
    try:
        for catalog in CATALOGS:
            YAML_CATALOGS.append(
                yaml.load(requests.get(catalog.get("url")).content.decode("utf-8"))
            )
    except Exception:
        raise
    cache_set("YAML_CATALOGS", YAML_CATALOGS)

hotspot_languages = [("en", u"English"), ("fr", u"Fran\xe7ais")]

MIRROR = "http://mirror.download.kiwix.org"
