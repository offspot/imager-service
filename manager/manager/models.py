#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import io
import json
import uuid
import logging
import collections
import zoneinfo
from pathlib import Path

import babel.languages
import pycountry
import jsonfield
import phonenumbers
import dateutil.parser
import PIL
from django import forms
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import (
    gettext as _,
    gettext_lazy as _lz,
)
from offspot_runtime.checks import (
    is_valid_timezone,
    is_valid_ssid,
    is_valid_hostname,
    is_valid_wpa2_passphrase,
    is_valid_domain,
)

from manager.scheduler import (
    create_order,
    SchedulerAPIError,
    get_order,
    get_warehouse_from,
    get_channel_choices,
    get_warehouse_choices,
    cancel_order,
)
from manager.pibox.packages import get_packages_id
from manager.pibox.data import hotspot_languages
from manager.pibox.util import (
    ONE_GB,
    b64encode,
    b64decode,
    human_readable_size,
    get_hardware_adjusted_image_size,
    is_valid_language,
    is_valid_admin_login,
    is_valid_admin_pwd,
)
from manager.pibox.config import (
    get_uuid,
    get_if_str,
    get_if_str_in,
    get_nested_key,
    extract_branding,
    get_list_if_values_match,
)
from manager.pibox.content import get_collection, get_required_image_size

logger = logging.getLogger(__name__)


def get_timezones_choices():
    for tz in sorted([(tz, tz) for tz in zoneinfo.available_timezones()]):
        yield tz


def get_branding_path(instance, filename):
    return "{uuid}_{fname}".format(uuid=get_uuid(), fname=filename)


def save_branding_file(branding_file):
    rpath = get_branding_path(1, branding_file.get("fname"))
    b64decode(rpath, branding_file.get("data"), settings.MEDIA_ROOT)
    return rpath


def retrieve_branding_file(field):
    if not field.name:
        return None
    fpath = Path(settings.MEDIA_ROOT).joinpath(field.name)
    if not fpath.exists():
        return None
    fname = Path(field.name).name.split("_")[-1]  # remove UUID
    return {"fname": fname, "data": b64encode(fpath)}


