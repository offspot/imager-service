#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import urllib
import datetime
import xml.etree.ElementTree as ET

from kiwixstorage import KiwixStorage

S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")


def get_url_for(bucket_name=None):

    url = urllib.parse.urlparse("s3://s3.us-west-1.wasabisys.com/")
    qs = urllib.parse.parse_qs(url.query)
    qs["keyId"] = S3_ACCESS_KEY
    qs["secretAccessKey"] = S3_SECRET_KEY
    if bucket_name:
        qs["bucketName"] = bucket_name

    return urllib.parse.SplitResult(
        "https",
        url.netloc,
        url.path,
        urllib.parse.urlencode(qs, doseq=True),
        url.fragment,
    ).geturl()


def storage_for_key(key):

    # init and test storage
    s3_storage = KiwixStorage(get_url_for())

    for wh in ("download", "warehouse"):
        bucket_name = f"org-kiwix-hotspot-cardshop-{wh}"
        print(f"testing {bucket_name}")
        if s3_storage.has_object(key, bucket_name=bucket_name):
            return KiwixStorage(get_url_for(bucket_name))

    raise ValueError(f"Couldn't find a bucket with key `{key}`")


def extend_validity(key, days=7):

    s3_storage = storage_for_key(key)
    print(f"Found key `{key}` on {s3_storage.bucket_name}")
    try:
        compliance = s3_storage.get_wasabi_compliance(key, s3_storage.bucket_name)
    except Exception as exc:
        print("Can't get compliance, {exc}")
        raise exc
    print("Current compliance:", compliance)

    try:
        retention_time_str = ET.fromstring(compliance)[0].text
        retention_time = datetime.datetime.fromisoformat(retention_time_str[:-1])
    except Exception as exc:
        print("Can't parse retention_time")
        raise exc

    new_retention_time = retention_time + datetime.timedelta(days=days)
    print(f"Extending by {days}d to {new_retention_time}...")
    s3_storage.set_object_autodelete_on(
        key=key,
        on=new_retention_time,
    )
    print("OK!")


if __name__ == "__main__":
    if not S3_ACCESS_KEY or not S3_SECRET_KEY:
        print(
            f"Missing environ `S3_ACCESS_KEY` ({S3_ACCESS_KEY}) and/or `S3_SECRET_KEY` ({S3_SECRET_KEY})"
        )
        sys.exit(1)

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <order-id> [<nb-days(7)>]")
        sys.exit(1)

    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    extend_validity(f"{sys.argv[1]}.img", days)
