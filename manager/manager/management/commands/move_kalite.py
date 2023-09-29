import datetime
import json
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from manager.models import Configuration

logger = logging.getLogger(__name__)

KALITE_ZIMS = {
    "en": "khanacademy_en_all.en",
    "fr": "khanacademy_fr_all.fr",
    "es": "khanacademy_es_all.es",
}


class Command(BaseCommand):
    help = (  # noqa: A003
        "Convert all YAML-based ZIM packages IDs " "into OPDS-based human IDs"
    )

    def handle(self, *args, **options):  # noqa: ARG002
        # toggle this once you've run the script successfuly
        # and you're confident you can update the DB
        alter = False

        configs = {}

        self.stdout.write("looping through KA-Lite using configurations...")

        for config in Configuration.objects.filter(
            Q(content_kalite_fr=True)
            | Q(content_kalite_en=True)
            | Q(content_kalite_es=True)
        ):
            self.stdout.write(f"Config #{config.id}")

            for lang in ("en", "es", "fr"):
                if getattr(config, f"content_kalite_{lang}"):
                    self.stdout.write(f"  kalite_{lang}=True")
                    if KALITE_ZIMS[lang] not in config.content_zims:
                        if not config.content_zims:
                            config.content_zims = []
                        config.content_zims.append(KALITE_ZIMS[lang])
                    setattr(config, f"content_kalite_{lang}", False)
                    if not configs.get(config.id):
                        configs[config.id] = {"previous_size": config.size}
                    configs[config.id][lang] = True

            if options["verbosity"] > 1:
                self.stdout.write(f"  -- {config.content_zims}")

            if alter:
                config.save()

        with open(f"all_configs_{datetime.datetime.now().isoformat()}", "w") as fh:
            json.dump(configs, fh)

        self.stdout.write(self.style.SUCCESS("    done"))
