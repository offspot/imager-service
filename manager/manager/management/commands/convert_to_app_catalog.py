import logging

from django.core.management.base import BaseCommand

from manager.models import Configuration

logger = logging.getLogger(__name__)

packages_map = {
    "wikifundi_fr": "wikifundi-fr.offspot.kiwix.org",
    "wikifundi_en": "wikifundi-en.offspot.kiwix.org",
    "wikifundi_es": "wikifundi-es.offspot.kiwix.org",
    "edupi": "file-manager.offspot.kiwix.org",
    "nomad": "nomad.offspot.kiwix.org",
    "mathews": "mathews.offspot.kiwix.org",
    "africatik": "africatik-en.offspot.kiwix.org",
    "africatikmd": "africatik-md.offspot.kiwix.org",
}


class Command(BaseCommand):
    help = "Convert all YAML-based ZIM packages IDs " "into OPDS-based human IDs"

    def handle(self, *args, **options):  # noqa: ARG002
        # toggle this once you've run the script successfuly
        # and you're confident you can update the DB
        alter = False

        self.stdout.write("looping through all configurations...")

        for config in Configuration.objects.all():
            self.stdout.write(f"Config #{config.id}")

            if config.content_packages:
                continue

            config.content_packages = []

            for optname, pkgname in packages_map.items():
                option = getattr(config, f"content_{optname}", False)
                if option:
                    config.content_packages.append(pkgname)

                    if options["verbosity"] > 1:
                        self.stdout.write(f"{optname} -> {pkgname} in #{config.id}")

            if alter:
                config.save()

        self.stdout.write(self.style.SUCCESS("    done"))
