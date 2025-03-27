import collections
import datetime
import io
import json
import logging
import re
import uuid
import zoneinfo
from pathlib import Path
from typing import ClassVar

import babel.languages
import dateutil.parser
import phonenumbers
import PIL
import pycountry
import requests
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils.translation import (
    gettext as _,
)
from django.utils.translation import (
    gettext_lazy as _lz,
)
from offspot_config.builder import ConfigBuilder, app_catalog
from offspot_config.utils.misc import b64_decode
from offspot_config.utils.sizes import get_sd_hardware_margin_for, round_for_cluster
from offspot_runtime.checks import (
    is_valid_domain,
    is_valid_hostname,
    is_valid_ssid,
    is_valid_timezone,
    is_valid_wpa2_passphrase,
)

from manager.kiwix_library import catalog
from manager.scheduler import (
    SchedulerAPIError,
    cancel_order,
    create_order,
    get_channel_choices,
    get_order,
    get_warehouse_choices,
    get_warehouse_from,
)
from manager.utils import (
    ONE_GB,
    extract_branding,
    get_if_str,
    get_if_str_in,
    get_list_if_values_match,
    get_nested_key,
    get_uuid,
    human_readable_size,
    is_valid_admin_login,
    is_valid_admin_pwd,
    is_valid_language,
    retrieve_branding_file,
)

logger = logging.getLogger(__name__)

