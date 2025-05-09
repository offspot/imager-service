import datetime
import os
import re
import urllib.parse

import xmltodict
from kiwixstorage import KiwixStorage

from utils.mongo import AutoImages

DOWNLOAD_WAREHOUSE_UPLOAD_URI = os.getenv("DOWNLOAD_WAREHOUSE_UPLOAD_URI") or ""
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY") or ""
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY") or ""


def get_s3_url() -> str:
    url = urllib.parse.urlparse(DOWNLOAD_WAREHOUSE_UPLOAD_URI)
    qs = urllib.parse.parse_qs(url.query)
    qs["keyId"] = [S3_ACCESS_KEY]
    qs["secretAccessKey"] = [S3_SECRET_KEY]
    return urllib.parse.SplitResult(
        "https",
        url.netloc,
        url.path,
        urllib.parse.urlencode(qs, doseq=True),
        url.fragment,
    ).geturl()


QUALIFIED_S3_URL = get_s3_url()


def get_s3_storage() -> KiwixStorage:
    return KiwixStorage(QUALIFIED_S3_URL)


def get_autodelete_date_for(slug: str) -> datetime.datetime:
    image = AutoImages.get(slug)
    s3 = get_s3_storage()
    img_key = re.sub(r"^/", "", urllib.parse.urlparse(image["http_url"]).path)
    payload = xmltodict.parse(s3.get_wasabi_compliance(key=img_key))
    return datetime.datetime.fromisoformat(
        payload["ObjectComplianceConfiguration"]["RetentionTime"].replace("Z", "")
    )


def update_autodelete_for(slug: str, on: datetime.datetime):
    image = AutoImages.get(slug)
    img_key = re.sub(r"^/", "", urllib.parse.urlparse(image["http_url"]).path)
    torrent_key = re.sub(r"^/", "", urllib.parse.urlparse(image["torrent_url"]).path)
    s3 = get_s3_storage()
    s3.set_object_autodelete_on(key=img_key, on=on)
    s3.set_object_autodelete_on(key=torrent_key, on=on)
