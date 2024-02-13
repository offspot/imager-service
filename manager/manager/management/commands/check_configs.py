import logging

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from manager.models import (
    Configuration,
    validate_admin_login,
    validate_admin_pwd,
    validate_language,
    validate_project_name,
    validate_timezone,
    validate_wifi_pwd,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Convert all YAML-based ZIM packages IDs " "into OPDS-based human IDs"

    def handle(self, *args, **options):  # noqa: ARG002

        self.stdout.write("looping through all configurations...")

        for config in Configuration.objects.all():
            try:
                validate_admin_login(config.admin_account)
            except ValidationError:
                self.stdout.write(f"#{config.id}: {config.admin_account=}")

            try:
                validate_admin_pwd(config.admin_password)
            except ValidationError:
                self.stdout.write(f"#{config.id}: {config.admin_password=}")

            try:
                validate_language(config.language)
            except ValidationError:
                self.stdout.write(f"#{config.id}: {config.language=}")

            try:
                validate_project_name(config.project_name)
            except ValidationError:
                self.stdout.write(f"#{config.id}: {config.project_name=}")

            try:
                validate_timezone(config.timezone)
            except ValidationError:
                self.stdout.write(f"#{config.id}: {config.timezone=}")

            if config.wifi_password is not None:
                try:
                    validate_wifi_pwd(config.wifi_password)
                except ValidationError:
                    self.stdout.write(f"#{config.id}: {config.wifi_password=}")