KH_TIMEZONES = [
    "Africa/Abidjan",
    "Africa/Accra",
    "Africa/Addis_Ababa",
    "Africa/Algiers",
    "Africa/Asmara",
    "Africa/Bamako",
    "Africa/Bangui",
    "Africa/Banjul",
    "Africa/Bissau",
    "Africa/Blantyre",
    "Africa/Brazzaville",
    "Africa/Bujumbura",
    "Africa/Cairo",
    "Africa/Casablanca",
    "Africa/Ceuta",
    "Africa/Conakry",
    "Africa/Dakar",
    "Africa/Dar_es_Salaam",
    "Africa/Djibouti",
    "Africa/Douala",
    "Africa/El_Aaiun",
    "Africa/Freetown",
    "Africa/Gaborone",
    "Africa/Harare",
    "Africa/Johannesburg",
    "Africa/Juba",
    "Africa/Kampala",
    "Africa/Khartoum",
    "Africa/Kigali",
    "Africa/Kinshasa",
    "Africa/Lagos",
    "Africa/Libreville",
    "Africa/Lome",
    "Africa/Luanda",
    "Africa/Lubumbashi",
    "Africa/Lusaka",
    "Africa/Malabo",
    "Africa/Maputo",
    "Africa/Maseru",
    "Africa/Mbabane",
    "Africa/Mogadishu",
    "Africa/Monrovia",
    "Africa/Nairobi",
    "Africa/Ndjamena",
    "Africa/Niamey",
    "Africa/Nouakchott",
    "Africa/Ouagadougou",
    "Africa/Porto-Novo",
    "Africa/Sao_Tome",
    "Africa/Tripoli",
    "Africa/Tunis",
    "Africa/Windhoek",
    "America/Adak",
    "America/Anchorage",
    "America/Anguilla",
    "America/Antigua",
    "America/Araguaina",
    "America/Argentina/Buenos_Aires",
    "America/Argentina/Catamarca",
    "America/Argentina/Cordoba",
    "America/Argentina/Jujuy",
    "America/Argentina/La_Rioja",
    "America/Argentina/Mendoza",
    "America/Argentina/Rio_Gallegos",
    "America/Argentina/Salta",
    "America/Argentina/San_Juan",
    "America/Argentina/San_Luis",
    "America/Argentina/Tucuman",
    "America/Argentina/Ushuaia",
    "America/Aruba",
    "America/Asuncion",
    "America/Atikokan",
    "America/Bahia",
    "America/Bahia_Banderas",
    "America/Barbados",
    "America/Belem",
    "America/Belize",
    "America/Blanc-Sablon",
    "America/Boa_Vista",
    "America/Bogota",
    "America/Boise",
    "America/Cambridge_Bay",
    "America/Campo_Grande",
    "America/Cancun",
    "America/Caracas",
    "America/Cayenne",
    "America/Cayman",
    "America/Chicago",
    "America/Chihuahua",
    "America/Costa_Rica",
    "America/Creston",
    "America/Cuiaba",
    "America/Curacao",
    "America/Danmarkshavn",
    "America/Dawson",
    "America/Dawson_Creek",
    "America/Denver",
    "America/Detroit",
    "America/Dominica",
    "America/Edmonton",
    "America/Eirunepe",
    "America/El_Salvador",
    "America/Fort_Nelson",
    "America/Fortaleza",
    "America/Glace_Bay",
    "America/Godthab",
    "America/Goose_Bay",
    "America/Grand_Turk",
    "America/Grenada",
    "America/Guadeloupe",
    "America/Guatemala",
    "America/Guayaquil",
    "America/Guyana",
    "America/Halifax",
    "America/Havana",
    "America/Hermosillo",
    "America/Indiana/Indianapolis",
    "America/Indiana/Knox",
    "America/Indiana/Marengo",
    "America/Indiana/Petersburg",
    "America/Indiana/Tell_City",
    "America/Indiana/Vevay",
    "America/Indiana/Vincennes",
    "America/Indiana/Winamac",
    "America/Inuvik",
    "America/Iqaluit",
    "America/Jamaica",
    "America/Juneau",
    "America/Kentucky/Louisville",
    "America/Kentucky/Monticello",
    "America/Kralendijk",
    "America/La_Paz",
    "America/Lima",
    "America/Los_Angeles",
    "America/Lower_Princes",
    "America/Maceio",
    "America/Managua",
    "America/Manaus",
    "America/Marigot",
    "America/Martinique",
    "America/Matamoros",
    "America/Mazatlan",
    "America/Menominee",
    "America/Merida",
    "America/Metlakatla",
    "America/Mexico_City",
    "America/Miquelon",
    "America/Moncton",
    "America/Monterrey",
    "America/Montevideo",
    "America/Montserrat",
    "America/Nassau",
    "America/New_York",
    "America/Nipigon",
    "America/Nome",
    "America/Noronha",
    "America/North_Dakota/Beulah",
    "America/North_Dakota/Center",
    "America/North_Dakota/New_Salem",
    "America/Ojinaga",
    "America/Panama",
    "America/Pangnirtung",
    "America/Paramaribo",
    "America/Phoenix",
    "America/Port-au-Prince",
    "America/Port_of_Spain",
    "America/Porto_Velho",
    "America/Puerto_Rico",
    "America/Punta_Arenas",
    "America/Rainy_River",
    "America/Rankin_Inlet",
    "America/Recife",
    "America/Regina",
    "America/Resolute",
    "America/Rio_Branco",
    "America/Santarem",
    "America/Santiago",
    "America/Santo_Domingo",
    "America/Sao_Paulo",
    "America/Scoresbysund",
    "America/Sitka",
    "America/St_Barthelemy",
    "America/St_Johns",
    "America/St_Kitts",
    "America/St_Lucia",
    "America/St_Thomas",
    "America/St_Vincent",
    "America/Swift_Current",
    "America/Tegucigalpa",
    "America/Thule",
    "America/Thunder_Bay",
    "America/Tijuana",
    "America/Toronto",
    "America/Tortola",
    "America/Vancouver",
    "America/Whitehorse",
    "America/Winnipeg",
    "America/Yakutat",
    "America/Yellowknife",
    "Antarctica/Casey",
    "Antarctica/Davis",
    "Antarctica/DumontDUrville",
    "Antarctica/Macquarie",
    "Antarctica/Mawson",
    "Antarctica/McMurdo",
    "Antarctica/Palmer",
    "Antarctica/Rothera",
    "Antarctica/Syowa",
    "Antarctica/Troll",
    "Antarctica/Vostok",
    "Arctic/Longyearbyen",
    "Asia/Aden",
    "Asia/Almaty",
    "Asia/Amman",
    "Asia/Anadyr",
    "Asia/Aqtau",
    "Asia/Aqtobe",
    "Asia/Ashgabat",
    "Asia/Atyrau",
    "Asia/Baghdad",
    "Asia/Bahrain",
    "Asia/Baku",
    "Asia/Bangkok",
    "Asia/Barnaul",
    "Asia/Beirut",
    "Asia/Bishkek",
    "Asia/Brunei",
    "Asia/Chita",
    "Asia/Choibalsan",
    "Asia/Colombo",
    "Asia/Damascus",
    "Asia/Dhaka",
    "Asia/Dili",
    "Asia/Dubai",
    "Asia/Dushanbe",
    "Asia/Famagusta",
    "Asia/Gaza",
    "Asia/Hebron",
    "Asia/Ho_Chi_Minh",
    "Asia/Hong_Kong",
    "Asia/Hovd",
    "Asia/Irkutsk",
    "Asia/Jakarta",
    "Asia/Jayapura",
    "Asia/Jerusalem",
    "Asia/Kabul",
    "Asia/Kamchatka",
    "Asia/Karachi",
    "Asia/Kathmandu",
    "Asia/Khandyga",
    "Asia/Kolkata",
    "Asia/Krasnoyarsk",
    "Asia/Kuala_Lumpur",
    "Asia/Kuching",
    "Asia/Kuwait",
    "Asia/Macau",
    "Asia/Magadan",
    "Asia/Makassar",
    "Asia/Manila",
    "Asia/Muscat",
    "Asia/Nicosia",
    "Asia/Novokuznetsk",
    "Asia/Novosibirsk",
    "Asia/Omsk",
    "Asia/Oral",
    "Asia/Phnom_Penh",
    "Asia/Pontianak",
    "Asia/Pyongyang",
    "Asia/Qatar",
    "Asia/Qyzylorda",
    "Asia/Riyadh",
    "Asia/Sakhalin",
    "Asia/Samarkand",
    "Asia/Seoul",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Srednekolymsk",
    "Asia/Taipei",
    "Asia/Tashkent",
    "Asia/Tbilisi",
    "Asia/Tehran",
    "Asia/Thimphu",
    "Asia/Tokyo",
    "Asia/Tomsk",
    "Asia/Ulaanbaatar",
    "Asia/Urumqi",
    "Asia/Ust-Nera",
    "Asia/Vientiane",
    "Asia/Vladivostok",
    "Asia/Yakutsk",
    "Asia/Yangon",
    "Asia/Yekaterinburg",
    "Asia/Yerevan",
    "Atlantic/Azores",
    "Atlantic/Bermuda",
    "Atlantic/Canary",
    "Atlantic/Cape_Verde",
    "Atlantic/Faroe",
    "Atlantic/Madeira",
    "Atlantic/Reykjavik",
    "Atlantic/South_Georgia",
    "Atlantic/St_Helena",
    "Atlantic/Stanley",
    "Australia/Adelaide",
    "Australia/Brisbane",
    "Australia/Broken_Hill",
    "Australia/Currie",
    "Australia/Darwin",
    "Australia/Eucla",
    "Australia/Hobart",
    "Australia/Lindeman",
    "Australia/Lord_Howe",
    "Australia/Melbourne",
    "Australia/Perth",
    "Australia/Sydney",
    "Canada/Atlantic",
    "Canada/Central",
    "Canada/Eastern",
    "Canada/Mountain",
    "Canada/Newfoundland",
    "Canada/Pacific",
    "Europe/Amsterdam",
    "Europe/Andorra",
    "Europe/Astrakhan",
    "Europe/Athens",
    "Europe/Belgrade",
    "Europe/Berlin",
    "Europe/Bratislava",
    "Europe/Brussels",
    "Europe/Bucharest",
    "Europe/Budapest",
    "Europe/Busingen",
    "Europe/Chisinau",
    "Europe/Copenhagen",
    "Europe/Dublin",
    "Europe/Gibraltar",
    "Europe/Guernsey",
    "Europe/Helsinki",
    "Europe/Isle_of_Man",
    "Europe/Istanbul",
    "Europe/Jersey",
    "Europe/Kaliningrad",
    "Europe/Kiev",
    "Europe/Kirov",
    "Europe/Lisbon",
    "Europe/Ljubljana",
    "Europe/London",
    "Europe/Luxembourg",
    "Europe/Madrid",
    "Europe/Malta",
    "Europe/Mariehamn",
    "Europe/Minsk",
    "Europe/Monaco",
    "Europe/Moscow",
    "Europe/Oslo",
    "Europe/Paris",
    "Europe/Podgorica",
    "Europe/Prague",
    "Europe/Riga",
    "Europe/Rome",
    "Europe/Samara",
    "Europe/San_Marino",
    "Europe/Sarajevo",
    "Europe/Saratov",
    "Europe/Simferopol",
    "Europe/Skopje",
    "Europe/Sofia",
    "Europe/Stockholm",
    "Europe/Tallinn",
    "Europe/Tirane",
    "Europe/Ulyanovsk",
    "Europe/Uzhgorod",
    "Europe/Vaduz",
    "Europe/Vatican",
    "Europe/Vienna",
    "Europe/Vilnius",
    "Europe/Volgograd",
    "Europe/Warsaw",
    "Europe/Zagreb",
    "Europe/Zaporozhye",
    "Europe/Zurich",
    "GMT",
    "Indian/Antananarivo",
    "Indian/Chagos",
    "Indian/Christmas",
    "Indian/Cocos",
    "Indian/Comoro",
    "Indian/Kerguelen",
    "Indian/Mahe",
    "Indian/Maldives",
    "Indian/Mauritius",
    "Indian/Mayotte",
    "Indian/Reunion",
    "Pacific/Apia",
    "Pacific/Auckland",
    "Pacific/Bougainville",
    "Pacific/Chatham",
    "Pacific/Chuuk",
    "Pacific/Easter",
    "Pacific/Efate",
    "Pacific/Enderbury",
    "Pacific/Fakaofo",
    "Pacific/Fiji",
    "Pacific/Funafuti",
    "Pacific/Galapagos",
    "Pacific/Gambier",
    "Pacific/Guadalcanal",
    "Pacific/Guam",
    "Pacific/Honolulu",
    "Pacific/Kiritimati",
    "Pacific/Kosrae",
    "Pacific/Kwajalein",
    "Pacific/Majuro",
    "Pacific/Marquesas",
    "Pacific/Midway",
    "Pacific/Nauru",
    "Pacific/Niue",
    "Pacific/Norfolk",
    "Pacific/Noumea",
    "Pacific/Pago_Pago",
    "Pacific/Palau",
    "Pacific/Pitcairn",
    "Pacific/Pohnpei",
    "Pacific/Port_Moresby",
    "Pacific/Rarotonga",
    "Pacific/Saipan",
    "Pacific/Tahiti",
    "Pacific/Tarawa",
    "Pacific/Tongatapu",
    "Pacific/Wake",
    "Pacific/Wallis",
    "US/Alaska",
    "US/Arizona",
    "US/Central",
    "US/Eastern",
    "US/Hawaii",
    "US/Mountain",
    "US/Pacific",
    "UTC",
]
KH_TIMEZONES_CHOICES = [(tz, tz) for tz in KH_TIMEZONES]


