"""
Django settings for manager project.

Generated by 'django-admin startproject' using Django 2.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import os
import pathlib
import urllib.parse

from django.utils.translation import gettext_lazy as _lz
from offspot_config.builder import BRANDING_PATH, Reader
from offspot_config.constants import INTERNAL_BRANDING_PATH
from offspot_config.inputs.checksum import Checksum
from offspot_config.utils.download import read_checksum_from
from offspot_config.utils.misc import b64_encode

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(BASE_DIR), "manager-data"
)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "s245*pzp1poz*#_!&$65&ld!f)5de2eshwc*!8w(2#5d&w0b=0"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(os.getenv("DEBUG", ""))

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost"),
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "manager",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "manager.middlewares.language_middleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "manager.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "manager.wsgi.application"


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(DATA_DIR, "db.sqlite3"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = "en"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

LOCALE_PATHS = [f"{BASE_DIR}/locale"]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

###############
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "manager": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "DEBUG"),
            "propagate": False,
        },
    },
}

# configure database from env DSN
if os.getenv("DATABASE", ""):
    database = {}
    dsn = urllib.parse.urlparse(os.getenv("DATABASE"))
    if dsn.scheme in ("mariadb", "mysql"):
        database = {
            "ENGINE": "django.db.backends.mysql",
            "NAME": dsn.path[1:] if dsn.path else None,
            "USER": dsn.username,
            "PASSWORD": dsn.password or "",
            "HOST": dsn.hostname,
            "PORT": str(dsn.port or 3306),
            "OPTIONS": {"init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
        }
    elif dsn.scheme.startswith("sqlite"):
        database = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": dsn.path,
        }
    DATABASES["default"] = database

    MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"

CONN_MAX_AGE = 600
CONN_HEALTH_CHECKS = True

MEDIA_ROOT = os.path.join(DATA_DIR, "media")
MEDIA_URL = "/media/"
STATIC_ROOT = os.path.join(DATA_DIR, "static")
STATIC_URL = "/static/"
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "stephane@kiwix.org")
# manager admin account's password
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
# manager's token over the API (/!\)
MANAGER_API_USERNAME = os.getenv("MANAGER_API_USERNAME", "manager")
MANAGER_API_KEY = os.getenv("MANAGER_API_KEY", "manager")
# API URL
CARDSHOP_API_URL = os.getenv("CARDSHOP_API_URL", "https://api.imager.kiwix.org")
CARDSHOP_API_URL_EXTERNAL = os.getenv(
    "CARDSHOP_API_URL_EXTERNAL", "https://api.imager.kiwix.org"
)
# Token for API allowing creation of user accounts
ACCOUNTS_API_TOKEN = os.getenv("ACCOUNTS_API_TOKEN", "dev")
# email-sending related (mailgun API)
MAIL_FROM = os.getenv("MAIL_FROM", "cardshop@kiwix.org")
MAILGUN_API_URL = os.getenv(
    "MAILGUN_API_URL", "https://api.mailgun.net/v3/cardshop.hotspot.kiwix.org"
)
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
# used for sending reset password links in emails
CARDSHOP_PUBLIC_URL = os.getenv("CARDSHOP_PUBLIC_URL", "https://imager.kiwix.org")
CONTENTS_FILE = os.path.join(BASE_DIR, "contents.json")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "main",
        "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "3600")),
        "OPTIONS": {"MAX_ENTRIES": 10},
    }
}

LANGUAGES = [
    ("en", _lz("English")),
    ("fr", _lz("French")),
]

BASE_IMAGE_URL = os.getenv("BASE_IMAGE_URL", "1.3.1")
BASE_IMAGE_ROOTFS_SIZE = int(os.getenv("BASE_IMAGE_ROOTFS_SIZE", "2663383040"))
OFFSPOT_TLD = os.getenv("OFFSPOT_TLD", "hotspot")
# should utilmately be supported by offspot-config
OFFSPOT_LANGUAGES = [
    ("en", _lz("English")),
    ("fr", _lz("French")),
]

# map of platform to URL for Kiwix Readers
# All of them will be added to the builder if use selects the appr. option
# must be manually updated from time to time
KIWIX_READERS_SOURCES = {
    "windows": "https://download.kiwix.org/release/kiwix-desktop/kiwix-desktop_windows_x64_2.4.1.zip",
    "android": "https://mirror.download.kiwix.org/release/kiwix-android/"
    "org.kiwix.kiwixmobile.standalone-3.14.0.apk",
    "macos": "https://download.kiwix.org/release/kiwix-macos/kiwix-macos_3.9.0.dmg",
    "linux": "https://download.kiwix.org/release/kiwix-desktop/"
    + "kiwix-desktop_x86_64_2.3.1-4.appimage",
}


def get_reader_from(platform: str, url: str):
    uri = urllib.parse.urlsplit(url)
    if uri.netloc == "download.kiwix.org":
        checksum = Checksum(algo="md5", value=read_checksum_from(f"{url}.md5"))
        url = uri._replace(netloc="mirror.download.kiwix.org").geturl()
    else:
        checksum = None
    return Reader.using(platform=platform, download_url=url, checksum=checksum)


# fetch this on start and forget about it
KIWIX_READERS = [
    get_reader_from(platform, url) for platform, url in KIWIX_READERS_SOURCES.items()
]

# map of ident to description for all currently being tested beta features
# OK to be empty.
# must be handled individually in builder
BETA_FEATURES = {
    # "dashboard-1.4": "Dashboard 1.4 UI with separate Downloads and Readers option",
    # "image-creator-1.0": "Image-creator 1.0 with aria2 downloader",
}


def get_branding_payload(fname: str) -> dict:
    data = INTERNAL_BRANDING_PATH.joinpath(fname).read_bytes()
    # write to disk for web-server served previews
    fpath = pathlib.Path(MEDIA_ROOT).joinpath("branding").joinpath(fname)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_bytes(data)
    return {
        "url_or_content": b64_encode(data),
        "to": str(BRANDING_PATH.joinpath(fname)),
        "via": "base64",
        "size": len(data),
        "is_url": False,
    }


BRANDING_FILES_PAYLOADS = {
    fname: get_branding_payload(fname)
    for fname in ("horizontal-logo-light.png", "square-logo-light.png")
}

DEFAULT_DOMAIN = "kiwix"
DEFAULT_SSID = "Kiwix Hotspot"
try:
    BRANDING_ORGS = list(set((os.getenv("BRANDING_ORGS") or "").split("|")))
except Exception:
    BRANDING_ORGS = []
