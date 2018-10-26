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
        "url": "http://download.kiwix.org/library/ideascube.yml",
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

ideascube_languages = collections.OrderedDict(
    [
        ("am", "አማርኛ"),
        ("ar", "\u0627\u0644\u0639\u0631\u0628\u064a\u0651\u0629"),
        ("bm", "Bambara"),
        ("en", "English"),
        ("es", "Espa\xf1ol"),
        ("fa-ir", "فارسی"),
        ("fr", "Fran\xe7ais"),
        ("ku", "Kurdî"),
        ("so", "Af-soomaali"),
        ("sw", "Kiswahili"),
    ]
)

MIRROR = "http://mirror.download.kiwix.org"
