#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import json
import logging
import collections
from pathlib import Path

import pytz
import pycountry
import jsonfield
import phonenumbers
import dateutil.parser
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User

from manager.scheduler import (
    create_order,
    SchedulerAPIError,
    get_order,
    get_warehouse_from,
)
from manager.pibox.packages import get_packages_id
from manager.pibox.data import ideascube_languages
from manager.pibox.util import (
    ONE_GB,
    b64encode,
    b64decode,
    human_readable_size,
    get_adjusted_image_size,
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


def get_channel_choices():
    from manager.scheduler import get_channels_list, as_items_or_none

    channels = as_items_or_none(*get_channels_list())
    if channels is None:
        return [("kiwix", "Kiwix")]
    return [
        (
            channel.get("slug"),
            "{name} ({pub})".format(
                name=channel.get("name"),
                pub="Private" if channel.get("private") else "Public",
            ),
        )
        for channel in channels
        if channel.get("active", False)
    ]


def get_warehouse_choices():
    from manager.scheduler import get_warehouses_list, as_items_or_none

    warehouses = as_items_or_none(*get_warehouses_list())
    if warehouses is None:
        return [("kiwix", "kiwix")]
    return [
        (warehouse.get("slug"), warehouse.get("slug"))
        for warehouse in warehouses
        if warehouse.get("active", False)
    ]


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


class Configuration(models.Model):
    class Meta:
        get_latest_by = "-id"
        ordering = ["-id"]

    KALITE_LANGUAGES = ["en", "fr", "es"]
    WIKIFUNDI_LANGUAGES = ["en", "fr"]

    organization = models.ForeignKey(
        "Organization", on_delete=models.CASCADE, related_name="configurations"
    )
    updated_on = models.DateTimeField(auto_now=True)

    name = models.CharField(
        max_length=100, help_text="Used <strong>only within the Cardshop</strong>"
    )
    project_name = models.CharField(
        max_length=100,
        default="Kiwix Hotspot",
        verbose_name="Hospot name",
        help_text="Used to name your Box and its WiFi network",
    )
    language = models.CharField(
        max_length=3,
        choices=ideascube_languages.items(),
        default="en",
        help_text="Hotspot interface language",
    )
    timezone = models.CharField(
        max_length=50,
        choices=[("UTC", "UTC"), ("Europe/Paris", "Europe/Paris")]
        + [(tz, tz) for tz in pytz.common_timezones],
        default="Europe/Paris",
        help_text="Where the plug would be deployed",
    )

    wifi_password = models.CharField(
        max_length=100,
        default=None,
        verbose_name="WiFi Password",
        help_text="Leave Empty for Open WiFi",
        null=True,
        blank=True,
    )
    admin_account = models.CharField(max_length=50, default="admin")
    admin_password = models.CharField(
        max_length=50,
        default="admin-password",
        help_text="To manage Ideascube, KA-Lite, Aflatoun, EduPi and Wikifundi",
    )

    branding_logo = models.FileField(
        blank=True, null=True, upload_to=get_branding_path, verbose_name="Logo"
    )
    branding_favicon = models.FileField(
        blank=True, null=True, upload_to=get_branding_path, verbose_name="Favicon"
    )
    branding_css = models.FileField(
        blank=True, null=True, upload_to=get_branding_path, verbose_name="CSS File"
    )

    content_zims = jsonfield.JSONField(
        blank=True,
        null=True,
        load_kwargs={"object_pairs_hook": collections.OrderedDict},
        default="",
    )
    content_kalite_fr = models.BooleanField(
        default=False,
        verbose_name="Khan Academy FR",
        help_text="Learning Platform (French)",
    )
    content_kalite_en = models.BooleanField(
        default=False,
        verbose_name="Khan Academy EN",
        help_text="Learning Platform (English)",
    )
    content_kalite_es = models.BooleanField(
        default=False,
        verbose_name="Khan Academy ES",
        help_text="Learning Platform (Spanish)",
    )
    content_wikifundi_fr = models.BooleanField(
        default=False,
        verbose_name="WikiFundi FR",
        help_text="Wikipedia-like Editing Platform (French)",
    )
    content_wikifundi_en = models.BooleanField(
        default=False,
        verbose_name="WikiFundi EN",
        help_text="Wikipedia-like Editing Platform (English)",
    )
    content_aflatoun = models.BooleanField(
        default=False, verbose_name="Aflatoun", help_text="Education Platform for kids"
    )
    content_edupi = models.BooleanField(
        default=False,
        verbose_name="EduPi",
        help_text="Share arbitrary files with all users",
    )
    content_edupi_resources = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="EduPi Resources",
        help_text="ZIP folder archive of documents to initialize EduPi with",
    )

    @classmethod
    def create_from(cls, config, organization):

        # only packages IDs which are in the catalogs
        packages_list = get_list_if_values_match(
            get_nested_key(config, ["content", "zims"]), get_packages_id()
        )
        # list of requested langs for kalite
        kalite_langs = get_list_if_values_match(
            get_nested_key(config, ["content", "kalite"]), cls.KALITE_LANGUAGES
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
            "organization": organization,
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
            "content_kalite_fr": "fr" in kalite_langs,
            "content_kalite_en": "en" in kalite_langs,
            "content_kalite_es": "es" in kalite_langs,
            "content_wikifundi_fr": "fr" in wikifundi_langs,
            "content_wikifundi_en": "en" in wikifundi_langs,
            "content_aflatoun": bool(get_nested_key(config, ["content", "aflatoun"])),
            "content_edupi": bool(get_nested_key(config, ["content", "edupi"])),
            "content_edupi_resources": get_if_str(
                get_nested_key(config, ["content", "edupi_resources"])
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
        ]

    @classmethod
    def get_or_none(cls, id):
        try:
            return cls.objects.get(id=id)
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
        return [m for m in Media.objects.all() if m.bytes >= self.size]

    @property
    def min_units(self):
        return self.min_media.units

    @property
    def kalite_languages(self):
        return [
            lang
            for lang in self.KALITE_LANGUAGES
            if getattr(self, "content_kalite_{}".format(lang), False)
        ]

    @property
    def wikifundi_languages(self):
        return [
            lang
            for lang in self.KALITE_LANGUAGES
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
            packages=self.content_zims or [],
            kalite_languages=self.kalite_languages,
            wikifundi_languages=self.wikifundi_languages,
            aflatoun_languages=["fr", "en"] if self.content_aflatoun else [],
        )

    @property
    def size(self):
        return get_required_image_size(self.collection)

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
                            ("kalite", self.kalite_languages),
                            ("wikifundi", self.wikifundi_languages),
                            ("aflatoun", self.content_aflatoun),
                            ("edupi", self.content_edupi),
                            ("edupi_resources", self.content_edupi_resources),
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

    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    channel = models.CharField(
        max_length=50, choices=get_channel_choices(), default="kiwix"
    )
    warehouse = models.CharField(
        max_length=50, choices=get_warehouse_choices(), default="kiwix"
    )
    email = models.EmailField()
    units = models.IntegerField()

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

    def get_warehouse_details(self):
        success, warehouse = get_warehouse_from(self.warehouse)
        if not success:
            raise SchedulerAPIError(warehouse)
        return warehouse

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Meta:
        ordering = ["organization", "user__username"]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

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
    def create_admin(cls):
        organization = Organization.create_kiwix()

        if User.objects.filter(username="admin").count():
            user = User.objects.get(username="admin")
        else:
            user = User.objects.create_superuser(
                username="admin",
                first_name="admin",
                email=organization.email,
                password=settings.ADMIN_PASSWORD,
            )
        if cls.objects.filter(user=user).count():
            return cls.objects.get(user=user)

        return cls.objects.create(user=user, organization=organization)

    @classmethod
    def exists(cls, username):
        return bool(User.objects.filter(username=username).count())

    @classmethod
    def taken(cls, email):
        return bool(User.objects.filter(email=email).count())

    @classmethod
    def create(cls, organization, first_name, email, username, password, is_admin):
        if cls.exists(username) or cls.taken(email):
            raise ValueError("Profile parameters non unique")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            is_staff=is_admin,
            is_superuser=is_admin,
        )

        try:
            return cls.objects.create(user=user, organization=organization)
        except Exception as exp:
            logger.error(exp)
            # make sure we remove the User object so it can be recreated later
            user.delete()
            raise exp

    @property
    def name(self):
        return self.user.get_full_name()

    def __str__(self):
        return "{user} ({org})".format(user=self.name, org=str(self.organization))