def openzim_fixed_ident(ident: str) -> str:
    """ZIM ident with openZIM publisher (while ZIM transition from bad publishers)"""
    publisher, name, flavour = ident.split(":", 2)
    return f"openZIM:{name}:{flavour}"


def get_timezones_choices():
    yield from sorted([(tz, tz) for tz in zoneinfo.available_timezones()])


def get_branding_path(instance, filename):  # noqa: ARG001
    return f"{get_uuid()}_{filename}"


def save_branding_file(branding_file):
    fname = get_branding_path(1, branding_file.get("fname"))
    fpath = Path(settings.MEDIA_ROOT) / fname
    fpath.write_bytes(b64_decode(branding_file.get("data")))
    return fname


def parse_json_config(cls, config, *, dont_store_branding: bool = False):
    # only packages IDs which are in the catalogs
    zims_list = get_list_if_values_match(
        get_nested_key(config, ["content", "zims"]), list(catalog.get_all_ids())
    )
    packages_list = get_list_if_values_match(
        get_nested_key(config, ["content", "packages"]), app_catalog.keys()
    )
    beta_features = get_list_if_values_match(
        get_nested_key(config, ["beta_features"]), list(settings.BETA_FEATURES.keys())
    )

    # branding
    logo = extract_branding(config, "logo", ["image/png"])
    favicon = extract_branding(config, "favicon", ["image/x-icon", "image/png"])

    name = get_if_str(
        get_nested_key(config, "name"),
        cls._meta.get_field("name").default,
    )
    ssid = get_if_str(
        get_nested_key(config, "ssid"),
        cls._meta.get_field("ssid").default,
    )
    project_name = get_if_str(
        get_nested_key(config, "project_name"),
        cls._meta.get_field("project_name").default,
    )

    # options
    name = get_if_str(
        get_nested_key(config, "name"),
        cls._meta.get_field("name").default,
    )

    # wifi
    wifi_password = None
    # wifi (previous format)
    if "wifi" in config and isinstance(config["wifi"], dict):
        if "password" in config["wifi"].keys() and config["wifi"].get(
            "protected", True
        ):
            wifi_password = get_if_str(get_nested_key(config, ["wifi", "password"]))
    # wifi (new format)
    if "wifi_password" in config.keys():
        wifi_password = config["wifi_password"]

    def branding_arg(value):
        if not value:
            return None
        if dont_store_branding:
            # return base64 string directly
            return value.get("data")
        return save_branding_file(value)

    # rebuild clean config from data
    return {
        "name": name,
        "ssid": ssid,
        "project_name": project_name,
        "language": get_if_str_in(
            get_nested_key(config, "language"),
            dict(cls._meta.get_field("language").choices).keys(),
        ),
        "timezone": get_if_str_in(
            get_nested_key(config, "timezone"),
            dict(cls._meta.get_field("timezone").choices).keys(),
        ),
        "wifi_password": wifi_password,
        "admin_account": get_if_str(
            get_nested_key(config, ["admin_account", "login"]),
            cls._meta.get_field("admin_account").default,
        ),
        "admin_password": get_if_str(
            get_nested_key(config, ["admin_account", "password"]),
            cls._meta.get_field("admin_password").default,
        ),
        "content_zims": zims_list,
        "content_packages": packages_list,
        "content_edupi_resources": get_if_str(
            get_nested_key(config, ["content", "edupi_resources"])
        ),
        "content_metrics": bool(get_nested_key(config, ["content", "metrics"])),
        "option_kiwix_readers": bool(
            get_nested_key(config, ["options", "kiwix_readers"])
        ),
        "branding_logo": branding_arg(logo),
        "branding_favicon": branding_arg(favicon),
        "beta_features": beta_features,
    }


def validate_project_name(value):
    # must valid hostname
    test2 = is_valid_hostname(value)
    test3 = is_valid_domain(value)
    if not test2 or not test3:
        reason = test2.help_text or test3.help_text
        raise ValidationError(
            _("%(value)s is not a valid Hotspot name (%(reason)s)"),
            code="invalid_name",
            params={"value": value, "reason": reason},
        )


def validate_ssid(value):
    # must be a valid SSID and a valid hostname
    test1 = is_valid_ssid(value)
    if not test1:
        reason = test1.help_text
        raise ValidationError(
            _("%(value)s is not a valid Hotspot SSID (%(reason)s)"),
            code="invalid_ssid",
            params={"value": value, "reason": reason},
        )


def validate_language(value):
    if not is_valid_language(value):
        raise ValidationError(
            _("%(value)s is not a valid language code"),
            code="invalid_language",
            params={"value": value},
        )


def validate_timezone(value):
    if not is_valid_timezone(value):
        raise ValidationError(
            _("%(value)s is not a valid timezone"),
            code="invalid_timezone",
            params={"value": value},
        )


def validate_wifi_pwd(value):
    if not is_valid_wpa2_passphrase(value):
        raise ValidationError(
            _("%(value)s is not a valid WiFi password (8-63 chars basic latin chars)"),
            code="invalid_wpa2",
            params={"value": value},
        )


def validate_admin_login(value):
    if not is_valid_admin_login(value):
        raise ValidationError(
            _("%(value)s is not a valid Admin login (31 chars max, A-Z,a-z,0-9,-,_)"),
            code="invalid_admin_username",
            params={"value": value},
        )


def validate_admin_pwd(value):
    if not is_valid_admin_pwd(value):
        raise ValidationError(
            _(
                "%(value)s is not a valid Admin password "
                + "(31 chars max, A-Z,a-z,0-9,-,_)"
            ),
            code="invalid_admin_password",
            params={"value": value},
        )


