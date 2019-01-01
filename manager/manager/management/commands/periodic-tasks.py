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
        self.stdout.write("## running periodic tasks...")

        self.stdout.write("updating scheduler data for in-progress orders...")
        for order in Order.objects.filter(status=Order.IN_PROGRESS):
            o = Order.fetch_and_get(order.id)
            self.stdout.write(o.min_id, o.status)

        self.stdout.write(self.style.SUCCESS("    done"))