class Address(models.Model):

    COUNTRIES = collections.OrderedDict(
        sorted([(c.alpha_2, c.name) for c in pycountry.countries], key=lambda x: x[1])
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, verbose_name="Address Name")
    recipient = models.CharField(max_length=100)
    email = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=30)
    address = models.TextField()
    country = models.CharField(max_length=50, choices=COUNTRIES.items())

    @classmethod
    def get_or_none(cls, aid):
        try:
            return cls.objects.get(id=aid)
        except cls.DoesNotExist:
            return None

    def save(self, *args, **kwargs):
        self.phone = self.cleaned_phone(self.phone)
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
    def verbose_country(self):
        return self.country_name_for(self.country)

    @property
    def human_phone(self):
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

    REGULAR = "regular"
    KINDS = {REGULAR: "Regular"}

    class Meta:
        unique_together = (("kind", "size"),)
        ordering = ["size"]

    name = models.CharField(max_length=50)
    kind = models.CharField(max_length=50, choices=KINDS.items())
    size = models.IntegerField(help_text="In GB")
    units_coef = models.FloatField(
        verbose_name="Units", help_text="How much units per GB"
    )

    @staticmethod
    def choices_for(items):
        return [
            (item.id, "{name} ({units}U)".format(name=item.name, units=item.units))
            for item in items
        ]

    @classmethod
    def get_or_none(cls, mid):
        try:
            return cls.objects.get(id=mid)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_choices(cls):
        return cls.choices_for(cls.objects.all())

    @classmethod
    def get_min_for(cls, size):
        matching = [media for media in cls.objects.all() if media.bytes >= size]
        return matching[0] if len(matching) else None

    def __str__(self):
        return self.name

    @property
    def bytes(self):
        return get_adjusted_image_size(self.size * ONE_GB)

    @property
    def human(self):
        return human_readable_size(self.size * ONE_GB, False)

    @property
    def units(self):
        return self.size * self.units_coef

    @property
    def verbose_kind(self):
        return self.KINDS.get(self.kind)


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
                del (config["branding"][key]["data"])
            except (TypeError, KeyError):
                pass

        return json.dumps(config, indent=4)


