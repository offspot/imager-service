from dataclasses import dataclass, field

from django.conf import settings
from offspot_config.builder import AppPackage, ConfigBuilder, FilesPackage
from offspot_config.catalog import app_catalog
from offspot_config.inputs import BaseConfig
from offspot_config.utils.download import get_online_rsc_size

from manager.kiwix_library import catalog
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
    content_zims: list[str] = field(default_factory=list)  # parsed json
    content_packages: list[str] = field(default_factory=list)  # parsed json
    content_edupi_resources: str | None = None
    content_metrics: bool = False

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
    edupi_resources: str | None,
    metrics: bool,
    zims: list[str],
    packages: list[str],
) -> ConfigBuilder:
    """builder from previous collection items"""
    config = ConfigLike(
        content_edupi_resources=edupi_resources,
        content_metrics=metrics,
        content_zims=zims,
        content_packages=packages,
    )

    return prepare_builder_for(config=config)


def prepare_builder_for(config: Configuration | ConfigLike) -> ConfigBuilder:
    builder = ConfigBuilder(
        base=BaseConfig(
            source=settings.BASE_IMAGE_URL,
            rootfs_size=settings.BASE_IMAGE_ROOTFS_SIZE,
        ),
        name=str(config.project_name),
        domain=str(config.project_name),
        welcome_domain="goto.kiwix",
        tld=settings.OFFSPOT_TLD,
        ssid=str(config.project_name),
        passphrase=config.wifi_password,
        timezone=config.timezone,
        environ={
            "ADMIN_USERNAME": str(config.admin_account),
            "ADMIN_PASSWORD": str(config.admin_password),
        },
        write_config=True,
        kiwix_zim_mirror="https://mirror.download.kiwix.org/zim/",
    )
    builder.add_dashboard(allow_zim_downloads=True)
    builder.add_captive_portal()
    builder.add_reverseproxy()

    for zim_ident in config.content_zims:
        builder.add_zim(catalog.get(zim_ident).get_zim_package())

    for package_ident in config.content_packages:
        package = app_catalog[package_ident]
        if isinstance(package, AppPackage):
            builder.add_app(package)
        elif isinstance(package, FilesPackage):
            builder.add_files_package(package)

    if (
        config.content_edupi_resources
        and "file-manager.offspot.kiwix.org" in config.content_packages
    ):
        builder.add_file(
            url_or_content=str(config.content_edupi_resources),
            to="${APP_DIR:file-manager.offspot.kiwix.org}",
            size=get_online_rsc_size(str(config.content_edupi_resources)),
            via="zip",
        )

    builder.add_hwclock()

    if config.content_metrics:
        builder.add_metrics()

    # # branding for dashboard (a single CSS file)
    # builder.add_file(
    #     url_or_content=gen_css_from_dashboard_options(
    #         "https://logo.png", colors="from-logo"
    #     ),
    #     to=str(CONTENT_TARGET_PATH / "dashboard-app/custom.css"),
    #     via="direct",
    #     size=0,
    #     is_url=False,
    # )

    return builder
