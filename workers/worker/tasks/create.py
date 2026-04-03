#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
import io
import json
import logging
import re
import subprocess
import tempfile
import threading
import urllib.parse

import torf
import yaml
from kiwixstorage import KiwixStorage
from utils import get_checksum
from utils.s3 import ImageTransferHook
from utils.scheduler import authenticate, get_access_token, update_task_status
from utils.setting import Setting

try:
    from yaml import CDumper as Dumper
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    # we don't NEED cython ext but it's faster so use it if avail.
    from yaml import Dumper, SafeLoader

logger = logging.getLogger(__name__)


def get_image_creator_version(payload: dict) -> str | None:
    try:
        if re.match(r"^[\d\.]+$", payload["image-creator"]["version"]):
            return payload["image-creator"]["version"]
    except Exception:
        ...


class CreateTask(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.exception: Exception = None  # exception to be re-raised by caller
        self.task: dict = {}
        self.logs = {}

        self._should_stop: bool = False  # stop flag

        self.extra = {}  # extra data to populate and send

        self.logger = logging.getLogger(__name__)  # to be overwritten

    def stop(self):
        self.logger.info("stopping thread")
        self._should_stop = True

    @property
    def canceled(self):
        return self._should_stop

    def report_status(self, status, status_log=None):
        self.logger.info(
            "updating task #{} status to: {}".format(self.task["_id"], status)
        )
        success, tid = update_task_status(
            self.task["_id"], status, status_log, extra=self.extra
        )
        return success

    def file_path(self, ext):
        return Setting.working_dir.joinpath(self.task["fname"]).with_suffix(f".{ext}")

    def read_log(self, path):
        cat = subprocess.run(["cat", str(path)], text=True, capture_output=True)
        return "{stdout}\n{stderr}".format(
            stdout=cat.stdout or "", stderr=cat.stderr or ""
        )

    def remove_files(self, only_errorneous=True):
        suffixes = [".ERROR.img", ".BUILDING.img"]
        if not only_errorneous:
            suffixes.append(".img")

        for suffix in suffixes:
            path = Setting.working_dir.joinpath(self.img_name + suffix)
            if path.is_file():
                logger.info("removing {}".format(path.name))
                path.unlink()

        # delete config and log
        for path in (self.log_path, self.config_path):
            if path.is_file():
                path.unlink()

    @property
    def img_path(self):
        return self.file_path("img")

    @property
    def torrent_path(self):
        return self.img_path.with_suffix(f"{self.img_path.suffix}.torrent")

    @property
    def img_name(self):
        return self.img_path.stem

    @property
    def log_path(self):
        return self.file_path("txt")

    @property
    def uploader_log_path(self):
        return self.file_path("log")

    @property
    def config_path(self):
        return self.file_path("yaml")

    def run(self):
        self.task, self.logger = self._args

        # make sure warehouse URI is OK before we start
        try:
            urllib.parse.urlparse(self.task["upload_uri"])
        except Exception as exp:
            self.logger.error("Error: Warehouse URI could not be parsed")
            self.logger.exception(exp)
            self.exception = exp
            self.report_status("failed", str(exp))
            return

        states = [
            ("build_image", "building", "built", "failed_to_build"),
            (
                "upload_image",
                "uploading",
                (
                    "uploaded_public"
                    if self.task["media_type"] == "virtual"
                    else "uploaded"
                ),
                "failed_to_upload",
            ),
        ]

        for method, working_status, success_status, failed_status in states:
            try:
                self.report_status(working_status)
                getattr(self, method)()
            except Exception as exp:
                self.logger.exception(exp)
                self.exception = exp
                if self.canceled:
                    self.report_status("canceled")
                else:
                    self.report_status(failed_status, str(exp))
                return
            else:
                self.report_status(success_status)

    def build_image(self):
        self.logger.info("Starting image creation")
        imager_path = Setting.imager_binary_path

        # read config
        payload = yaml.load(self.task["config_yaml"], Loader=SafeLoader)

        # were we asked to use a specific image-creator version?
        ic_version = get_image_creator_version(payload)
        if ic_version:
            imager_path = imager_path.with_name(f"image-creator_{ic_version}")
            if not imager_path.exists():
                logger.warning(f"requested image-creator version missing: {ic_version}")
                imager_path = Setting.imager_binary_path

        # write config to file, making sure to exclude special image-creator prop
        try:
            del payload["image-creator"]
        except KeyError:
            ...
        self.config_path.write_text(
            yaml.dump(payload, Dumper=Dumper, explicit_start=True, sort_keys=False)
        )
        del payload

        build_dir = tempfile.TemporaryDirectory(
            suffix=".build",
            dir=Setting.working_dir,
            ignore_cleanup_errors=True,
        )
        args = [
            str(imager_path),
            "--max-size",
            "1TB",
            "--debug",
            "--cache-dir",
            str(Setting.cache_dir),
            "--build-dir",
            build_dir.name,
            str(self.config_path),
            str(self.img_path),
        ]

        self.logger.info("Starting {args}\n".format(args=" ".join(args)))

        self.logs["installer_log"] = "{args}\n".format(args=" ".join(args))
        log_fd = open(str(self.log_path), "w")
        ps = subprocess.Popen(
            args=args,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            close_fds=True,
        )

        self.logger.info("installer started: {}".format(ps))
        while ps.poll() is None:
            self.logs["installer_log"] = self.read_log(self.log_path)

            # kill upon request
            if self.canceled:
                self.logger.info("terminating installer…")
                ps.terminate()
                ps.wait(10)
                ps.kill()
                ps.wait(10)
                break

        ps.wait(10)

        successful = ps.returncode == 0 and self.img_path.exists()

        if successful:
            self.logger.info("installer ran successfuly.")
            # get and store size and checksum
            self.extra["image"] = {
                "fname": self.img_path.name,
                "size": self.img_path.stat().st_size,
                "checksum": "{0}:{1}".format(*get_checksum(str(self.img_path))),
            }
        else:
            self.logger.error("installer failed: {}".format(ps.returncode))

        self.logger.info("collecting full terminated log")
        self.logs["installer_log"] = self.read_log(self.log_path)

        # clean up working folder
        build_dir.cleanup()
        self.remove_files()

        if not successful:
            raise subprocess.SubprocessError("installer rc: {}".format(ps.returncode))

    def upload_image(self):
        # first build torrent with expected sources
        self._build_torrent_file()

        # then upload torrent file to all sources
        self._upload_image_to_warehouse()

        # then delete torrent file
        try:
            self.logger.info("removing torrent file: {}".format(self.torrent_path.name))
            self.torrent_path.unlink(missing_ok=True)
        except Exception as exp:
            self.logger.error("Unable to remove torrent file: {}".format(exp))
            self.logger.exception(exp)

        # then upload image files to all sources
        upload_succeeded = self.upload_images_to_all_locations()

        # remove image
        try:
            self.logger.info("removing image file: {}".format(self.img_path.name))
            self.img_path.unlink()
        except Exception as exp:
            self.logger.error("Unable to remove image file: {}".format(exp))
            self.logger.exception(exp)

        if not upload_succeeded:
            raise subprocess.SubprocessError("File upload failed")

    def _build_torrent_file(self):
        uploader_logger = logging.getLogger("uploader_log")
        uploader_logger.info(f"Creating torrent file for {self.img_path.name}")
        webseeds = []

        dl_urls = urllib.parse.urlparse(self.task["download_uris"])
        for dl_url in dl_urls:
            parts = list(urllib.parse.urlsplit(dl_url.geturl()))
            parts[0] = parts[0].replace("+torrent", "")
            dl_url = urllib.parse.urlparse(urllib.parse.urlunsplit(parts))
            download_url = f"{dl_url.geturl()}/{self.img_path.name}"
            webseeds.append(download_url)
        
        torrent = torf.Torrent(
            path=self.img_path,
            trackers=[],
            webseeds=webseeds,
        )
        torrent.generate()
        torrent.write(self.torrent_path)


    def upload_image_to_dest(self):
        upload_url = self.task["upload_uri"]

        # add (secret) credentials to S3 URL
        if self.task["upload_uri"].startswith("s3"):
            upload_uri = urllib.parse.urlparse(self.task["upload_uri"])
            qs = urllib.parse.parse_qs(upload_uri.query)
            qs["keyId"] = [Setting.s3_access_key]
            qs["secretAccessKey"] = [Setting.s3_secret_key]
            upload_url = urllib.parse.SplitResult(
                "https",
                upload_uri.netloc,
                upload_uri.path,
                urllib.parse.urlencode(qs, doseq=True),
                upload_uri.fragment,
            ).geturl()





    def _upload_image(self):

        if self.task["upload_uri"].startswith("s3://"):
            self.upload_image_s3()
        elif
        else:
            self.upload_image_with_curl()

    def upload_image_s3(self):
        self.logger.info("Starting S3 upload")

        # add credentials to URL
        url = urllib.parse.urlparse(self.task["upload_uri"])
        qs = urllib.parse.parse_qs(url.query)
        qs["keyId"] = Setting.s3_access_key
        qs["secretAccessKey"] = Setting.s3_secret_key

        # setup upload logging
        uploader_log = io.StringIO()
        uploader_logger = logging.getLogger("uploader_log")
        uploader_logger.propagate = True
        uploader_logger.setLevel(logging.DEBUG)
        uploader_logger.addHandler(logging.StreamHandler(stream=uploader_log))

        # init and test storage
        uploader_logger.info("initializing S3")
        s3_storage = KiwixStorage(
            urllib.parse.SplitResult(
                "https",
                url.netloc,
                url.path,
                urllib.parse.urlencode(qs, doseq=True),
                url.fragment,
            ).geturl()
        )
        uploader_logger.debug(
            f"S3 initialized for {s3_storage.url.netloc}/{s3_storage.bucket_name}"
        )

        # torrent
        dl_url = urllib.parse.urlparse(self.task["download_uri"])
        upload_torrent = "torrent" in dl_url.scheme

        if upload_torrent:
            parts = list(urllib.parse.urlsplit(dl_url.geturl()))
            parts[0] = parts[0].replace("+torrent", "")
            dl_url = urllib.parse.urlparse(urllib.parse.urlunsplit(parts))

            uploader_logger.info(f"Creating torrent file for {self.img_path.name}")
            torrent_path = self.img_path.with_suffix(f"{self.img_path.suffix}.torrent")
            download_url = f"{dl_url.geturl()}/{self.img_path.name}"
            torrent = torf.Torrent(
                path=self.img_path,
                trackers=[
                    "https://opentracker.xyz:443/announce",
                    "http://torrent.nwps.ws:80/announce",
                    "udp://tracker.open-internet.nl:6969/announce",
                    "udp://tracker.coppersurfer.tk:6969/announce",
                    "udp://tracker.openbittorrent.com:80/announce",
                ],
                webseeds=[download_url],
            )
            torrent.generate()
            torrent.write(torrent_path)
            uploader_logger.info(f".. created {torrent_path.name}")

            uploader_logger.info(f"Uploading {torrent_path.name}")
            s3_storage.upload_file(fpath=str(torrent_path), key=torrent_path.name)
            uploader_logger.info(".. uploaded")
            torrent_path.unlink()

        # upload
        uploader_logger.info(f"Uploading to {self.img_path.name}")
        try:
            hook = ImageTransferHook(output=uploader_log, fpath=self.img_path)
            s3_storage.upload_file(
                fpath=str(self.img_path), key=self.img_path.name, Callback=hook
            )
            uploaded = True
        except Exception as exc:
            uploaded = False
            uploader_logger.error(f"uploader failed: {exc}")
            uploader_logger.exception(exc)
        else:
            uploader_logger.info("uploader ran successfuly.")

        # setting autodelete
        try:
            # make sure autodelete is above bucket's min retention (should be 1d)
            expire_on = datetime.datetime.now() + datetime.timedelta(
                days=max([2, self.task["media_duration"]])
            )
            uploader_logger.info(f"Setting autodelete to {expire_on}")
            s3_storage.set_object_autodelete_on(key=self.img_path.name, on=expire_on)
        except Exception as exc:
            uploader_logger.error("Failed to set autodelete")
            uploader_logger.exception(exc)

        if upload_torrent:
            try:
                uploader_logger.info(f"Setting torrent autodelete to {expire_on}")
                s3_storage.set_object_autodelete_on(key=torrent_path.name, on=expire_on)
            except Exception as exc:
                uploader_logger.error("Failed to set autodelete on torrent")
                uploader_logger.exception(exc)

        self.logger.info("collecting uploader log")
        try:
            self.logs["uploader_log"] = uploader_log.getvalue()
            uploader_log.close()
        except Exception as exc:
            self.logger.error(f"Failed to collect logs: {exc}")

        # remove image
        try:
            self.logger.info("removing image file: {}".format(self.img_path.name))
            self.img_path.unlink()
        except Exception as exp:
            self.logger.error("Unable to remove image file: {}".format(exp))
            self.logger.exception(exp)

        if not uploaded:
            raise subprocess.SubprocessError("S3 upload failed")

