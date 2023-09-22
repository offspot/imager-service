from typing import Any, List, Optional
from dataclasses import asdict, dataclass, field

from typeguard import typechecked
from docker_export import Image
import yaml
from yaml import dump

try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper


from manager.pibox.packages import get_package


class BlockStr(str):
    ...


def blockstr_representer(dumper, data):
    style = "|"
    tag = "tag:yaml.org,2002:str"
    return dumper.represent_scalar(tag, data, style=style)


yaml.add_representer(BlockStr, blockstr_representer, Dumper=Dumper)


@typechecked
@dataclass(kw_only=True)
class BaseImage:
    source: str
    root_size: int


@typechecked
@dataclass(kw_only=True)
class Package:
    kind: str
    title: str
    description: str
    languages: Optional[List[str]] = None
    tags: Optional[List[str]] = field(default_factory=list)
    icon: Optional[str] = None


@typechecked
@dataclass(kw_only=True)
class ZimPackage(Package):
    url: str
    title: Optional[str] = None


@typechecked
@dataclass(kw_only=True)
class AppPackage(Package):
    image: str
    image_filesize: int
    image_fullsize: int
    download_url: Optional[str] = None
    download_size: Optional[int] = None

    @property
    def oci_image(self):
        return OCIImage(
            name=self.image, filesize=self.image_filesize, fullsize=self.image_fullsize
        )


@typechecked
@dataclass(kw_only=True)
class FilesPackage(Package):
    download_url: str
    download_size: Optional[int] = None


OFFSPOT_CATALOG = {
    "wikifundi-fr.offspot.kiwix.org": AppPackage(
        kind="app",
        title="WikiFundi",
        description="Environnement qui vous permet de créer "
        "des articles Wikipédia hors-ligne (en français)",
        languages=["fra"],
        tags=["Wikipedia"],
        icon="https://drive.offspot.it/wikifundi/wikifundi_logo.png",
        image="ghcr.io/offspot/wikifundi:1.0",
        image_filesize=1997875200,
        image_fullsize=1997766122,
        download_url="https://drive.offspot.it/wikifundi/fr_2021-12.tar",
        download_size=4723138560,
    ),
    "wikifundi-en.offspot.kiwix.org": AppPackage(
        kind="app",
        title="WikiFundi",
        description="Offline editable environment that provides "
        "a similar experience to editing Wikipedia online (in English)",
        languages=["eng"],
        tags=["Wikipedia"],
        icon="https://drive.offspot.it/wikifundi/wikifundi_logo.png",
        image="ghcr.io/offspot/wikifundi:1.0",
        image_filesize=1997875200,
        image_fullsize=1997766122,
        download_url="https://drive.offspot.it/wikifundi/en_2021-12.tar",
        download_size=5477140480,
    ),
    "wikifundi-es.offspot.kiwix.org": AppPackage(
        kind="app",
        title="WikiFundi",
        description="Entorno editable sin conexión que brinda "
        "una experiencia similar a la edición de Wikipedia en línea (en español)",
        languages=["spa"],
        tags=["Wikipedia"],
        icon="https://drive.offspot.it/wikifundi/wikifundi_logo.png",
        image="ghcr.io/offspot/wikifundi:1.0",
        image_filesize=1997875200,
        image_fullsize=1997766122,
        download_url="https://drive.offspot.it/wikifundi/es_2021-12.tar",
        download_size=5842176000,
    ),
    "edupi.offspot.kiwix.org": AppPackage(
        kind="app",
        title="Ressources EduPi",
        description="Accès à diverses ressources",
        languages=["mul"],
        tags=["files"],
        image="ghcr.io/offspot/edupi:1.0",
        image_filesize=591226880,
        image_fullsize=591129543,
    ),
    "nomad.offspot.kiwix.org": FilesPackage(
        kind="files",
        title="Nomad exercices du CP à la 3è",
        description="Application Android",
        languages=["fra"],
        tags=["android"],
        icon="https://drive.offspot.it/nomad/nomad_logo.png",
        download_url="https://drive.offspot.it/nomad/"
        "nomadeducation_fr_android_2021-11.zip",
        download_size=116444328,
    ),
    "mathews.offspot.kiwix.org": FilesPackage(
        kind="files",
        title="Chasse au trésor Math Mathews",
        description="Un jeu pour faire des maths (6-9 ans)",
        languages=["fra"],
        tags=["android"],
        icon="https://drive.offspot.it/mathews/mathmathews_logo.png",
        download_url="https://drive.offspot.it/mathews/mathmathews_fr_android_1.6.zip",
        download_size=35710192,
    ),
    "africatik-en.offspot.kiwix.org": FilesPackage(
        kind="files",
        title="Africatik Écoles numériques",
        description="Applications éducatives adaptées au contexte culturel "
        "africain (version Écoles numériques)",
        languages=["fra"],
        tags=["android", "windows"],
        icon="https://drive.offspot.it/africatik/africatik_logo.png",
        download_url="https://drive.offspot.it/africatik/"
        "africatik_fr_ecoles-numeriques_2023-02.zip",
        download_size=13906969131,
    ),
    "africatik-md.offspot.kiwix.org": FilesPackage(
        kind="files",
        title="Africatik Maisons digitales",
        description="Applications éducatives adaptées au contexte culturel "
        "africain (version Maisons digitales)",
        languages=["fra"],
        tags=["android", "windows"],
        icon="https://drive.offspot.it/africatik/africatik_logo.png",
        download_url="https://drive.offspot.it/africatik/"
        "africatik_fr_maisons-digitales_2023-02.zip",
        download_size=4394410977,
    ),
}


