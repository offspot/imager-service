#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django.core.management.base import BaseCommand

from manager.models import Order

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Executes periodic tasks"

    def handle(self, *args, **options):
        logger.info("## running periodic tasks...")

        logger.info("updating scheduler data for in-progress orders...")
        for order in Order.objects.filter(status=Order.IN_PROGRESS):
            o = Order.fetch_and_get(order.id)
            logger.debug(f"..{o.min_id}: {o.status}")

        logger.info(">done")