def validate_fileresources_url(value):
    try:
        resp = requests.get(value, stream=True, timeout=5)
    except Exception as exc:
        raise ValidationError(
            _("%(value)s is not a reachable URL"),
            code="invalid_url_exc",
            params={"value": value},
        ) from exc
    if resp.status_code != 200:  # noqa: PLR2004
        raise ValidationError(
            _("%(value)s is not a working URL (HTTP %(code)s)"),
            code="invalid_url_exc",
            params={"value": value, "code": resp.status_code},
        )
    content_type = resp.headers.get("content-type", "n/a")
    if content_type != "application/zip":
        raise ValidationError(
            _("%(value)s is not a ZIP file (%(ct)s)"),
            code="invalid_url_exc",
            params={"value": value, "ct": content_type},
        )
    if not resp.headers.get("Content-Length", None):
        raise ValidationError(
            _("Size of %(value)s cannot be determinded (Content-Length)"),
            code="invalid_url_nosize",
            params={"value": value},
        )


class ConvertedImageFileField(models.ImageField):
    def __init__(self, *args, **kwargs):
        self.max_upload_size = kwargs.pop("max_upload_size", 1048576)
        self.max_disk_size = kwargs.pop("max_disk_size", 3145728)

        super().__init__(*args, **kwargs)

    def validate(self, value, model_instance):
        super().validate(value, model_instance)

        file = getattr(model_instance, self.attname)
        file_path = Path(file.path)

        # assume this is a regular save without an uploaded new content
        # if user is reuploading a file with exact same name and exact same bytes size
        # then we'd skip the update (!) but we can't know
        if (
            file_path.exists()
            and file.size < self.max_disk_size
            and file.size == value.size
            and file.name == value.name
        ):
            return

        if value.size > self.max_upload_size:
            raise ValidationError(
                _("File size is too large: %(value)s. Keep it under %(max)s"),
                code="too_big",
                params={
                    "value": human_readable_size(value.size),
                    "max": human_readable_size(self.max_upload_size),
                },
            )
        src = io.BytesIO()
        for chunk in value.chunks():
            src.write(chunk)
        dst = io.BytesIO()
        try:
            with PIL.Image.open(src) as image:
                image.save(dst, "PNG")
        except Exception as exc:
            logger.warning(f"Cant convert {value.name} to PNG: {exc}")
            raise ValidationError(
                _("File cannot be converted to PNG"), code="convert_failed"
            ) from exc
        else:
            converted_size = dst.getbuffer().nbytes
            if converted_size > self.max_disk_size:
                raise ValidationError(
                    _(
                        "File (converted to PNG) size is too large: %(value)s. "
                        + "Keep it under %(max)s"
                    ),
                    code="converted_too_big",
                    params={
                        "value": human_readable_size(converted_size),
                        "max": human_readable_size(self.max_disk_size),
                    },
                )
            value.save(name=str(Path(value.name).with_suffix(".png")), content=dst)


class JSONList(models.JSONField, list):
    """consider JSON field as a list"""

    ...


class BetaFeaturesListFormField(forms.MultipleChoiceField):
    """mutilple choice field for selecting beta_features (stored in JSONField)"""

    def __init__(self, **kwargs):
        # remove JSONField related kwargs
        kwargs.pop("encoder", None)
        kwargs.pop("decoder", None)
        super().__init__(choices=settings.BETA_FEATURES.items, **kwargs)