############# COMMON


def get_size_for(payload):
    tar_images_size = sum([image.filesize for image in payload["config"].all_images])
    expanded_images_size = sum(
        [image.fullsize for image in payload["config"].all_images]
    )
    expanded_files_size = sum([file.fullsize for file in payload["config"].all_files])

    raw_content_size = sum([tar_images_size, expanded_images_size, expanded_files_size])
    margin = get_margin_for(raw_content_size)
    min_image_size = sum([payload["config"].base.rootfs_size, raw_content_size, margin])

    return min_image_size


#############


# services:
#   httpd:
#     container_name: base-httpd
#     image: "ghcr.io/offspot/base-httpd:1.0"
#     pull_policy: never
#     read_only: true
#     restart: unless-stopped
#     ports:
#       - "80:80"
#     volumes:
#       - type: bind
#         source: /boot/offspot.yaml
#         target: /var/www/offspot.yaml
#         read_only: true
#       - type: bind
#         source: /boot/offspot.yaml
#         target: /var/www/offspot.yaml
#         read_only: true


class OCIImage:
    kind: str = "image"  # Item interface

    def __init__(
        self, name: str, filesize: int, fullsize: int, url: Optional[str] = None
    ):
        self.oci: Image = Image.parse(name)
        self.url = url
        self.filesize = filesize
        self.fullsize = fullsize

    @property
    def size(self) -> int:  # Item interface
        return self.filesize

    @property
    def source(self) -> str:  # Item interface
        return str(self.oci)

    def __repr__(self):
        return f"{self.__class__.__name__}<{repr(self.oci)}>"

    def __str__(self):
        return str(self.oci)

    def to_dict(self):
        return {
            "ident": str(self.oci),
            "filesize": self.filesize,
            "fullsize": self.fullsize,
        }


def ociimage_representer(self, data: OCIImage):
    return self.represent_mapping("tag:yaml.org,2002:map", data.to_dict().items())


yaml.add_representer(OCIImage, ociimage_representer, Dumper=Dumper)


class File:
    ...


