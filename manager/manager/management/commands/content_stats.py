import logging
from collections import OrderedDict

from django.core.management.base import BaseCommand

from manager.models import Configuration

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Get info content usage stats"

    def handle(self, *args, **options):  # noqa: ARG002
        content: dict[str, int] = {}

        qs = Configuration.objects.all()

        self.stdout.write(f"looping through {qs.count()} configurations")

        for config in qs:

            for zimid in config.content_zims:
                if zimid not in content:
                    content[zimid] = 1
                else:
                    content[zimid] += 1

        content = OrderedDict(
            sorted(content.items(), key=lambda item: item[1], reverse=True)
        )

        top = max(content.values())

        for zimid, nb in content.items():
            if nb < top // 10:
                break
            print(f"{zimid},{nb}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("done"))
