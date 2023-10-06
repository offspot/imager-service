import pathlib
from dataclasses import dataclass, field

from django.conf import settings
from offspot_config.builder import ConfigBuilder
from offspot_config.catalog import app_catalog, get_app_path
from offspot_config.constants import CONTENT_TARGET_PATH
from offspot_config.inputs import BaseConfig
from offspot_config.utils.download import get_online_rsc_size
from offspot_config.utils.misc import format_size
from offspot_config.zim import get_zim_package

from manager.models import Configuration


@dataclass
class ConfigLike:
    name: str = "default"
    project_name: str = "default"
    language: str = "en"
    timezone: str = "UTC"
    wifi_password: str | None = None
    admin_account: str = "admin"
    admin_password: str = "admin-password"
    branding_logo: str = ""
    branding_favicon: str = ""
    branding_css: str = ""
    content_zims: list[str] = field(default_factory=list)  # parsed json
    content_wikifundi_fr: bool = False
    content_wikifundi_en: bool = False
    content_wikifundi_es: bool = False
    content_edupi: bool = False
    content_edupi_resources: str | None = None
    content_nomad: bool = False
    content_mathews: bool = False
    content_africatik: bool = False
    content_africatikmd: bool = False

    @property
    def size(self) -> int:
        return 1

    @property
    def wifi_protected(self):
        return bool(self.wifi_password)

    @property
    def display_name(self):
        return self.name or self.project_name


def gen_css_from_dashboard_options(logo_url: str, colors) -> str:
    if logo_url:
        ...
    if colors:
        ...
    return """:root {
  --main-color: blue;
  --secondary-color: yellow;
}
"""


def prepare_builder_for_collection(
    *,
    edupi: bool,
    edupi_resources: str | None,
    nomad: bool,
    mathews: bool,
    africatik: bool,
    africatikmd: bool,
    packages: list[str],
    wikifundi_languages: list[str],
) -> ConfigBuilder:
    """builder from previous collection items"""
    config = ConfigLike(
        content_edupi=edupi,
        content_edupi_resources=edupi_resources,
        content_nomad=nomad,
        content_mathews=mathews,
        content_africatik=africatik,
        content_africatikmd=africatikmd,
        content_wikifundi_fr="fr" in wikifundi_languages,
        content_wikifundi_en="en" in wikifundi_languages,
        content_wikifundi_es="es" in wikifundi_languages,
        content_zims=packages,
    )

    return prepare_builder_for(config=config)


def prepare_builder_for(config: Configuration | ConfigLike) -> ConfigBuilder:
    builder = ConfigBuilder(
        base=BaseConfig(
            source=settings.BASE_IMAGE_URL,
            rootfs_size=settings.BASE_IMAGE_ROOTFS_SIZE,
        ),
        name=config.name,
        domain=config.name,
        tld=settings.OFFSPOT_TLD,
        ssid=config.name,
        passphrase=None,
        environ={
            "ADMIN_USERNAME": config.admin_account,
            "ADMIN_PASSWORD": config.admin_password,
        },
    )
    builder.add_dashboard(allow_zim_downloads=True)
    builder.add_hwclock()
    builder.add_captive_portal()
    builder.add_reverseproxy()

    for zim_ident in config.content_zims:
        builder.add_zim(get_zim_package(zim_ident))

    for lang in ("fr", "en", "es"):
        if getattr(config, f"content_wikifundi_{lang}"):
            builder.add_app(
                app_catalog.get_apppackage(f"wikifundi-{lang}.offspot.kiwix.org")
            )

    if config.content_edupi:
        builder.add_app(
            app_catalog.get_apppackage("edupi.offspot.kiwix.org"),
            environ={"SRC_DIR": "/data/source"},
        )
        if config.content_edupi_resources:
            builder.add_file(
                url_or_content=str(config.content_edupi_resources),
                to=f'{get_app_path(app_catalog.get_apppackage("edupi.offspot.kiwix.org"))}/source',
                size=get_online_rsc_size(str(config.content_edupi_resources)),
                via="zip",
            )

    if config.content_nomad:
        builder.add_files_package(
            app_catalog.get_filespackage("nomad.offspot.kiwix.org")
        )

    if config.content_mathews:
        builder.add_files_package(
            app_catalog.get_filespackage("mathews.offspot.kiwix.org")
        )

    if config.content_africatik:
        builder.add_files_package(
            app_catalog.get_filespackage("africatik-en.offspot.kiwix.org")
        )

    if config.content_africatikmd:
        builder.add_files_package(
            app_catalog.get_filespackage("africatik-md.offspot.kiwix.org")
        )

    # branding for dashboard (a single CSS file)
    builder.add_file(
        url_or_content=gen_css_from_dashboard_options(
            "https://logo.png", colors="from-logo"
        ),
        to=str(CONTENT_TARGET_PATH / "dashboard-app/custom.css"),
        via="direct",
        size=0,
        is_url=False,
    )

    return builder
