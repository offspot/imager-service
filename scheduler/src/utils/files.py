import datetime
import logging
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import SplitResult, parse_qs, urlencode, urlparse

import requests
from kiwix_uploader.api import remove_file_retrying, set_marker_retrying

from utils.mongo import UploadedFiles

AUTO_IMAGES_EXTEND_BEFORE_DAYS = int(os.getenv("AUTO_IMAGES_EXTEND_BEFORE_DAYS") or 5)
AUTO_IMAGES_EXTEND_FOR_DAYS = int(os.getenv("AUTO_IMAGES_EXTEND_FOR_DAYS") or 10)
# Path to SSH private key used to delete files from warehouse
SSH_KEY_PATH = Path(os.getenv("PRIVATE_SSH_KEY_PATH", "/etc/ssh/uploader.key")).resolve(
    strict=True
)
# S3 credentials used to delete files from warehouse (or update wasabi autodelete)
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY") or ""
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY") or ""

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_credentials_s3_url(s3_url: str) -> str:
    url = urlparse(s3_url)
    qs = parse_qs(url.query)
    qs["keyId"] = [S3_ACCESS_KEY]
    qs["secretAccessKey"] = [S3_SECRET_KEY]
    return SplitResult(
        "https",
        url.netloc,
        url.path,
        urlencode(qs, doseq=True),
        url.fragment,
    ).geturl()


class MarkerNotFound(Exception): ...


class InvalidExpirationDate(Exception): ...


class FileChecker:
    http_timeout: int = 20
    extend_before_days: int = AUTO_IMAGES_EXTEND_BEFORE_DAYS
    extend_for_days: int = AUTO_IMAGES_EXTEND_FOR_DAYS
    marker_suffix: str = ".delete_on"

    def __init__(self, file: dict):
        self.file = file

    def _file_exists(self, fname_suffix: str) -> bool:
        """whether the file (or marker using correct suffix) exists (HTTP check)"""
        resp = requests.get(
            f"{self.file['download_url']}{fname_suffix}",
            allow_redirects=True,
            timeout=self.http_timeout,
            stream=True,
        )
        if resp.status_code == HTTPStatus.NOT_FOUND:
            return False
        resp.raise_for_status()
        return True

    def file_exists(self) -> bool:
        """whether file stil exists (avail via HTTP)"""
        return self._file_exists("")

    def marker_exists(self) -> bool:
        """whether marker (delete date holder) stil exists (avail via HTTP)"""
        return self._file_exists(self.marker_suffix)

    def remove_anyway(self):
        """remove the file and its marker from storage"""
        self.remove_file_and_entry()

    @property
    def max_renewal_date(self):
        """date in the future after which expiration extension is required"""
        return datetime.datetime.now() + datetime.timedelta(
            days=self.extend_before_days
        )

    @property
    def next_expiration_on(self):
        """date to expire at based on previous expiration and constant (nb days)"""
        return datetime.datetime.now() + datetime.timedelta(days=self.extend_for_days)

    @property
    def expire_on(self) -> datetime.datetime:
        if not hasattr(self, "_expire_on"):
            self._expire_on = self.get_expiry()
        return self._expire_on

    @expire_on.setter
    def expire_on(self, on: datetime.datetime):
        self._expire_on = on

    def extend_if_expiring_soon(self) -> bool:
        """extend expiration date if it's close to expiration"""
        try:
            self.expire_on
        except (MarkerNotFound, InvalidExpirationDate):
            # set in past so considered expired
            self.expire_on = datetime.datetime.now() - datetime.timedelta(
                days=self.extend_before_days, minutes=1
            )
        except Exception as exc:
            # network error? log
            logger.error(
                f"Failed to check {self.file['_id']},{self.file['download_url']}: {exc!s}"
            )
            return False

        if self.expire_on <= self.max_renewal_date:
            return self.update_marker_with(days_from_now=self.extend_for_days)
        return False

    def update_marker_with(self, days_from_now: int) -> bool:
        """Upload a marker with the new datetime."""
        upload_url = (
            get_credentials_s3_url(self.file["upload_url"])
            if self.file["upload_url"].startswith("s3")
            else self.file["upload_url"]
        )

        return (
            set_marker_retrying(
                upload_url=upload_url,
                private_key=SSH_KEY_PATH,
                delete_after=days_from_now,
            )
            == 0
        )

    def remove_if_expired(self) -> bool:
        """remove file both from storage and DB is it expired"""
        try:
            self.expire_on
        except (MarkerNotFound, InvalidExpirationDate):
            return self.remove_file_and_entry()
        except Exception as exc:
            # network error? log
            logger.error(
                f"Failed to check {self.file['_id']},{self.file['download_url']}: {exc!s}"
            )
            return False

        if self.expire_on < datetime.datetime.now():
            return self.remove_file_and_entry()

        return False

    def remove_file_and_entry(self):
        """remove file from both storage and DB"""
        self.remove_file_from_storage()
        # only remove entry if file removal succeeded (didnt fail)
        self.remove_db_entry()
        return True

    def remove_file_from_storage(self):
        marker_exists, file_exists = self.marker_exists(), self.file_exists()
        if not file_exists and not marker_exists:
            return

        upload_url = (
            get_credentials_s3_url(self.file["upload_url"])
            if self.file["upload_url"].startswith("s3")
            else self.file["upload_url"]
        )
        if file_exists:
            # remove file
            remove_file_retrying(upload_url=upload_url, private_key=SSH_KEY_PATH)

        if marker_exists:
            # remove expiration marker file
            remove_file_retrying(
                upload_url=f"{upload_url}{self.marker_suffix}", private_key=SSH_KEY_PATH
            )

    def remove_db_entry(self):
        return UploadedFiles().delete_one({"_id": self.file["_id"]}).deleted_count

    def get_expiry(self) -> datetime.datetime:
        """expiration date as specified in marker file (fetch via HTTP)"""
        resp = requests.get(
            f"{self.file['download_url']}{self.marker_suffix}",
            allow_redirects=True,
            timeout=self.http_timeout,
        )
        if resp.status_code == HTTPStatus.NOT_FOUND:
            raise MarkerNotFound()

        try:
            return datetime.datetime.fromisoformat(resp.text)
        except Exception:
            raise InvalidExpirationDate()
