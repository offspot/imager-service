#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django.contrib.auth.decorators import user_passes_test

logger = logging.getLogger(__name__)


def staff_required(func):
    return user_passes_test(lambda u: u.is_staff)(func)
