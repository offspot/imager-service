#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import collections

import langcodes

from manager.pibox.data import get_catalog


def get_packages_by_lang():
    packages = {}
    for package in get_catalog().values():
        plang = langcodes.Language.get(package["language"]).language
        if not plang:
            continue
        if plang not in packages.keys():
            packages[plang] = {}
        packages[plang][package["id"]] = package
    return packages


def get_packages_id():
    return list(get_catalog().keys())


def get_packages_langs():
    return collections.OrderedDict(
        sorted(
            [
                (
                    langcodes.Language.get(lang).language,
                    langcodes.Language.get(lang).language_name(),
                )
                for lang in get_packages_by_lang()
                if lang
            ],
            key=lambda x: x[1],
        )
    )


def get_package(pid):
    """retrieve package from its ID"""
    return get_catalog().get(pid)
