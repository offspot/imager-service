#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import collections

import langcodes

from manager.pibox.data import YAML_CATALOGS
from manager.pibox.util import human_readable_size


def get_packages_flat():
    packages = []
    for catalog in YAML_CATALOGS:
        packages += catalog["all"].values()
    return packages


ALL_PACKAGES = get_packages_flat()


def get_parsed_package(package):
    name = package.get("name")
    name_tag_regexp = r"(.+)\[(.+)\]$"
    if re.match(name_tag_regexp, name):
        name, tags_str = re.match(name_tag_regexp, name).groups()
        name = name.strip()
        tags = [t.strip() for t in tags_str.split(",")]
    else:
        tags = []
    key = "_".join(package.get("langid").rsplit(".", 1))
    package.update(
        {
            "hsize": human_readable_size(package.get("size", 0)).replace(" ", " "),
            "tags": tags,
            "sname": name,
            "skey": key.replace(".", "__"),
            "key": key,
        }
    )
    return package


def get_packages_by_lang():
    packages = {}
    for package in ALL_PACKAGES:
        plang = langcodes.Language.get(package.get("language")).language
        pid = package.get("langid")
        if not plang or not pid:
            continue
        if plang not in packages.keys():
            packages[plang] = {}
        packages[plang].update({pid: get_parsed_package(package)})
    return packages


def get_packages_id():
    return [package.get("langid") for package in ALL_PACKAGES if package.get("langid")]


def get_packages_langs():
    def _name(lk, ln):
        return ln if ln else lk.upper()

    return collections.OrderedDict(
        sorted(
            [
                (
                    langcodes.Language.get(l).language,
                    langcodes.Language.get(l).language_name(),
                )
                for l in PACKAGES_BY_LANG
            ],
            key=lambda x: x[1],
        )
    )


def get_package(pid):
    """ retrieve package from its ID """
    for package in ALL_PACKAGES:
        if package.get("langid") == pid:
            return package
    return None


PACKAGES_BY_LANG = get_packages_by_lang()
PACKAGES_LANGS = get_packages_langs()