class BetaFeaturesListField(models.JSONField, list):

    def formfield(self, **kwargs):
        defaults = {"form_class": BetaFeaturesListFormField}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class Configuration(models.Model):
    class Meta:
        get_latest_by = "-id"
        ordering: ClassVar[list[str]] = ["-id"]
        verbose_name = _lz("configuration")
        verbose_name_plural = _lz("configurations")

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="configurations",
        verbose_name=_lz("configurations"),
    )
    updated_on = models.DateTimeField(
        auto_now=True,
        verbose_name=_lz("updated on"),
    )
    updated_by = models.ForeignKey(
        "Profile",
        on_delete=models.CASCADE,
        related_name="configurations",
        verbose_name=_lz("configurations"),
    )
    size = models.BigIntegerField(
        blank=True,
        verbose_name=_lz("Size"),
    )

    name = models.CharField(
        verbose_name=_lz("Config Name"),
        max_length=100,
        help_text=_lz("Used <strong>only within the Imager</strong>"),
    )
    project_name = models.CharField(
        max_length=32,
        default=settings.DEFAULT_DOMAIN,
        verbose_name=_lz("Domain name"),
        help_text=_lz("The landing page will be at http://name.hotspot"),
        validators=[validate_project_name],
    )
    ssid = models.CharField(
        max_length=32,
        default=settings.DEFAULT_SSID,
        verbose_name=_lz("WiFi Network name"),
        help_text=_lz("Name of network in WiFi list (SSID)"),
        validators=[validate_ssid],
    )
    language = models.CharField(
        max_length=3,
        choices=settings.OFFSPOT_LANGUAGES,
        default="en",
        verbose_name=_lz("Language"),
        help_text=_lz("Hotspot interface language"),
        validators=[validate_language],
    )
    timezone = models.CharField(
        max_length=75,
        choices=KH_TIMEZONES_CHOICES,
        default="Europe/Paris",
        verbose_name=_lz("Timezone"),
        help_text=_lz("Where the Hotspot would be deployed"),
        validators=[validate_timezone],
    )

    wifi_password = models.CharField(
        max_length=63,
        default=None,
        verbose_name=_lz("WiFi Password"),
        help_text=_lz(
            "Leave empty for Open WiFi (recommended)"
            + "<br />Latin and special characters. 8 chars min."
        ),
        null=True,
        blank=True,
        validators=[validate_wifi_pwd],
    )
    admin_account = models.CharField(
        max_length=31,
        default="admin",
        validators=[validate_admin_login],
        verbose_name=_lz("To manage Clock and EduPi"),
    )
    admin_password = models.CharField(
        max_length=31,
        default="admin-password",
        verbose_name=_lz("Admin password"),
        help_text=_lz("To manage Clock, EduPi and Wikifundi"),
        validators=[validate_admin_pwd],
    )

    branding_logo = ConvertedImageFileField(
        blank=True,
        null=True,
        upload_to=get_branding_path,
        verbose_name=_lz("Horizontal Logo (1MB max Image)"),
    )
    branding_favicon = models.ImageField(
        blank=True,
        null=True,
        upload_to=get_branding_path,
        verbose_name=_lz("Square Logo (1MB max Image)"),
    )

    content_zims = JSONList(
        blank=True,
        null=True,
        default=list,
    )

    content_packages = JSONList(
        blank=True,
        null=True,
        default=list,
    )

    content_edupi_resources = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_lz("Preload Files"),
        help_text=_lz(
            "Preload File Manager with files here by indicating the URL "
            + "of a ZIP file containing your resources"
        ),
        validators=[
            URLValidator(schemes=["http", "https"]),
            validate_fileresources_url,
        ],
    )

    content_metrics = models.BooleanField(
        default=False,
        verbose_name=_lz("Metrics Dashboard"),
        help_text=_lz("Hotspot Usage Statistics"),
    )

    option_kiwix_readers = models.BooleanField(
        default=False,
        verbose_name=_lz("Kiwix Readers"),
        help_text=_lz("Downloadable Kiwix software for all platforms"),
    )

    beta_features = BetaFeaturesListField(
        blank=True,
        null=True,
        default=list,
        help_text=_lz("List of beta features you want to test"),
    )

    @classmethod
    def create_from(cls, config, author):
        kwargs = parse_json_config(cls, config)
        if not author.can_brand:
            kwargs["project_name"] = settings.DEFAULT_DOMAIN
            kwargs["ssid"] = settings.DEFAULT_SSID
            for key in ("branding_logo", "branding_favicon"):
                if key in kwargs:
                    del kwargs[key]
        kwargs.update(
            {
                "updated_by": author,
                "organization": author.organization,
            }
        )

        try:
            return cls.objects.create(**kwargs)
        except Exception as exp:
            logger.warn(exp)

            # remove saved branding files
            for key in ("branding_logo", "branding_favicon"):
                if kwargs.get(key):
                    Path(settings.MEDIA_ROOT).joinpath(kwargs.get(key)).unlink(
                        missing_ok=True
                    )
            raise exp

    def duplicate(self, by):
        kwargs = {}
        for field in self._meta.fields:
            kwargs[field.name] = getattr(self, field.name)
        kwargs.pop("id")
        kwargs["name"] = "{} (Duplicate)".format(kwargs.get("name", ""))
        kwargs["updated_by"] = by
        new_instance = self.__class__(**kwargs)
        new_instance.save()

        return new_instance

    def size_value_changed(self):
        try:  # get_min_size initialize a builder which could fail on missing ZIM
            computed_size = self.builder.get_min_size()
            if computed_size != self.size:
                self.size = computed_size
                return True
        except Exception:
            return True
        return False

    def _cleanup_zims(self):
        # remove packages not in catalog
        def _valid_zims_only():
            for ident in self.content_zims:
                if ident in catalog.get_all_ids():
                    yield ident
                    continue
                if openzim_fixed_ident(ident) in catalog.get_all_ids():
                    yield openzim_fixed_ident(ident)

        self.content_zims = list(_valid_zims_only())

    def save(self, *args, **kwargs):
        self._cleanup_zims()
        self.size_value_changed()
        super().save(*args, **kwargs)

    def retrieve_missing_zims(self):
        """checks packages list over catalog for changes"""
        return [
            ident
            for ident in self.content_zims
            if ident not in catalog.get_all_ids()
            and openzim_fixed_ident(ident) not in catalog.get_all_ids()
        ]

    @classmethod
    def get_choices(cls, organization):
        return [
            (
                item.id,
                "{name} ({date})".format(
                    name=item.display_name, date=item.updated_on.strftime("%c")
                ),
            )
            for item in cls.objects.filter(organization=organization).order_by(
                "-updated_on"
            )
            if not item.retrieve_missing_zims()
        ]

    @classmethod
    def get_or_none(cls, aid):
        try:
            return cls.objects.get(id=aid)
        except cls.DoesNotExist:
            return None

    @property
    def wifi_protected(self):
        return bool(self.wifi_password)

    @property
    def display_name(self):
        return self.name or self.project_name

    @property
    def json(self):
        return json.dumps(self.to_dict(), indent=4)

    @property
    def min_media(self):
        return Media.get_min_for(self.size)

    def can_fit_on(self, media):
        return media.bytes >= self.size

    def compatible_medias(self):
        return Media.objects.filter(actual_size__gte=self.size)
        # return [m for m in Media.objects.all() if m.bytes >= self.size]

    @property
    def min_units(self):
        return self.min_media.units

    def all_languages(self):
        return self._meta.get_field("language").choices

    def __str__(self):
        return self.display_name

    @property
    def builder(self) -> ConfigBuilder:
        from manager.builder import prepare_builder_for

        return prepare_builder_for(self)

    def to_dict(self):
        return collections.OrderedDict(
            [
                ("id", self.id),
                ("name", self.name),
                ("ssid", self.ssid),
                ("project_name", self.project_name),
                ("language", self.language),
                ("timezone", self.timezone),
                ("wifi_password", self.wifi_password),
                (
                    "admin_account",
                    collections.OrderedDict(
                        [
                            ("login", self.admin_account),
                            ("password", self.admin_password),
                        ]
                    ),
                ),
                ("human_size", self.min_media.human if self.min_media else 0),
                ("size", self.min_media.size if self.min_media else 0),
                (
                    "content",
                    collections.OrderedDict(
                        [
                            ("zims", self.content_zims),
                            ("packages", self.content_packages),
                            ("edupi_resources", self.content_edupi_resources),
                            ("metrics", self.content_metrics),
                        ]
                    ),
                ),
                (
                    "options",
                    collections.OrderedDict(
                        [("kiwix_readers", self.option_kiwix_readers)]
                    ),
                ),
                (
                    "branding",
                    collections.OrderedDict(
                        [
                            ("logo", retrieve_branding_file(self.branding_logo)),
                            ("favicon", retrieve_branding_file(self.branding_favicon)),
                        ]
                    ),
                ),
                ("beta_features", self.current_beta_features),
            ]
        )

    def to_creator_yaml(self) -> str:
        return self.builder.render()

    @property
    def current_beta_features(self) -> list[str]:
        """list of currently valid beta features"""
        if not self.organization.beta_is_active:
            return []
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