def validate_project_name(value):
    # must be a valid SSID and a valid hostname
    test1 = is_valid_ssid(value)
    test2 = is_valid_hostname(value)
    test3 = is_valid_domain(value)
    if not test1 or not test2 or not test3:
        reason = test1.help_text or test2.help_text or test3.help_text
        raise ValidationError(
            _("%(value)s is not a valid Hotspot name (%(reason)s)"),
            code="invalid_name",
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


class ConvertedImageFileField(models.ImageField):
    def __init__(self, *args, **kwargs):
        self.max_upload_size = kwargs.pop("max_upload_size", 1048576)

        super().__init__(*args, **kwargs)

    def validate(self, value, model_instance):
        super().validate(value, model_instance)

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
            logger.warning(f"cant convert {value.path} to PNG: {exc}")
            raise ValidationError(
                _("File cannot be converted to PNG"), code="convert_failed"
            )
        else:
            value.save(name=str(Path(value.name).with_suffix(".png")), content=dst)


class Configuration(models.Model):
    class Meta:
        get_latest_by = "-id"
        ordering = ["-id"]
        verbose_name = _lz("configuration")
        verbose_name_plural = _lz("configurations")

    KALITE_LANGUAGES = ["en", "fr", "es"]
    WIKIFUNDI_LANGUAGES = ["en", "fr", "es"]

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
        help_text=_lz("Used <strong>only within the Cardshop</strong>"),
    )
    project_name = models.CharField(
        max_length=32,
        default="kiwix",
        verbose_name=_lz("Hospot name"),
        help_text=_lz(
            "Network name; the landing page will also be at http://name.hotspot"
        ),
        validators=[validate_project_name],
    )
    language = models.CharField(
        max_length=3,
        choices=hotspot_languages,
        default="en",
        verbose_name=_lz("Language"),
        help_text=_lz("Hotspot interface language"),
        validators=[validate_language],
    )
    timezone = models.CharField(
        max_length=75,
        choices=get_timezones_choices(),
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
    )

    branding_logo = ConvertedImageFileField(
        blank=True,
        null=True,
        upload_to=get_branding_path,
        verbose_name=_lz("Logo (1MB max Image)"),
    )
    branding_favicon = models.ImageField(
        blank=True,
        null=True,
        upload_to=get_branding_path,
        verbose_name=_lz("Favicon (1MB max Image)"),
    )
    branding_css = models.FileField(
        blank=True,
        null=True,
        upload_to=get_branding_path,
        verbose_name=_lz("CSS File"),
    )

    content_zims = jsonfield.JSONField(
        blank=True,
        null=True,
        load_kwargs={"object_pairs_hook": collections.OrderedDict},
        default="",
    )
    content_wikifundi_fr = models.BooleanField(
        default=False,
        verbose_name=_lz("WikiFundi FR"),
        help_text=_lz("Wikipedia-like Editing Platform (French)"),
    )
    content_wikifundi_en = models.BooleanField(
        default=False,
        verbose_name=_lz("WikiFundi EN"),
        help_text=_lz("Wikipedia-like Editing Platform (English)"),
    )
    content_wikifundi_es = models.BooleanField(
        default=False,
        verbose_name=_lz("WikiFundi ES"),
        help_text=_lz("Wikipedia-like Editing Platform (Spanish)"),
    )
    content_edupi = models.BooleanField(
        default=False,
        verbose_name=_lz("EduPi"),
        help_text=_lz("Share arbitrary files with all users"),
    )
    content_edupi_resources = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_lz("EduPi Resources"),
        help_text=_lz("ZIP folder archive of documents to initialize EduPi with"),
    )
    content_nomad = models.BooleanField(
        default=False,
        verbose_name=_lz("Nomad android apps"),
        help_text=_lz("Révisions du CP à la 3è"),
    )
    content_mathews = models.BooleanField(
        default=False,
        verbose_name=_lz("Math Mathews android"),
        help_text=_lz("Un jeu pour réviser les maths"),
    )
    content_africatik = models.BooleanField(
        default=False,
        verbose_name=_lz("Africatik Écoles"),
        help_text=_lz(
            "Applications éducatives adaptées au contexte culturel africain "
            "(version Écoles numériques)"
        ),
    )
    content_africatikmd = models.BooleanField(
        default=False,
        verbose_name=_lz("Africatik Maisons digitales"),
        help_text=_lz(
            "Applications éducatives adaptées au contexte culturel africain "
            "(version Maisons digitales)"
        ),
    )

    @classmethod
    def create_from(cls, config, author):
        # only packages IDs which are in the catalogs
        packages_list = get_list_if_values_match(
            get_nested_key(config, ["content", "zims"]), get_packages_id()
        )
        # list of requested langs for wikifundi
        wikifundi_langs = get_list_if_values_match(
            get_nested_key(config, ["content", "wikifundi"]), cls.WIKIFUNDI_LANGUAGES
        )

        # branding
        logo = extract_branding(config, "logo", ["image/png"])
        favicon = extract_branding(config, "favicon", ["image/x-icon", "image/png"])
        css = extract_branding(config, "css", ["text/css", "text/plain"])

        # name is used twice
        name = get_if_str(
            get_nested_key(config, "project_name"),
            cls._meta.get_field("project_name").default,
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

        # rebuild clean config from data
        kwargs = {
            "updated_by": author,
            "organization": author.organization,
            "name": name,
            "project_name": name,
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
            "branding_logo": save_branding_file(logo) if logo is not None else None,
            "branding_favicon": save_branding_file(favicon)
            if favicon is not None
            else None,
            "branding_css": save_branding_file(css) if css is not None else None,
            "content_zims": packages_list,
            "content_wikifundi_fr": "fr" in wikifundi_langs,
            "content_wikifundi_en": "en" in wikifundi_langs,
            "content_wikifundi_es": "es" in wikifundi_langs,
            "content_edupi": bool(get_nested_key(config, ["content", "edupi"])),
            "content_edupi_resources": get_if_str(
                get_nested_key(config, ["content", "edupi_resources"])
            ),
            "content_nomad": bool(get_nested_key(config, ["content", "nomad"])),
            "content_mathews": bool(get_nested_key(config, ["content", "mathews"])),
            "content_africatik": bool(get_nested_key(config, ["content", "africatik"])),
            "content_africatikmd": bool(
                get_nested_key(config, ["content", "africatikmd"])
            ),
        }

        try:
            return cls.objects.create(**kwargs)
        except Exception as exp:
            logger.warn(exp)

            # remove saved branding files
            for key in ("branding_logo", "branding_favicon", "branding_css"):
                if kwargs.get(key):
                    try:
                        Path(settings.MEDIA_ROOT).joinpath(kwargs.get(key))
                    except FileNotFoundError:
                        pass
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
        computed_size = get_required_image_size(self.collection)
        if computed_size != self.size:
            self.size = computed_size
            return True
        return False

    def save(self, *args, **kwargs):
        # remove packages not in catalog
        self.content_zims = [
            package for package in self.content_zims if package in get_packages_id()
        ]
        self.size_value_changed()
        super().save(*args, **kwargs)

    def retrieve_missing_zims(self):
        """checks packages list over catalog for changes"""
        return [
            package for package in self.content_zims if package not in get_packages_id()
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
            for item in cls.objects.filter(organization=organization)
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

    @property
    def wikifundi_languages(self):
        return [
            lang
            for lang in self.WIKIFUNDI_LANGUAGES
            if getattr(self, "content_wikifundi_{}".format(lang), False)
        ]

    def all_languages(self):
        return self._meta.get_field("language").choices

    def __str__(self):
        return self.display_name

    @property
    def collection(self):
        return get_collection(
            edupi=self.content_edupi,
            edupi_resources=self.content_edupi_resources or None,
            nomad=self.content_nomad,
            mathews=self.content_mathews,
            africatik=self.content_africatik,
            africatikmd=self.content_africatikmd,
            packages=self.content_zims or [],
            wikifundi_languages=self.wikifundi_languages,
        )

    def to_dict(self):
        # for key in ("project_name", "language", "timezone"):
        #     config.append((key, getattr(self, key)))
        return collections.OrderedDict(
            [
                ("name", self.name),
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
                ("size", self.min_media.human),
                (
                    "content",
                    collections.OrderedDict(
                        [
                            ("zims", self.content_zims),
                            ("wikifundi", self.wikifundi_languages),
                            ("edupi", self.content_edupi),
                            ("edupi_resources", self.content_edupi_resources),
                            ("nomad", self.content_nomad),
                            ("mathews", self.content_mathews),
                            ("africatik", self.content_africatik),
                            ("africatikmd", self.content_africatikmd),
                        ]
                    ),
                ),
                (
                    "branding",
                    collections.OrderedDict(
                        [
                            ("logo", retrieve_branding_file(self.branding_logo)),
                            ("favicon", retrieve_branding_file(self.branding_favicon)),
                            ("css", retrieve_branding_file(self.branding_css)),
                        ]
                    ),
                ),
            ]
        )


class Organization(models.Model):
    class Meta:
        ordering = ["slug"]
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

    def get_warehouse_details(self, use_public=False):
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
        ordering = ["organization", "user__username"]
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
                expiry = expiry.astimezone(timezone.utc)
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
        return "{user} ({org})".format(user=self.name, org=str(self.organization))


class Address(models.Model):
    class Meta:
        ordering = ("-id",)
        verbose_name = _lz("address")
        verbose_name_plural = _lz("addresss")

    COUNTRIES = collections.OrderedDict(
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
        help_text=_lz("Used only within the Cardshop"),
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
    KINDS = {PHYSICAL: "Physical", VIRTUAL: "Virtual"}
    EXPIRATION_DELAY = 14

    class Meta:
        unique_together = (("kind", "size"),)
        ordering = ["size"]
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
        return super(Media, self).save(*args, **kwargs)

    @staticmethod
    def choices_for(items, display_units=True):
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
    def get_choices(cls, kind=None, display_units=True):
        qs = cls.objects.all()
        if kind is not None:
            qs = qs.filter(kind=kind)
        return cls.choices_for(qs, display_units=display_units)

    @classmethod
    def get_min_for(cls, size):
        matching = [media for media in cls.objects.all() if media.bytes >= size]
        return matching[0] if len(matching) else None

    def __str__(self):
        return self.name

    @property
    def bytes(self):
        return self.actual_size or self.get_bytes()

    def get_bytes(self):
        return get_hardware_adjusted_image_size(self.size * ONE_GB)

    @property
    def human(self):
        return human_readable_size(self.size * ONE_GB, False)

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
    STATUSES = {
        IN_PROGRESS: "In Progress",
        COMPLETED: "Completed",
        FAILED: "Failed",
        CANCELED: "Canceled",
        NOT_CREATED: "Not accepted by Scheduler",
    }

    class Meta:
        ordering = ["-created_on"]
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
    scheduler_data = jsonfield.JSONField(
        load_kwargs={"object_pairs_hook": collections.OrderedDict},
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
    config = jsonfield.JSONField(
        load_kwargs={"object_pairs_hook": collections.OrderedDict},
        verbose_name=_lz("Config"),
    )
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
            order.scheduler_data_on = timezone.now()
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
        except KeyError:
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
    def _submit_provisionned_order(cls, order, skip_units=False):
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
            order = cls.fetch_and_get(order.id)
            if order.status == cls.IN_PROGRESS:
                return order.min_id
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
        return "L{dj}R{sched}".format(dj=self.id, sched=self.scheduler_id[:4]).upper()

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
        return "Order #{id}/{sid}".format(id=self.id, sid=self.scheduler_id)

    def to_payload(self):
        return {
            "config": self.config_json,
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
        self.scheduler_data_on = timezone.now()
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
