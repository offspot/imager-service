#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import collections
import datetime
import logging
import os
import re
import threading
import urllib.parse
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import iso639
import requests
import xmltodict
from offspot_config.inputs.checksum import Checksum
from offspot_config.zim import ZimPackage

CATALOG_URL = os.getenv("CATALOG_URL", "https://opds.library.kiwix.org")
UPDATE_EVERY_SECONDS: int = int(os.getenv("UPDATE_EVERY_SECONDS", "3600"))
RE_ILLUS_UUID = re.compile(
    r"/catalog/v2/illustration/(?P<uuid>[a-z0-9\-]{36})/\?size=48"
)

logger = logging.getLogger(__name__)


def to_human_id(name: str, publisher: str | None = "", flavour: str | None = "") -> str:
    """periodless exchange identifier for ZIM Title"""
    publisher = publisher or "openZIM"
    flavour = flavour or ""
    return f"{publisher}:{name}:{flavour}"


def get_illustration_url(illus_uuid: str) -> str:
    return urljoin(
        catalog.final_catalog_url,
        f"/catalog/v2/illustration/{illus_uuid}/?size=48",
    )


@dataclass(kw_only=True)
class Book:
    ident: str
    name: str
    title: str
    description: str
    langs_iso639_1: list[str] = field(default_factory=list)
    langs_iso639_3: list[str]
    tags: list[str]
    flavour: str
    size: int
    url: str
    illustration_uuid: str
    version: str

    def __post_init__(self):
        for lang in list(self.langs_iso639_3):
            value: str = lang
            try:
                value = iso639.Lang(lang).pt1
            # skip language if code is invalid or deprecated
            except (
                iso639.exceptions.DeprecatedLanguageValue,
                iso639.exceptions.InvalidLanguageValue,
            ) as exc:
                logger.error(f"{self.ident}: {exc}")
                self.langs_iso639_3.remove(lang)
                continue
            self.langs_iso639_1.append(value)

        # fallback to eng if no valid code was supplied
        if not self.langs_iso639_3:
            self.langs_iso639_3.append("eng")
        if not self.langs_iso639_1:
            self.langs_iso639_1.append("en")

        # fix many incorrect flavours
        # self.flavour = re.sub(r"^_", "", self.flavour)

    @property
    def category(self) -> str:
        try:
            return next(
                tag.split(":", 1)[1]
                for tag in self.tags
                if tag.startswith("_category:")
            )
        except StopIteration:
            return ""

    @property
    def filename(self) -> str:
        return Path(urllib.parse.urlparse(self.url).path).name

    @property
    def illustration_url(self) -> str:
        return get_illustration_url(self.illustration_uuid)

    @property
    def lang_codes(self) -> list[str]:
        return self.langs_iso639_3

    @property
    def lang_code(self) -> str:
        return self.langs_iso639_3[0]

    @property
    def language(self) -> iso639.Lang:
        return iso639.Lang(self.lang_code)

    # below are ContentPackage interface
    @property
    def ext(self) -> str:
        return "zim"

    @property
    def checksum(self) -> Checksum:
        return Checksum(algo="md5", value=f"{self.url}.md5", kind="url")

    @property
    def archive_size(self) -> int:
        return self.size

    @property
    def expanded_size(self) -> int:
        return self.size

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def get_zim_package(self) -> ZimPackage:
        return ZimPackage(
            kind="zim",
            ident=self.ident,
            name=self.name,
            title=self.title,
            description=self.description,
            languages=self.langs_iso639_3,
            tags=self.tags,
            flavour=self.flavour,
            download_size=self.size,
            download_url=self.url,
            download_checksum=self.checksum,
            icon_url=self.illustration_url,
            version=self.version,
        )