class Organization(models.Model):
    class Meta:
        ordering: ClassVar[list[str]] = ["slug"]
        verbose_name = _lz("organization")
        verbose_name_plural = _lz("organizations")

    slug = models.SlugField(primary_key=True, verbose_name=_lz("Slug"))
    name = models.CharField(max_length=100, verbose_name=_lz("Name"))
    language = models.CharField(
        max_length=2,
        verbose_name=_lz("Language"),
        choices=settings.LANGUAGES,
        blank=True,
        null=True,
    )
    channel = models.CharField(
        max_length=50,
        choices=get_channel_choices(),
        default="kiwix",
        verbose_name=_lz("Channel"),
    )
    warehouse = models.CharField(
        max_length=50,
        choices=get_warehouse_choices(),
        default="kiwix",
        verbose_name=_lz("Warehouse"),
    )
    public_warehouse = models.CharField(
        max_length=50,
        choices=get_warehouse_choices(),
        default="download",
        verbose_name=_("Pub WH"),
    )
    email = models.EmailField(verbose_name=_lz("Email"))
    units = models.IntegerField(
        null=True, blank=True, default=0, verbose_name=_lz("Units")
    )
    beta_is_active = models.BooleanField(verbose_name="Beta is active", default=False)

    @property
    def is_obsolete(self) -> bool:
        if self.profile_set.filter(user__is_staff=True).count():
            return False

        now = datetime.datetime.now(tz=datetime.UTC)
        amonth_ago = now - datetime.timedelta(days=30)
        return self.profile_set.filter(expire_on__gte=amonth_ago).count() == 0

    @property
    def is_limited(self):
        return self.units is not None

    @classmethod
    def get_or_none(cls, slug):
        try:
            return cls.objects.get(slug=slug)
        except cls.DoesNotExist:
            return None

    @classmethod
    def create_kiwix(cls):
        if cls.objects.filter(slug="kiwix").count():
            return cls.objects.get(slug="kiwix")
        return cls.objects.create(
            slug="kiwix", name="Kiwix", email="reg@kiwix.org", units=256000
        )

    def get_warehouse_details(self, *, use_public=False):
        success, warehouse = get_warehouse_from(
            self.public_warehouse if use_public else self.warehouse
        )
        if not success:
            raise SchedulerAPIError(warehouse)
        return warehouse

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Meta:
        ordering: ClassVar[list[str]] = ["organization", "user__username"]
        verbose_name = _lz("profile")
        verbose_name_plural = _lz("profiles")

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, verbose_name=_lz("User")
    )
    language = models.CharField(
        max_length=2,
        verbose_name=_lz("Language"),
        choices=settings.LANGUAGES,
        blank=True,
        null=True,
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, verbose_name=_lz("Organization")
    )
    can_order_physical = models.BooleanField(
        default=False, verbose_name=_lz("Can order physical?")
    )
    expire_on = models.DateTimeField(
        blank=True, null=True, verbose_name=_lz("Expire on")
    )

    @property
    def is_obsolete(self) -> bool:
        return self.organization.is_obsolete

    @property
    def is_limited(self):
        if self.user.is_staff:
            return False
        return self.organization.is_limited

    @property
    def username(self):
        return self.user.username

    @property
    def email(self):
        return self.user.email

    @classmethod
    def get_or_none(cls, username):
        try:
            return cls.objects.get(user__username=username)
        except (cls.DoesNotExist, User.DoesNotExist):
            return None

    @classmethod
    def get_using(cls, email):
        return cls.objects.get(user__email=email)

    @property
    def can_brand(self):
        return self.user.is_staff or self.organization.slug in settings.BRANDING_ORGS

    @property
    def cannot_brand(self):
        """useful in templates inline vars"""
        return not self.can_brand

    @classmethod
    def create_admin(cls):
        organization = Organization.create_kiwix()

        if User.objects.filter(username="admin").count():
            user = User.objects.get(username="admin")
        else:
            user = User.objects.create_superuser(
                username="admin",
                first_name="John",
                last_name="Doe",
                email=organization.email,
                password=settings.ADMIN_PASSWORD,
            )
        if cls.objects.filter(user=user).count():
            return cls.objects.get(user=user)

        return cls.objects.create(
            user=user, organization=organization, can_order_physical=True
        )

    @classmethod
    def exists(cls, username):
        return bool(User.objects.filter(username=username).count())

    @classmethod
    def taken(cls, email):
        return bool(User.objects.filter(email=email).count())

    @classmethod
    def create(
        cls,
        organization,
        first_name,
        email,
        username,
        password,
        is_admin,
        expiry,
        can_order_physical,
    ):
        if cls.exists(username) or cls.taken(email):
            raise ValueError(_("Profile parameters non unique"))

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            is_staff=is_admin,
            is_superuser=is_admin,
        )

        try:
            if expiry and not expiry.tzinfo:
                expiry = expiry.astimezone(datetime.UTC)
            return cls.objects.create(
                user=user,
                organization=organization,
                can_order_physical=is_admin or can_order_physical,
                expire_on=expiry,
            )
        except Exception as exp:
            logger.error(exp)
            # make sure we remove the User object so it can be recreated later
            user.delete()
            raise exp

    @property
    def name(self):
        return self.user.get_full_name()

    def get_language(self, request_lang=None):
        if self.language:
            return self.language

        if self.organization.language:
            return self.organization.language

        if request_lang:
            request_lang = request_lang.split("-")[0]
            if request_lang in [code for code, name in settings.LANGUAGES]:
                return request_lang

        return settings.LANGUAGE_CODE

    def __str__(self):
        return f"{self.name} ({self.organization!s})"


class Address(models.Model):
    class Meta:
        ordering: ClassVar[list[str]] = ["-id"]
        verbose_name = _lz("address")
        verbose_name_plural = _lz("addresss")

    COUNTRIES = collections.OrderedDict(  # noqa: RUF012
        sorted([(c.alpha_2, c.name) for c in pycountry.countries], key=lambda x: x[1])
    )

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, verbose_name=_lz("Organization")
    )
    created_by = models.ForeignKey(
        "Profile",
        on_delete=models.CASCADE,
        related_name="created_addresses",
        verbose_name=_lz("Created addrresses"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_lz("Address Name"),
        help_text=_lz("Used only within the Imager"),
    )
    recipient = models.CharField(max_length=100, verbose_name=_lz("Recipient Name"))
    email = models.EmailField(max_length=255, verbose_name=_lz("Email"))
    phone = models.CharField(
        null=True,
        blank=True,
        max_length=30,
        help_text=_lz("In international “+” format"),
        verbose_name=_lz("Phone"),
    )
    address = models.TextField(
        null=True,
        blank=True,
        help_text=_lz("Complete address without name and country"),
        verbose_name=_lz("Address"),
    )
    country = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=COUNTRIES.items(),
        verbose_name=_lz("Country"),
    )

    @classmethod
    def get_or_none(cls, aid):
        try:
            return cls.objects.get(id=aid)
        except cls.DoesNotExist:
            return None

    def save(self, *args, **kwargs):
        self.phone = self.cleaned_phone(self.phone) if self.phone is not None else None
        super().save(*args, **kwargs)

    @classmethod
    def get_choices(cls, organization):
        return [
            (item.id, item.name)
            for item in cls.objects.filter(organization=organization)
        ]

    @staticmethod
    def country_name_for(country_code):
        return Address.COUNTRIES.get(country_code)

    @property
    def physical_compatible(self):
        return (
            self.phone is not None
            and self.address is not None
            and self.country is not None
        )

    @property
    def verbose_country(self):
        return self.country_name_for(self.country)

    @property
    def language(self):
        langs = babel.languages.get_official_languages(
            self.country.upper() if self.country else None
        )
        avail_langs = [code for code, name in settings.LANGUAGES]
        for lang in langs:
            if lang in avail_langs:
                return lang
        return settings.LANGUAGE_CODE

    @property
    def human_phone(self):
        if self.phone is None:
            return None
        return phonenumbers.format_number(
            phonenumbers.parse(self.phone, None),
            phonenumbers.PhoneNumberFormat.INTERNATIONAL,
        )

    @staticmethod
    def cleaned_phone(number):
        pn = phonenumbers.parse(number, None)
        if not phonenumbers.is_possible_number(pn):
            raise ValueError("Phone Number not possible")
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)

    def to_payload(self):
        return {
            "name": self.recipient,
            "email": self.email,
            "phone": self.human_phone,
            "address": self.address,
            "country": self.country,
            "shipment": None,
        }

    def __str__(self):
        return self.name


