import json
from collections.abc import Iterable
from pathlib import Path

import dateutil.parser
from django import template
from offspot_config.catalog import app_catalog
from offspot_config.packages import AppPackage, FilesPackage, Package

from manager.kiwix_library import Book, catalog, get_illustration_url
from manager.models import Address, Configuration, Order, openzim_fixed_ident
from manager.utils import human_readable_size

register = template.Library()


class AppCatalogEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Package):
            return {
                "ident": obj.ident,
                "kind": obj.kind,
                "title": obj.title,
                "description": obj.description,
                "languages": obj.languages,
                "tags": obj.tags,
                "icon_url": obj.icon_url or "",
                "size": obj.size or 0,
            }
        return json.JSONEncoder.default(self, obj)


def human_size(value, binary: bool = True):  # noqa: FBT001 FBT002
    return human_readable_size(value, binary=binary).replace(" ", " ")  # noqa: RUF001


register.filter("human_size", human_size)


def raw_number(value):
    return str(value)


register.filter("raw_number", raw_number)


def fname(value):
    return Path(value).name.split("_")[-1]


register.filter("fname", fname)


def books_from_json(db_value: str | list[str]) -> list[Book]:
    if db_value is None:
        db_value = []
    if isinstance(db_value, str):
        db_value = json.loads(db_value or "[]") or []
    books = [
        catalog.get_or_none(ident) or catalog.get_or_none(openzim_fixed_ident(ident))
        for ident in db_value or []
    ]
    return [book for book in books if book]


register.filter("books_from_json", books_from_json)


def apps_from_json(db_value: str | list[str]) -> list[AppPackage]:
    if db_value is None:
        db_value = []
    if isinstance(db_value, str):
        db_value = json.loads(db_value or "[]") or []

    apps = [app_catalog.get(ident, None) for ident in db_value]
    return [app for app in apps if isinstance(app, AppPackage)]


register.filter("apps_from_json", apps_from_json)


def files_from_json(db_value: str | list[str]) -> list[FilesPackage]:
    if db_value is None:
        db_value = []
    if isinstance(db_value, str):
        db_value = json.loads(db_value or "[]") or []
    files = [app_catalog.get(ident, None) for ident in db_value]
    return [file for file in files if isinstance(file, FilesPackage)]


register.filter("files_from_json", files_from_json)


def as_widget(field):
    if not hasattr(field, "as_widget"):
        return field
    our_classes = ["form-control"]
    if getattr(field, "errors", False):
        our_classes += ["alert-danger"]
    return field.as_widget(attrs={"class": field.css_classes(" ".join(our_classes))})


register.filter("as_widget", as_widget)


def country_name(country_code):
    return Address.country_name_for(country_code)


register.filter("country", country_name)


def get_id(mongo_data):
    return mongo_data.get("_id") if isinstance(mongo_data, dict) else None


register.filter("id", get_id)


def clean_statuses(items):
    if not isinstance(items, list):
        return []
    return sorted(
        [
            {
                "status": item.get("status"),
                "on": dateutil.parser.parse(item.get("on")),
                "payload": item.get("payload"),
            }
            for item in items
        ],
        key=lambda x: x["on"],
        reverse=True,
    )


register.filter("clean_statuses", clean_statuses)


def plus_one(number):
    return number + 1


register.filter("plus_one", plus_one)


def status_color(status):
    return {
        Order.COMPLETED: "message-success",
        Order.FAILED: "message-error",
        Order.NOT_CREATED: "message-error",
    }.get(status, "")


register.filter("status_color", status_color)


def clean_datetime(dt):
    return dateutil.parser.parse(dt) if dt else None


register.filter("datetime", clean_datetime)


def short_id(anid):
    if not anid:
        return None
    return anid[:8] + anid[-3:]


register.filter("short_id", short_id)


def yesno(value):
    """yes or no string from bool value"""
    return "yes" if bool(value) else "no"


register.filter("yesnoraw", yesno)


def only_apps(value: Iterable[Package]) -> Iterable[AppPackage]:
    """yes or no string from bool value"""
    for package in value:
        if isinstance(package, AppPackage):
            yield package


register.filter("only_apps", only_apps)


def only_files(value: Iterable[Package]) -> Iterable[FilesPackage]:
    """yes or no string from bool value"""
    for package in value:
        if isinstance(package, FilesPackage):
            yield package


register.filter("only_files", only_files)


def hide_internals(value: dict[str, Package]) -> dict[str, Package]:
    """yes or no string from bool value"""
    internal_idents = [
        "contentfilter.offspot.kiwix.org",
        "file-manager.offspot.kiwix.org",
    ]
    return {
        ident: package
        for ident, package in value.items()
        if ident not in internal_idents
    }


register.filter("hide_internals", hide_internals)


def to_json(value) -> str:
    return json.dumps(value, cls=AppCatalogEncoder)


register.filter("to_json", to_json)


def has_expired(errors) -> bool:
    if not errors:
        return False
    for error in errors.get("__all__", []):
        if error.code == "expired":
            return True
    return False


register.filter("has_expired", has_expired)


@register.simple_tag
def update_query_params(request, field, value):
    """Updates query parameter in the current URL without duplicating parameters."""
    query_params = request.GET.copy()
    current_sort = request.GET.get("sort")
    query_params[field] = value
    if field == "sort":
        query_params.pop("dir", None)
        if value in ["updated_on", "created_on"] and not current_sort:
            query_params["dir"] = "asc"
        elif value == current_sort:
            current_dir = request.GET.get("dir")
            query_params["dir"] = "asc" if current_dir == "desc" else "desc"
        else:
            query_params["dir"] = "desc"
    if "all" in request.GET:
        query_params["all"] = request.GET["all"]
    return query_params.urlencode()


@register.inclusion_tag("_sort_header.html")
def sort_header(request, field_name, display_name, sort_field, sort_dir):
    """Renders a sortable header with proper sort indicators"""
    return {
        "request": request,
        "field_name": field_name,
        "display_name": display_name,
        "sort_field": sort_field,
        "sort_dir": sort_dir,
        "order_filter": request.GET.get("only"),
    }


def get_config_name_from(config_id: int) -> str:
    config = Configuration.get_or_none(config_id)
    if not config:
        return "n/a"
    return config.name


register.filter("config_name", get_config_name_from)


@register.filter("illus_url")
def illustration_url_from(uuid: str):
    return get_illustration_url(uuid)
