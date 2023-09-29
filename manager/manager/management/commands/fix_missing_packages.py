#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django.core.management.base import BaseCommand

from manager.models import Configuration
from manager.pibox.packages import get_packages_id

logger = logging.getLogger(__name__)
all_ids = get_packages_id()


def find_correct_package(pid):
    # check novid->maxi
    if "novid" in pid:
        test = pid.replace("novid", "maxi")
        if test in all_ids:
            return test

    # check nodet->mini
    if "nodet" in pid:
        test = pid.replace("nodet", "mini")
        if test in all_ids:
            return test

    # no flavour->maxi
    ident, lang = pid.rsplit(".", 1)
    test = f"{ident}_maxi.{lang}"
    if test in all_ids:
        return test

    # special cases
    if pid == "wikipedia_en_100000.en":
        return "wikipedia_en_top_maxi.en"
    if pid == "wikipedia_en_maths_maxi.en":
        return "wikipedia_en_mathematics_maxi.en"


class Command(BaseCommand):
    help = "Executes periodic tasks"  # noqa: A003

    def handle(self, *args, **options):  # noqa: ARG002
        self.stdout.write("## fixing package names due to changes in flavour...")

        self.stdout.write("looping through all configurations...")
        for config in Configuration.objects.all():
            for index, pid in enumerate(config.content_zims):
                if pid not in all_ids:
                    npid = find_correct_package(pid)
                    if npid is None:
                        self.stdout.write(
                            f"could not find replacement ID for {config.id} in {pid}"
                        )
                    else:
                        self.stdout.write(f"replacing {pid} with {npid} in {config.id}")
                        config.content_zims[index] = npid
                        config.save()

        self.stdout.write(self.style.SUCCESS("    done"))