class Media(models.Model):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"
    KINDS = {PHYSICAL: "Physical", VIRTUAL: "Virtual"}  # noqa: RUF012
    EXPIRATION_DELAY = 14

    class Meta:
        unique_together = (("kind", "size"),)
        ordering: ClassVar[list[str]] = ["size"]
        verbose_name = _lz("media")
        verbose_name_plural = _lz("medias")

    name = models.CharField(max_length=50, verbose_name=_lz("Name"))
    kind = models.CharField(
        max_length=50, choices=KINDS.items(), verbose_name=_lz("Kind")
    )
    size = models.BigIntegerField(help_text=_lz("In GB"), verbose_name=_lz("Size"))
    actual_size = models.BigIntegerField(
        help_text=_lz("In bytes (auto calc)"),
        blank=True,
        verbose_name=_lz("Actual size"),
    )
    units_coef = models.FloatField(
        verbose_name=_lz("Units"), help_text=_lz("How much units per GB")
    )

    def save(self, *args, **kwargs):
        self.actual_size = self.get_bytes()
        return super().save(*args, **kwargs)

    @staticmethod
    def choices_for(items, *, display_units=True):
        return [
            (item.id, f"{item.name} ({item.units}U)" if display_units else item.name)
            for item in items
        ]

    @classmethod
    def get_or_none(cls, mid):
        try:
            return cls.objects.get(id=mid)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_choices(cls, *, kind=None, display_units=True):
        qs = cls.objects.all()
        if kind is not None:
            qs = qs.filter(kind=kind)
        return cls.choices_for(qs, display_units=display_units)

    @classmethod
    def get_min_for(cls, size):
        matching = [
            media
            for media in cls.objects.filter(kind=cls.VIRTUAL)  # assume virtual
            if media.bytes >= size
        ]
        return matching[0] if len(matching) else None

    def __str__(self):
        return self.name

    @property
    def bytes(self):
        return self.actual_size or self.get_bytes()

    def get_bytes(self):
        # reduced bytes size as the HW might not support advertised size
        size = self.size - get_sd_hardware_margin_for(self.size)
        return round_for_cluster(size * ONE_GB)

    @property
    def human(self):
        return human_readable_size(self.size * ONE_GB, binary=False)

    @property
    def units(self):
        return self.size * self.units_coef

    @property
    def verbose_kind(self):
        return self.KINDS.get(self.kind)

    def get_duration_for(self, quantity=1):
        return self.EXPIRATION_DELAY * quantity


class OrderData(dict):
    @property
    def id(self):
        return self.get("_id")

    @property
    def config_name(self):
        return self.get("config", {}).get("name")

    @property
    def verbose_country(self):
        return Address.country_name_for(self.get("recipient", {}).get("country"))

    @property
    def status(self):
        try:
            return self.clean_statuses()[0].get("status")
        except IndexError:
            return None

    @property
    def verbose_status(self):
        return Order.STATUSES.get(self.status)

    def clean_statuses(self):
        return sorted(
            [
                {
                    "status": item.get("status"),
                    "on": dateutil.parser.parse(item.get("on")),
                    "payload": item.get("payload"),
                }
                for item in self.get("statuses", [])
            ],
            key=lambda x: x["on"],
            reverse=True,
        )

    def pretty_config(self):
        config = self.get("config", {})
        for key in ("logo", "favicon", "css"):
            try:
                del config["branding"][key]["data"]
            except (TypeError, KeyError):
                pass

        return json.dumps(config, indent=4)

    @property
    def can_recreate(self):
        """whether to allow recreating an order

        Failed and Canceled are OK
        Completed are OK
        In Progress only if pending_expiry (work completed)"""
        statuses = self.get("statuses", [])
        status = Order.status_from_statuses(statuses)
        if status == Order.IN_PROGRESS:
            return statuses[-1]["status"] == "pending_expiry"
        return status in (
            Order.CANCELED,
            Order.FAILED,
            Order.COMPLETED,
        )


