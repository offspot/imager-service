import logging
import re
import sys

from django.core.management.base import BaseCommand

from manager.kiwix_library import catalog, to_human_id
from manager.models import Configuration

try:
    from manager.management.commands.convertdata import fixed_ids, gone_ids
except ImportError:
    print(  # noqa: T201
        """You must implement update data variables:
- fixed_ids: Dict[str, Tuple(str, str)] = {"old_id.xx": ("new_name", "flavour")}
- gone_ids: List[str] = ["old_id_not_in_lib_anymore.xx"]
"""
    )
    sys.exit(1)

logger = logging.getLogger(__name__)
# all_ids = get_packages_id()  # current, on-library IDs
all_ids = list(catalog.get_all_ids())


def get_new_id(yaml_id: str) -> str | int:
    # already converted
    if yaml_id in all_ids:
        return yaml_id

    if yaml_id in gone_ids:
        return -1

    # khan videos in fixed_ids dont have the lang suffix
    if yaml_id.startswith("khan-academy-videos_"):
        yaml_id = yaml_id.rsplit(".", 1)[0]

    repl_flavours = {
        "nodet": "mini",
        "novid": "maxi",
        "_mini": "mini",
        "_maxi": "maxi",
        "_nopic": "nopic",
    }

    if yaml_id in fixed_ids:
        name, flavour = fixed_ids.get(yaml_id)[0], fixed_ids.get(yaml_id)[1]
    else:
        name, _ = yaml_id.rsplit(".", 1)
        last_part = name.rsplit("_", 1)[-1]
        flavour = ""
        if last_part in repl_flavours:
            flavour = repl_flavours.get(last_part, last_part)
        if last_part in ("mini", "nopic", "maxi"):
            flavour = last_part
            name = re.sub(f"_{last_part}$", "", name)

    for publisher in ("Kiwix", "openZIM", "WikiProjectMed"):
        opds_id = to_human_id(name, publisher, flavour)
        if opds_id in all_ids:
            return opds_id

    return 0


class Command(BaseCommand):
    help = (  # noqa: A003
        "Convert all YAML-based ZIM packages IDs " "into OPDS-based human IDs"
    )

    def handle(self, *args, **options):  # noqa: ARG002
        # toggle this once you've run the script successfuly
        # and you're confident you can update the DB
        alter = True

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

        self.stdout.write(str(len(cant_find)))
        self.stdout.write("- " + "\n- ".join(list(set(cant_find))))

        self.stdout.write(self.style.SUCCESS("    done"))
