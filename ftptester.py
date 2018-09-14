#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
import json
import ftplib
from time import sleep
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from typing import Optional


class Operation:
    """Base class for all operations

    Attributes:
        success (:obj:`bool`, optional): task is successful or not
        std_out (:obj:`bytes`, optional): std_out
        error (:obj:`Error`, optional): error of the operation
    """

    name: str = "Operation Base Class"

    def __init__(self):
        self.success: Optional[bool] = None
        self.std_out: Optional[bytes] = None
        self.error: Optional[Error] = None

    @property
    def log(self) -> {}:
        result = {"success": self.success, "name": self.name}

        if self.std_out is not None:
            result["std_out"] = self.std_out.decode()
        if self.error is not None:
            result["error"] = {
                "domain": self.error.domain,
                "code": self.error.code,
                "stderr": self.error.stderr.decode()
                if self.error.stderr is not None
                else None,
            }
        return result

    def execute(self):
        pass


class Error(Exception):
    """Operation Error

    Attributes:
        domain (optional): a code to identify which module produced the error
        code (optional): a code to identify the error if error occurred
        message (:obj:`str`, optional): a message to describe the error if error occurred
        stderr (:obj:`bytes`, optional): stderr
    """

    def __init__(
        self,
        domain: Optional[str],
        code: Optional[int] = None,
        message: Optional[str] = None,
        stderr: Optional[bytes] = None,
    ):
        self.domain = domain
        self.code = code
        self.message = message
        self.stderr = stderr


class Upload(Operation):
    """ Upload zim files to server """

    name = "Upload Zim File"

    def __init__(
        self,
        zim_files_dir: Path,
        dispatcher_host: str,
        warehouse_host: str,
        warehouse_command_port: int,
        username: str,
        password: str,
    ):
        super().__init__()
        self.zim_files_dir: Path = zim_files_dir

        self.dispatcher_host: str = dispatcher_host
        self.warehouse_host: str = warehouse_host
        self.warehouse_command_port: int = warehouse_command_port
        self.username: str = username
        self.password: str = password
        self.token = None

    def execute(self):
        try:
            self._get_token()
            for path in self.zim_files_dir.iterdir():
                if path.is_file() and path.suffix == ".zim":
                    self._safe_upload(path)
                    path.unlink()
            self.zim_files_dir.rmdir()
            self.success = True
        except HTTPError as e:
            self.success = False
            self.error = Error("upload.token.HTTPError", e.code, str(e))
        except ConnectionRefusedError as e:
            self.success = False
            self.error = Error("upload.ftp.ConnectionRefusedError", message=str(e))

    def _get_token(self):
        return  # skip auth for now
        url = "https://{host}/api/auth/authorize".format(host=self.dispatcher_host)
        headers = {"username": self.username, "password": self.password}
        request = Request(url, headers=headers, method="POST")

        with urlopen(request, timeout=30) as response:
            response_json = json.loads(response.read(), encoding="utf-8")
            self.token = response_json["access_token"]

    def _safe_upload(self, path: Path):
        retries = 1
        error = None
        while retries > 0:
            try:
                self._upload(path)
            # except ConnectionRefusedError as exp:
            except Exception as exp:  # ConnectionRefusedError ?
                print("… failed.")
                error = exp
                retries -= 1
                sleep(5)
            else:
                return
        raise error or Exception("")

    def _upload(self, path: Path):
        print("Uploading {}…".format(path.name))
        with ftplib.FTP() as ftp:
            ftp.connect(self.warehouse_host, self.warehouse_command_port, timeout=30)
            ftp.login(self.username, self.token)
            with open(path, "rb") as file:
                ftp.storbinary("STOR {}".format(path.name), file)


if __name__ == "__main__":
    uploader = Upload(
        Path(sys.argv[1]),
        "Setting.dispatcher_host",
        "localhost",
        21,
        "Setting.username",
        "Setting.password",
    )
    uploader.execute()
