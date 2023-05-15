#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
import logging
import re
from typing import Optional

import xmltodict
import requests

from manager.utils import cache_get, cache_set

CATALOG_URL = "https://library.kiwix.org/catalog/v2"
logger = logging.getLogger(__name__)


def to_human_id(
    name: str, publisher: Optional[str] = "", flavour: Optional[str] = ""
) -> str:
    """periodless exchange identifier for ZIM Title"""
    publisher = publisher or "openZIM"
    flavour = flavour or ""
    return f"{publisher}:{name}:{flavour}"


def get_catalog():
    books = cache_get("OPDS_CATALOG", {})
    if books:
        return books

    # get all entries from OPDS API
    try:
        resp = requests.get(f"{CATALOG_URL}/entries", params={"count": "-1"})
        resp.raise_for_status()
        catalog = xmltodict.parse(resp.content)
        if "feed" not in catalog:
            raise ValueError("Malformed OPDS response")
        if not int(catalog["feed"]["totalResults"]):
            raise IOError("Catalog has no entry; probably misbehaving")
        for entry in catalog["feed"]["entry"]:
            links = {link["@type"]: link for link in entry["link"]}
            version = datetime.datetime.fromisoformat(
                re.sub(r"[A-Z]$", "", entry["updated"])
            ).strftime("%Y-%m-%d")
            flavour = entry.get("flavour") or ""
            publisher = entry.get("publisher", {}).get("name") or ""
            ident = to_human_id(
                name=entry["name"],
                publisher=publisher,
                flavour=flavour,
            )
            books[ident] = {
                "id": ident,
                "name": entry["name"],
                "title": entry["title"],
                "description": entry["summary"],
                "language": entry["language"] or "eng",
                "tags": entry["tags"].split(";"),
                "flavour": flavour,
                "size": int(links["application/x-zim"]["@length"]),
                "url": re.sub(r".meta4$", "", links["application/x-zim"]["@href"]),
                "illustration": links["image/png;width=48;height=48;scale=1"]["@href"],
                "version": version,
            }
    except Exception as exc:
        logger.error(f"Unable to load catalog from OPDS: {exc}")
        raise exc
    cache_set("OPDS_CATALOG", books)
    return books


hotspot_languages = [("en", "English"), ("fr", "Fran\xe7ais")]
