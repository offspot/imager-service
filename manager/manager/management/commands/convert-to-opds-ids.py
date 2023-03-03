import logging
import re
import sys
import typing

from django.core.management.base import BaseCommand

from manager.models import Configuration
from manager.pibox.packages import get_packages_id

try:
    from .convertdata import fixed_ids, gone_ids
except ImportError:
    print(
        """You must implement update data variables:
- fixed_ids: Dict[str, Tuple(str, str)] = {"old_id.xx": ("new_name", "flavour")}
- gone_ids: List[str] = ["old_id_not_in_lib_anymore.xx"]
"""
    )
    sys.exit(1)

logger = logging.getLogger(__name__)
all_ids = get_packages_id()  # current, on-library IDs


def get_new_id(yaml_id: str) -> typing.Union[str, int]:

    if yaml_id in gone_ids:
        return -1

    # khan videos in fixed_ids dont have the lang suffix
    if yaml_id.startswith("khan-academy-videos_"):
        yaml_id = yaml_id.rsplit(".", 1)[0]

    if yaml_id in fixed_ids:
        name, flavour = fixed_ids.get(yaml_id)[0], fixed_ids.get(yaml_id)[1]
    else:
        name, _ = yaml_id.rsplit(".", 1)
        last_part = name.rsplit("_", 1)[-1]
        flavour = ""
        if last_part in ("nodet", "novid"):
            flavour = {"nodet": "mini", "novid": "maxi"}.get(last_part, last_part)
        if last_part in ("mini", "nopic", "maxi"):
            flavour = last_part
            name = re.sub(f"_{last_part}$", "", name)

    for publisher in ("Kiwix", "openZIM", "WikiProjectMed"):
        opds_id = f"{publisher}:{name}:{flavour}"
        if opds_id in all_ids:
            return opds_id

    return 0


class Command(BaseCommand):
    help = "Convert all YAML-based ZIM packages IDs into OPDS-based human IDs"

    def handle(self, *args, **options):
        # toggle this once you've run the script successfuly
        # and you're confident you can update the DB
        alter = False

        self.stdout.write("looping through all configurations...")

        cant_find = []

        for config in Configuration.objects.all():
            self.stdout.write(f"Config #{config.id}")

            for index, yaml_id in enumerate(config.content_zims):  # keeping order
                # ID is already in current library
                if yaml_id in all_ids:
                    continue

                package_id = get_new_id(yaml_id)

                if package_id == -1:
                    # package disapeared. dropping
                    config.content_zims[index] = None
                    continue

                if not package_id:
                    self.stdout.write(
                        f"cant find replacement ID for {yaml_id} in {config.id}"
                    )
                    cant_find.append(yaml_id)
                    continue

                if options["verbosity"] > 1:
                    self.stdout.write(
                        f"{yaml_id} -> {package_id} in #{config.id}[{index}]"
                    )

                config.content_zims[index] = package_id

            config.content_zims = [pid for pid in config.content_zims if pid]

            if alter:
                config.save()

        self.stdout.write("- " + "\n- ".join(list(set(cant_find))))

        self.stdout.write(self.style.SUCCESS("    done"))
