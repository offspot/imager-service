#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu
import datetime
import logging

from django.core.management.base import BaseCommand

from manager.models import Order, Profile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Executes periodic tasks"

    def handle(self, *args, **options):  # noqa: ARG002
        logger.info("## running periodic tasks...")
        now = datetime.datetime.now(tz=datetime.UTC)

        logger.info("updating scheduler data for in-progress orders...")
        for order in Order.objects.filter(status=Order.IN_PROGRESS):
            o = Order.fetch_and_get(order.id)
            logger.debug(f"..{o.min_id}: {o.status}")

        logger.info("disabling expired user accounts...")
        for profile in Profile.objects.filter(expire_on__lte=now, user__is_active=True):
            logger.info(f"  disabling {profile.username}: {profile}")
            profile.user.is_active = False
            profile.user.save()
            profile.expire_on = None
            profile.save()

        logger.info(">done")