class Catalog:
    final_catalog_url: str

    def __init__(self):
        self.updated_on: datetime.datetime = datetime.datetime(1970, 1, 1)
        # list of Book by ident
        self._books: dict[str, Book] = {}
        # list of book-idents by language (ISO-639-1)
        self._by_langs: dict[str, list[str]]
        self.refresh_thread: threading.Thread = threading.Thread()
        self.refresh()

    def __contains__(self, ident: str) -> bool:
        return ident in self.get_all_ids()

    @property
    def all_books(self) -> Generator[Book, None, None]:
        self.ensure_fresh()
        yield from self._books.values()

    @property
    def nb_books(self) -> int:
        self.ensure_fresh()
        return len(self._books)

    @property
    def languages(self) -> collections.OrderedDict[str, str]:
        overrides = {
            "ina": "Interlingua",
        }
        return collections.OrderedDict(
            sorted(
                [
                    (
                        lang,
                        overrides.get(lang, iso639.Lang(lang).name),
                    )
                    for lang in self._by_langs.keys()
                ],
                key=lambda x: x[1],
            )
        )

    def get(self, ident: str) -> Book:
        self.ensure_fresh()
        return self._books[ident]

    def get_or_none(self, ident: str) -> Book | None:
        self.ensure_fresh()
        return self._books.get(ident)

    def get_all_ids(self) -> Generator[str, None, None]:
        self.ensure_fresh()
        yield from self._books.keys()

    def get_for_lang(self, lang_code: str) -> Generator[Book, str, None]:
        self.ensure_fresh()
        for ident in self._by_langs.get(lang_code, []):
            yield self.get(ident)

    def ensure_fresh(self):
        # only refresh library if it reachs a configured age
        if self.updated_on < datetime.datetime.utcnow() - datetime.timedelta(
            seconds=UPDATE_EVERY_SECONDS
        ):
            # dont refresh if already refreshing
            if self.refresh_thread.is_alive():
                return
            # refresh in a dedicated thread as to no block current request
            # current request will use cached data
            self.refresh_thread = threading.Thread(target=self.refresh)
            self.refresh_thread.start()

    def refresh(self):
        logger.debug(f"refreshing catalog via {CATALOG_URL}")
        books: dict[str, Book] = {}
        langs: dict[str, list[str]] = {}
        try:
            resp = requests.get(
                f"{CATALOG_URL}/v2/entries",
                params={"count": "-1"},
                timeout=30,
                allow_redirects=True,
            )
            resp.raise_for_status()
            self.final_catalog_url = resp.url

            catalog = xmltodict.parse(resp.content)
            if "feed" not in catalog:
                raise ValueError("Malformed OPDS response")
            if not int(catalog["feed"]["totalResults"]):
                raise OSError("Catalog has no entry; probably misbehaving")
            for entry in catalog["feed"]["entry"]:
                if not entry.get("name"):
                    logger.warning(f"Skipping entry without name: {entry}")
                    continue

                links = {link["@type"]: link for link in entry["link"]}
                version = datetime.datetime.fromisoformat(
                    re.sub(r"[A-Z]$", "", entry["updated"])
                ).strftime("%Y-%m-%d")
                flavour = entry.get("flavour") or ""
                publisher = entry.get("publisher", {}).get("name") or ""
                ident = to_human_id(
                    name=entry["name"],
                    publisher=publisher,
                    flavour=flavour,
                )
                if not links.get("image/png;width=48;height=48;scale=1"):
                    logger.warning(f"Book has no illustration: {ident}")
                else:
                    illustration_relpath = links.get(
                        "image/png;width=48;height=48;scale=1", {}
                    ).get("@href", "")
                    if m := RE_ILLUS_UUID.match(illustration_relpath):
                        illustration_uuid = m.groupdict()["uuid"]
                    else:
                        raise OSError("Unexpected mismatch with illustration pattern")
                books[ident] = Book(
                    ident=ident,
                    name=entry["name"],
                    title=entry["title"],
                    description=entry["summary"],
                    langs_iso639_3=list(set(entry["language"].split(","))) or ["eng"],
                    tags=list(set(entry["tags"].split(";"))),
                    flavour=flavour,
                    size=int(links["application/x-zim"]["@length"]),
                    url=re.sub(r".meta4$", "", links["application/x-zim"]["@href"]),
                    illustration_uuid=illustration_uuid,
                    version=version,
                )
        except Exception as exc:
            logger.error(f"Unable to load catalog from OPDS: {exc}")
            # only fail refresh if we have no previous catalog to use
            if not self._books:
                raise exc
        else:
            # re-order alphabetically by language then title
            books = collections.OrderedDict(
                sorted(
                    ((ident, book) for ident, book in books.items()),
                    key=lambda item: (item[1].language.name, item[1].title),
                )
            )
            for ident in books.keys():
                for lang in books[ident].lang_codes:
                    if lang not in langs:
                        langs[lang] = []
                    langs[lang].append(ident)
            self._books = books
            self._by_langs = langs
            self.updated_on = datetime.datetime.utcnow()
            logger.debug(f"refreshed on {self.updated_on}")


catalog = Catalog()
