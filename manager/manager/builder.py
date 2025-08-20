from dataclasses import dataclass, field

from django.conf import settings
from offspot_config.builder import (
    BRANDING_PATH,
    AppPackage,
    ConfigBuilder,
    FilesPackage,
    get_internal_image,
)
from offspot_config.catalog import app_catalog
from offspot_config.inputs.base import BaseConfig
from offspot_config.oci_images import OCIImage
from offspot_config.utils.dashboard import Link
from offspot_config.utils.download import get_online_rsc_size

from manager.__about__ import get_version
from manager.kiwix_library import catalog
from manager.models import Configuration
from manager.utils import retrieve_branding_file


@dataclass
class ConfigLike:
    name: str = "default"
    ssid: str = "default"
    project_name: str = "default"
    language: str = "en"
    timezone: str = "UTC"
    wifi_password: str | None = None
    admin_account: str = "admin"
    admin_password: str = "admin-password"
    variant: str = ""
    branding_logo: str = ""
    branding_favicon: str = ""
    content_zims: list[str] = field(default_factory=list)  # parsed json
    content_packages: list[str] = field(default_factory=list)  # parsed json
    content_edupi_resources: str | None = None
    content_metrics: bool = False
    option_kiwix_readers: bool = False
    beta_features: list[str] = field(default_factory=list)  # parsed json

    @property
    def size(self) -> int:
        return 1

    @property
    def wifi_protected(self):
        return bool(self.wifi_password)

    @property
    def display_name(self):
        return self.name or self.project_name

    @property
    def current_beta_features(self) -> list[str]:
        """list of currently valid beta features"""
        if not self.beta_features:
            return []
        return [
            feature
            for feature in self.beta_features
            if feature in settings.BETA_FEATURES
        ]

    @property
    def has_any_beta(self) -> bool:
        """whether config has any currently valid beta feature"""
        return bool(self.current_beta_features)

    def has_beta(self, feature: str) -> bool:
        """whether that feature is currently valid and selected"""
        return feature in self.current_beta_features


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
        name=str(config.ssid),
        domain=str(config.project_name),
        welcome_domain="goto.kiwix",
        tld=settings.OFFSPOT_TLD,
        ssid=str(config.ssid),
        passphrase=str(config.wifi_password) if config.wifi_password else None,
        timezone=str(config.timezone),
        environ={
            "ADMIN_USERNAME": str(config.admin_account),
            "ADMIN_PASSWORD": str(config.admin_password),
        },
        write_config=True,
        kiwix_zim_mirror="https://mirror.download.kiwix.org/zim/",
        public_version=get_version(extended=False)
    )

    # add branding
    horizontal = retrieve_branding_file(
        config.branding_logo, is_virtual=isinstance(config, ConfigLike)
    )
    if horizontal:
        builder.add_file(
            url_or_content=horizontal["data"],
            to=str(BRANDING_PATH.joinpath("horizontal-logo-light.png")),
            via="base64",
            size=int(horizontal["size"]),
            is_url=False,
        )
    else:
        builder.add_file(
            **settings.BRANDING_FILES_PAYLOADS["horizontal-logo-light.png"]
        )
    del horizontal

    square = retrieve_branding_file(
        config.branding_favicon, is_virtual=isinstance(config, ConfigLike)
    )
    if square:
        builder.add_file(
            url_or_content=square["data"],
            to=str(BRANDING_PATH.joinpath("square-logo-light.png")),
            via="base64",
            size=int(square["size"]),
            is_url=False,
        )
    else:
        builder.add_file(**settings.BRANDING_FILES_PAYLOADS["square-logo-light.png"])
    del square

    # dashboard links
    links = []
    if config.content_metrics:
        links.append(Link("Metrics", "//metrics.${FQDN}"))

    readers = None
    if config.option_kiwix_readers:
        readers = settings.KIWIX_READERS

    builder.add_dashboard(allow_zim_downloads=True, readers=readers, links=links)
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
            is_url=True,
        )

    builder.add_hwclock()

    if config.content_metrics:
        builder.add_metrics()

    # post-config updates for [beta features]
    if not config.has_any_beta:
        return builder

    if config.has_beta("dashboard-1.4"):
        # change image for dashboard (download and compose)
        dashboard_img = get_internal_image("dashboard")
        if (
            dashboard_img in builder.config["oci_images"]
            and dashboard_img.oci.tag == "1.3.1"
        ):
            dashboard_img_new = OCIImage(
                ident="ghcr.io/offspot/dashboard:1.4.7",
                filesize=179865600,
                fullsize=179749957,
            )
            builder.config["oci_images"].remove(dashboard_img)
            builder.config["oci_images"].add(dashboard_img_new)
            builder.compose["services"]["home"]["image"] = dashboard_img_new.source

    # if config.has_beta("image-creator-1.0"):
    #     # set special image-creator.version prop in YAML that worker understands
    #     # and will have it change imager path
    #     builder.config["image-creator"] = {"version": "1.1.0"}

    return builder