class Order(models.Model):
    NOT_CREATED = "not-created"
    IN_PROGRESS = "in-progress"
    FAILED = "failed"
    COMPLETED = "completed"
    STATUSES = {
        IN_PROGRESS: "In Progress",
        COMPLETED: "Completed",
        FAILED: "Failed",
        NOT_CREATED: "Not accepted by Scheduler",
    }

    class Meta:
        ordering = ["-created_on"]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE)

    scheduler_id = models.CharField(max_length=50, unique=True, blank=True)
    scheduler_data = jsonfield.JSONField(
        load_kwargs={"object_pairs_hook": collections.OrderedDict},
        null=True,
        blank=True,
    )
    scheduler_data_on = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=50, choices=STATUSES.items(), default=IN_PROGRESS
    )

    # copy of request data for archive purpose
    channel = models.CharField(max_length=50)
    client_name = models.CharField(max_length=100)
    client_email = models.EmailField()
    config = jsonfield.JSONField(
        load_kwargs={"object_pairs_hook": collections.OrderedDict}
    )
    media_name = models.CharField(max_length=50)
    media_size = models.IntegerField()
    quantity = models.IntegerField()
    units = models.IntegerField()
    recipient_name = models.CharField(max_length=100)
    recipient_email = models.EmailField()
    recipient_phone = models.CharField(max_length=50, blank=True, null=True)
    recipient_address = models.TextField()
    recipient_country_code = models.CharField(max_length=3)

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
        if not isinstance(statuses, list) or not len(statuses):
            return Order.FAILED
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
    def create_from(cls, client, config, media, quantity, address):
        order = cls(
            organization=client.organization,
            created_by=client,
            channel=client.organization.channel,
            client_name=client.name,
            client_email=client.email,
            config=config.json,
            media_name=media.name,
            media_size=media.size,
            quantity=quantity,
            units=media.units * quantity,
            recipient_name=address.recipient,
            recipient_email=address.email,
            recipient_phone=address.phone,
            recipient_address=address.address,
            recipient_country_code=address.country,
        )
        if order.units > client.organization.units:
            raise ValueError(
                "Order needs {r}U but in {org} has only {a}".format(
                    r=order.units, org=client.organization, a=client.organization.units
                )
            )
        else:
            # remove units from org
            client.organization.units -= order.units
            client.organization.save()

        payload = order.to_payload()
        created, scheduler_id = create_order(payload)
        if not created:
            logger.error(scheduler_id)
            # restore units on org
            client.organization.units += order.units
            client.organization.save()
            raise SchedulerAPIError(scheduler_id)
        order.scheduler_id = scheduler_id
        order.save()
        return order

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
            "sd_card": {"name": self.media_name, "size": self.media_size},
            "quantity": self.quantity,
            "units": self.units,
            "client": {"name": self.client_name, "email": self.client_email},
            "recipient": {
                "name": self.recipient_name,
                "email": self.recipient_email,
                "phone": self.recipient_phone,
                "address": self.recipient_address,
                "country": self.recipient_country_code,
                "shipment": None,
            },
            "channel": self.channel,
            "warehouse": self.organization.get_warehouse_details(),
        }