class Order(models.Model):
    NOT_CREATED = "not-created"
    IN_PROGRESS = "in-progress"
    FAILED = "failed"
    CANCELED = "canceled"
    COMPLETED = "completed"
    STATUSES = {  # noqa: RUF012
        IN_PROGRESS: "In Progress",
        COMPLETED: "Completed",
        FAILED: "Failed",
        CANCELED: "Canceled",
        NOT_CREATED: "Not accepted by Scheduler",
    }

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_on"]
        verbose_name = _lz("order")
        verbose_name_plural = _lz("orders")

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, verbose_name=_lz("Organization")
    )
    created_on = models.DateTimeField(auto_now_add=True, verbose_name=_lz("Created on"))
    created_by = models.ForeignKey(
        Profile, on_delete=models.SET_NULL, null=True, verbose_name=_lz("Created by")
    )

    scheduler_id = models.CharField(
        max_length=50, unique=True, blank=True, verbose_name=_lz("Scheduler ID")
    )
    scheduler_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_lz("Scheduler Data"),
    )
    scheduler_data_on = models.DateTimeField(
        null=True, blank=True, verbose_name=_lz("Scheduler Data On")
    )
    status = models.CharField(
        max_length=50,
        choices=STATUSES.items(),
        default=IN_PROGRESS,
        verbose_name=_lz("Status"),
    )

    # copy of request data for archive purpose
    channel = models.CharField(max_length=50, verbose_name=_lz("Channel"))
    client_name = models.CharField(max_length=100, verbose_name=_lz("Client name"))
    client_email = models.EmailField(verbose_name=_lz("Client Email"))
    client_limited = models.BooleanField(
        default=True, verbose_name=_lz("Client is limited")
    )
    client_language = models.CharField(
        max_length=2,
        verbose_name=_lz("Client language"),
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    config = models.JSONField(
        verbose_name=_lz("Config"),
    )
    config_yaml = models.TextField(verbose_name=_lz("YAML Config"), default="")
    media_name = models.CharField(max_length=50, verbose_name=_lz("Media name"))
    media_type = models.CharField(max_length=50, verbose_name=_lz("Media type"))
    media_duration = models.IntegerField(
        blank=True, null=True, verbose_name=_lz("Media duration")
    )
    media_size = models.BigIntegerField(verbose_name=_lz("Media size"))
    quantity = models.IntegerField(verbose_name=_lz("Quantity"))
    units = models.IntegerField(verbose_name=_lz("Units"))
    recipient_name = models.CharField(
        max_length=100, verbose_name=_lz("Recipient name")
    )
    recipient_email = models.EmailField(verbose_name=_lz("Recipient Email"))
    recipient_language = models.CharField(
        max_length=2,
        verbose_name=_lz("Recipient language"),
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    recipient_phone = models.CharField(
        max_length=50, blank=True, null=True, verbose_name=_lz("Recipient phone")
    )
    recipient_address = models.TextField(verbose_name=_lz("Recipient Address"))
    recipient_country_code = models.CharField(
        max_length=3, verbose_name=_lz("Recipient Country Code")
    )
    warehouse_upload_uri = models.CharField(
        max_length=255, verbose_name=_lz("Warehouse Upload URI")
    )
    warehouse_download_uri = models.CharField(
        max_length=255, verbose_name=_lz("Warehouse Download URI")
    )

    @classmethod
    def fetch_and_get(cls, order_id):
        order = cls.objects.get(id=order_id)
        # fetch current version of scheduler data
        retrieved, scheduler_data = get_order(order.scheduler_id)
        if retrieved:
            order.retrieved = True
            order.scheduler_data = scheduler_data
            order.scheduler_data_on = datetime.datetime.now(tz=datetime.UTC)
            # update status fron scheduler data
            order.status = Order.status_from_statuses(scheduler_data.get("statuses"))
            order.save()
        else:
            order.retrieved = False
        return order

    @staticmethod
    def status_from_statuses(statuses):
        if not isinstance(statuses, list) or not statuses:
            return Order.FAILED

        status = statuses[-1].get("status")
        if "failed" in status:
            return Order.FAILED
        if status in ("canceled", "timedout"):
            return Order.FAILED
        if status in ("shipped", "pending_expiry"):
            return Order.COMPLETED

        return Order.IN_PROGRESS

    @classmethod
    def get_or_none(cls, min_id):
        try:
            local_id = re.match(r"^L([0-9]+)R", min_id).groups()[0]
        except (KeyError, AttributeError):
            return None
        except cls.DoesNotExist:
            return None
        else:
            return cls.fetch_and_get(local_id)

    @classmethod
    def get_by_scheduler_id(cls, scheduler_id):
        try:
            return cls.objects.get(scheduler_id=scheduler_id)
        except cls.DoesNotExist:
            return None

    @classmethod
    def _submit_provisionned_order(cls, order, *, skip_units=False):
        if not skip_units:
            if (
                order.created_by.is_limited
                and order.units > order.created_by.organization.units
            ):
                raise ValueError(
                    _("Order requires %(req_u)dU but %(org)s has only %(avail_u)d")
                    % {
                        "req_u": order.units,
                        "org": order.created_by.organization,
                        "avail_u": order.created_by.organization.units,
                    }
                )
            if order.created_by.is_limited:
                # remove units from org
                order.created_by.organization.units -= order.units
                order.created_by.organization.save()

        payload = order.to_payload()
        created, scheduler_id = create_order(payload)
        if not created:
            logger.error(scheduler_id)
            # restore units on org
            if not skip_units and order.created_by.is_limited:
                order.created_by.organization.units += order.units
                order.created_by.organization.save()
            raise SchedulerAPIError(scheduler_id)
        order.scheduler_id = scheduler_id
        order.save()
        return order

    @classmethod
    def create_from(
        cls, client, config, media, quantity, address=None, request_lang=None
    ):
        if not address and media.kind != Media.VIRTUAL:
            raise ValueError(_("Non-virtual order requires an address"))
        country_code = (address.country if address is not None else None) or ""
        client_language = client.get_language(request_lang)
        warehouse = client.organization.get_warehouse_details(
            use_public=media.kind == Media.VIRTUAL
        )
        order = cls(
            organization=client.organization,
            created_by=client,
            channel=client.organization.channel,
            client_name=client.name,
            client_email=client.email,
            client_language=client_language,
            client_limited=client.is_limited,
            config=config.json,
            config_yaml=config.builder.render(),
            media_name=media.name,
            media_type=media.kind,
            media_size=media.size,
            media_duration=media.get_duration_for(quantity),
            quantity=quantity,
            units=media.units * quantity,
            recipient_name=address.recipient if address else client.name,
            recipient_email=address.email if address else client.email,
            recipient_language=address.language if address else client_language,
            recipient_phone=address.phone if address else "",
            recipient_address=address.address if address else "",
            recipient_country_code=country_code,
            warehouse_upload_uri=warehouse["upload_uri"],
            warehouse_download_uri=warehouse["download_uri"],
        )

        return Order._submit_provisionned_order(order)

    @classmethod
    def profile_has_active(cls, client):
        for order in cls.objects.filter(created_by=client, status=cls.IN_PROGRESS):
            order_ = cls.fetch_and_get(order.id)
            if order_.status == cls.IN_PROGRESS:
                return order_.min_id
        return False

    def recreate(self):
        order = Order.fetch_and_get(self.id)
        if not order.data.can_recreate:
            raise ValueError(_("Unable to recreate order (cancel first?)."))

        order.id = None
        order.scheduler_id = None
        order.scheduler_data = None
        order.created_on = None
        order.scheduler_data_on = None
        order.status = self.IN_PROGRESS

        return Order._submit_provisionned_order(
            order, skip_units=order.status in (self.COMPLETED, self.IN_PROGRESS)
        )

    @property
    def data(self):
        return OrderData(self.scheduler_data or self.to_payload())

    @property
    def active(self):
        return self.status == self.IN_PROGRESS

    @property
    def min_id(self):
        return f"L{self.id}R{self.scheduler_id[:4]}".upper()

    @property
    def short_id(self):
        return self.scheduler_id[:8] + self.scheduler_id[-3:]

    @property
    def config_json(self):
        return json.loads(self.config)

    @property
    def verbose_status(self):
        return self.STATUSES.get(self.status)

    def __str__(self):
        return f"Order #{self.id}/{self.scheduler_id}"

    def to_payload(self):
        return {
            "config": self.config_json,
            "config_yaml": self.config_yaml,
            "sd_card": {
                "name": self.media_name,
                "size": self.media_size,
                "type": self.media_type,
                "duration": self.media_duration,
            },
            "quantity": self.quantity,
            "units": self.units,
            "client": {
                "name": self.client_name,
                "email": self.client_email,
                "limited": self.client_limited,
                "language": self.client_language,
            },
            "recipient": {
                "name": self.recipient_name,
                "email": self.recipient_email,
                "language": self.recipient_language,
                "phone": self.recipient_phone,
                "address": self.recipient_address,
                "country": self.recipient_country_code,
                "shipment": None,
            },
            "channel": self.channel,
            "warehouse": {
                "upload_uri": self.warehouse_upload_uri,
                "download_uri": self.warehouse_download_uri,
            },
        }

    def cancel(self):
        """manually cancel an order"""
        canceled, resp = cancel_order(self.scheduler_id)
        if canceled:
            self.status = self.CANCELED
            self.save()
        else:
            logger.error(resp)
        return canceled

    def anonymize(self):
        redacted = "[ANONYMIZED]"
        self.scheduler_data = {}
        self.scheduler_data_on = datetime.datetime.now(tz=datetime.UTC)
        self.client_name = redacted
        self.client_email = "anonymized.tld"
        self.recipient_name = redacted
        self.recipient_email = self.client_email
        self.recipient_phone = redacted
        self.recipient_address = redacted
        self.save()


class PasswordResetCode(models.Model):
    code = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        "Profile", on_delete=models.CASCADE, related_name="passwordresets"
    )
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.profile} -- {self.code}"

    @classmethod
    def get_or_none(cls, code):
        try:
            return cls.objects.get(code=code)
        except cls.DoesNotExist:
            return None
