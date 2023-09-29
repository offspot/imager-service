#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

import yaml

try:
    from yaml import CSafeLoader as Loader
except ImportError:
    from yaml import SafeLoader as Loader
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


def get_yaml_catalogs():
    yaml_catalogs = cache_get("YAML_CATALOGS", [])
    if not yaml_catalogs:
        logger.info("Downloading catalogs online")
        try:
            for catalog in CATALOGS:
                yaml_catalogs.append(
                    yaml.load(
                        requests.get(catalog.get("url")).content.decode("utf-8"),
                        Loader=Loader,
                    )
                )
        except Exception as exc:
            logger.error(f"Unable to load ideascube catalog: {exc}")
            raise exc
        cache_set("YAML_CATALOGS", yaml_catalogs)
    return yaml_catalogs


hotspot_languages = [("en", "English"), ("fr", "Fran\xe7ais")]
