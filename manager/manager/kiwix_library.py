#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import collections
import datetime
import logging
import os
import re
from collections.abc import Generator
from dataclasses import dataclass, field

import langcodes
import requests
import xmltodict

CATALOG_URL = os.getenv("CATALOG_URL", "https://library.kiwix.org")
UPDATE_EVERY_SECONDS: int = int(os.getenv("UPDATE_EVERY_SECONDS", "7200"))

logger = logging.getLogger(__name__)


def to_human_id(name: str, publisher: str | None = "", flavour: str | None = "") -> str:
    """periodless exchange identifier for ZIM Title"""
    publisher = publisher or "openZIM"
    flavour = flavour or ""
    return f"{publisher}:{name}:{flavour}"


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
    illustration_relpath: str
    version: str

    def __post_init__(self):
        for lang in self.langs_iso639_3:
            value: str = lang
            try:
                value = str(langcodes.Language.get(lang).language)
            except NameError:
                ...
            self.langs_iso639_1.append(value)

    @property
    def illustration_url(self) -> str:
        return f"{CATALOG_URL}{self.illustration_relpath}"

    @property
    def lang_codes(self) -> list[str]:
        return [
            self.langs_iso639_1[index] or iso3
            for index, iso3 in enumerate(self.langs_iso639_3)
        ]

    @property
    def lang_code(self) -> str:
        try:
            return self.langs_iso639_1[0]
        except IndexError:
            return self.langs_iso639_3[0]

    @property
    def language(self) -> langcodes.Language:
        return langcodes.Language.get(self.lang_code)

    # below are ContentPackage interface
    @property
    def ext(self) -> str:
        return "zim"

    @property
    def checksum(self) -> str | None:
        return None

    @property
    def archive_size(self) -> int:
        return self.size

    @property
    def expanded_size(self) -> int:
        return self.size


class Catalog:
    def __init__(self):
        self.updated_on: datetime.datetime = datetime.datetime(1970, 1, 1)
        # list of Book by ident
        self._books: dict[str, Book] = {}
        # list of book-idents by language (ISO-639-1)
        self._by_langs: dict[str, list[str]]
        self.ensure_fresh()

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
        return collections.OrderedDict(
            sorted(
                [
                    (
                        str(langcodes.Language.get(lang).language),
                        str(langcodes.Language.get(lang).language_name()),
                    )
                    for lang in self._by_langs.keys()
                ],
                key=lambda x: x[1],
            )
        )

    def get(self, ident: str) -> Book:
        self.ensure_fresh()
        return self._books[ident]

    def get_all_ids(self) -> Generator[str, None, None]:
        self.ensure_fresh()
        yield from self._books.keys()

    def get_for_lang(self, lang_code: str) -> Generator[Book, str, None]:
        self.ensure_fresh()
        for ident in self._by_langs.get(lang_code, []):
            yield self.get(ident)

    def ensure_fresh(self):
        if self.updated_on < datetime.datetime.utcnow() - datetime.timedelta(
            seconds=UPDATE_EVERY_SECONDS
        ):
            self.refresh()

    def refresh(self):
        books: dict[str, Book] = {}
        langs: dict[str, list[str]] = {}
        try:
            resp = requests.get(
                f"{CATALOG_URL}/catalog/v2/entries", params={"count": "-1"}, timeout=30
            )
            resp.raise_for_status()
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
                books[ident] = Book(
                    ident=ident,
                    name=entry["name"],
                    title=entry["title"],
                    description=entry["summary"],
                    langs_iso639_3=entry["language"].split(",") or ["eng"],
                    tags=entry["tags"].split(";"),
                    flavour=flavour,
                    size=int(links["application/x-zim"]["@length"]),
                    url=re.sub(r".meta4$", "", links["application/x-zim"]["@href"]),
                    illustration_relpath=links.get(
                        "image/png;width=48;height=48;scale=1", {}
                    ).get("@href", ""),
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
                    key=lambda item: (item[1].language.language_name(), item[1].title),
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


catalog = Catalog()
hotspot_languages = [("en", "English"), ("fr", "Fran\xe7ais")]


# def get_packages_by_lang():
#     packages = {}
#     for package in get_catalog().values():
#         plang = langcodes.Language.get(package["language"]).language
#         if not plang:
#             continue
#         if plang not in packages.keys():
#             packages[plang] = {}
#         packages[plang][package["id"]] = package
#     return packages


# def get_packages_id():
#     return list(get_catalog().keys())


# def get_packages_langs():
#     return collections.OrderedDict(
#         sorted(
#             [
#                 (
#                     langcodes.Language.get(lang).language,
#                     langcodes.Language.get(lang).language_name(),
#                 )
#                 for lang in get_packages_by_lang()
#                 if lang
#             ],
#             key=lambda x: x[1],
#         )
#     )


# def get_package(pid):
#     """retrieve package from its ID"""
#     return get_catalog().get(pid)


# def get_package_content(package_id):
#     """content-like dict for packages (zim file or static site)"""
#     package = get_package(package_id)
#     package.update({"ext": "zip" if package.get("type") != "zim" else "zim"})
#     return {
#         "url": package["url"],
#         "name": package_id,
#         "checksum": None,
#         "archive_size": package["size"],
#         # add a 10% margin for non-zim (zip file mostly)
#         "expanded_size": package["size"] * 1.1
#         if package.get("type") != "zim"
#         else package["size"],
#     }


# def get_packages_contents(packages=None):
#     """ideacube: ZIM file or ZIP file for each package"""
#     if packages is None:
#         packages = []
#     return [get_package_content(package) for package in packages]