class ConfigBuilder:
    def __init__(self, base):
        self.config = {
            "base": {"source": base.source, "root_size": base.root_size},
            "output": {"size": None},
            "oci_images": [],
            "files": [],
            "write_config": False,
            # "offspot": {},
            "offspot": {"containers": {"name": "offspot", "services": {}}},
        }
        # self.compose = {"name": "offspot", "services": {}}

        self.dashboard_entries = []
        self.file_entries = []

        self.with_kiwixserve: bool = False
        self.with_files: bool = False
        self.with_reverseproxy: bool = False
        self.with_dashboard: bool = False
        self.with_captive_portal: bool = False
        self.with_hwclock: bool = False

    @property
    def compose(self):
        return self.config["offspot"]["containers"]

    def add_package(self, ident: str):
        try:
            prefix, ident = ident.split(":", 1)
        except Exception:
            raise ValueError(f"Invalid prefix:ident value for package: {ident}")

        if prefix == "zim":
            return self.add_zim(ident)
        if prefix == "app":
            return self.add_app(ident)
        if prefix == "file":
            return self.add_files_package(ident)

        raise ValueError(f"Invalid package prefix: {prefix}")

    def set_output_size(self, size: int):
        self.config["output"]["size"] = size

    def add_dashboard(self):
        if self.with_dashboard:
            return

        self.with_dashboard = True

        image = OCIImage(
            name="ghcr.io/offspot/dashboard:1.0",
            filesize=119941120,
            fullsize=119838811,
        )
        self.config["oci_images"].append(image)

        # add to compose
        self.compose["services"]["dashboard"] = {
            "image": image.source,
            "container_name": "dashboard",
            "pull_policy": "never",
            "restart": "unless-stopped",
            "expose": ["80"],
            "volumes": [
                {
                    "type": "bind",
                    "source": "/data/contents/dashboard.yaml",
                    "target": "/src/home.yaml",
                    "read_only": True,
                }
            ],
        }

    def add_reverseproxy(self):
        if self.with_reverseproxy:
            return

        self.with_reverseproxy = True

        image = OCIImage(
            name="ghcr.io/offspot/reverse-proxy:1.0",
            filesize=114974720,
            fullsize=114894424,
        )
        self.config["oci_images"].append(image)

        # add to compose
        self.compose["services"]["reverse-proxy"] = {
            "image": image.source,
            "container_name": "reverse-proxy",
            "network_mode": "host",
            "cap_add": [
                "NET_ADMIN",
            ],
            "environment": {
                "FQDN": "generic.offspot",
                "SERVICES": "kiwix,edupi",
            },
            "pull_policy": "never",
            "restart": "unless-stopped",
            "ports": ["80:80", "443:443"],
        }

    def add_captive_portal(self):
        if self.with_captive_portal:
            return

        self.with_captive_portal = True

        image = OCIImage(
            name="ghcr.io/offspot/captive-portal:1.0",
            filesize=187668480,
            fullsize=187604243,
        )
        self.config["oci_images"].append(image)

        # add to compose
        self.compose["services"]["captive-portal"] = {
            "image": image.source,
            "container_name": "captive-portal",
            "network_mode": "host",
            "cap_add": [
                "NET_ADMIN",
            ],
            "environment": {
                "HOTSPOT_NAME": "My hotspot",
                "HOTSPOT_IP": "192.168.2.1",
                "HOTSPOT_FQDN": "demo.offspot",
                "CAPTURED_NETWORKS": "192.168.2.128/25",
                "TIMEOUT": "60",
                "FILTER_MODULE": "portal_filter",
            },
            "pull_policy": "never",
            "restart": "unless-stopped",
            "expose": ["2080", "2443"],
            "volumes": [
                {
                    "type": "bind",
                    "source": "/var/run/internet",
                    "target": "/var/run/internet",
                    "read_only": True,
                }
            ],
        }

    def add_hwclock(self):
        if self.with_hwclock:
            return

        self.with_hwclock = True

        # add image
        image = OCIImage(
            name="ghcr.io/offspot/hwclock:1.0",
            filesize=59412480,
            fullsize=59382985,
        )
        self.config["oci_images"].append(image)

        # add to compose
        self.compose["services"]["hwclock"] = {
            "image": image.source,
            "container_name": "hwclock",
            "pull_policy": "never",
            "read_only": True,
            "restart": "unless-stopped",
            "expose": ["80"],
            "cap-add": ["CAP_SYS_TIME"],
            "privileged": True,
        }

    def add_zim(self, zim: ZimPackage):
        if zim not in self.dashboard_entries:
            self.dashboard_entries.append(zim)

        if self.with_kiwixserve:
            return

        self.with_kiwixserve = True

        image = OCIImage(
            name="ghcr.io/offspot/kiwix-serve:3.4.0",
            filesize=29194240,
            fullsize=29162475,
        )
        self.config["oci_images"].append(image)

        # add to compose
        self.compose["services"]["kiwix-serve"] = {
            "image": image.source,
            "container_name": "kiwix-serve",
            "pull_policy": "never",
            "restart": "unless-stopped",
            "expose": ["80"],
            "volumes": [
                {
                    "type": "bind",
                    "source": "/data/contents/zims",
                    "target": "/data",
                    "read_only": True,
                }
            ],
            "command": '/bin/sh -c "kiwix-serve --blockexternal '
            '--port 80 --nodatealiases /data/*.zim"',
        }

    def add_app(self, app_id: str):
        if app_id in self.compose["services"]:
            return

        package = OFFSPOT_CATALOG[app_id]
        if package.kind != "app":
            raise ValueError(f"Package {app_id} is not an app")

        self.config["oci_images"].append(package.image)
        self.compose["services"][app_id] = {
            "image": package.oci_image.source,
            "container_name": "app_id",
            "pull_policy": "never",
            "restart": "unless-stopped",
            "expose": ["80"],
        }

    def add_files_package(self, package: Package):
        # add to files so it gets downloaded
        if package not in self.config["files"]:
            self.config["files"].append(package)

        # add image to compose
        if not self.with_files:
            image = OCIImage(
                name="ghcr.io/offspot/file-browser:1.0",
                filesize=47226880,
                fullsize=47162907,
            )

            # add to compose
            self.config["oci_images"].append(image)
            self.compose["services"]["files"] = {
                "image": image.source,
                "container_name": "files",
                "pull_policy": "never",
                "restart": "unless-stopped",
                "expose": ["80"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/data/contents/files",
                        "target": "/data",
                        "read_only": True,
                    }
                ],
            }

            self.with_files = True

        # add to package_entries to it gets its endpoint in reverse proxy
        if package not in self.file_entries:
            self.file_entries.append(package)

    def add_file(url: str, to: str, via: str):
        self.config["files"].append({"url": url, "to": to, "via": via})

    def render(self) -> dict[str, Any]:
        """compute config based on requests"""
        ...

        # add kiwix apps

        # render compose

        # compute output size
        self.config["output"] = get_size_for(self.config)


if __name__ == "__main__":
    cb = ConfigBuilder(
        BaseImage(
            source="https://drive.offspot.it/base/offspot-base-arm64-1.0.1.img.xz",
            root_size=2449473536,
        )
    )
    cb.add_file()
    cb.add_dashboard()
    cb.add_hwclock()
    cb.add_captive_portal()
    cb.add_reverseproxy()
    cb.add_zim(get_package("kiwix:wikipedia_fr_test:"))
    cb.add_zim(get_package("kiwix:wikipedia_en_all:maxi"))
    cb.add_app("wikifundi-fr.offspot.kiwix.org")
    cb.add_files_package("nomad.offspot.kiwix.org")
    import pprint

    print(dump(cb.config, Dumper=Dumper, explicit_start=True, sort_keys=False))
