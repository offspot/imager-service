#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from django import template

from manager.pibox import get_parsed_package
from manager.pibox.util import human_readable_size

register = template.Library()


def human_size(value, binary=True):
    return human_readable_size(value, binary)

register.filter('human_size', human_size)


def parsed_sname(package):
    return get_parsed_package(package)['sname']

register.filter('parsed_sname', parsed_sname)
