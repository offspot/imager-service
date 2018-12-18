#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
from collections import OrderedDict

from whost.common import UPDATE_SCRIPT, read_conf, update_conf
from whost.ui import cli, restart_line, display_menu, display_success, display_error
from whost.ui.devices import configure_devices
from whost.ui.network import configure_network
from whost.ui.credentials import configure_credentials, is_authenticated
from whost.network import is_internet_connected


def exit_to_shell():
    display_success("Exiting to shell.")
    sys.exit(10)


def exit_to_logout():
    display_success("Exiting to logout.")
    sys.exit(20)


def update_code():
    cli.info_2("Launching update script…")
    cli.info(str(UPDATE_SCRIPT))


def toggle_host():
    enabled = read_conf().get("enabled", False)
    answer = cli.ask_yes_no(
        "You are about to {} this host. Are you sure?".format(
            "disable" if enabled else "enable"
        )
    )
    if answer:
        ns = "enabled" if not enabled else "disabled"
        if update_conf({"enabled": not enabled}):
            display_success("Successfuly {} host!".format(ns))
        else:
            display_error("Error: host could not be {}.".format(ns))


def display_home():

    cli.info_section("Hotsport Cardshop writer-host configurator")

    print("Checking internet connection…", end="", flush=True)
    connected = is_internet_connected()
    authenticated = is_authenticated() if connected else False
    restart_line()

    config = read_conf()
    connected_str = "CONNECTED" if connected else "NOT CONNECTED"
    connected_color = cli.green if connected else cli.red
    authenticated_str = "AUTHENTICATED" if authenticated else "NOT AUTHENTICATED"
    authenticated_color = cli.green if authenticated else cli.red
    enabled = config.get("enabled", False)
    enabled_color = cli.green if enabled else cli.red
    enabled_str = "ENABLED" if enabled else "DISABLED"
    configured_readers = len(config.get("writers", {}))
    configured_readers_color = cli.yellow if configured_readers else cli.red

    menu = OrderedDict(
        [
            ("configure-network", ("Configure Network", configure_network)),
            ("configure-credentials", ("Configure Credentials", configure_credentials)),
            ("configure-readers", ("Configure USB Writers", configure_devices)),
            ("update-code", ("Update code and restart", update_code)),
            (
                "toggle-host",
                (
                    "{} this Host".format("Enable" if not enabled else "Disable"),
                    toggle_host,
                ),
            ),
            ("exit-to-shell", ("Exit to a shell", exit_to_shell)),
            ("logout", ("Exit (logout)", exit_to_logout)),
        ]
    )

    cli.info_1("Internet Connectivity:", connected_color, connected_str)
    cli.info_1("Authentication:", authenticated_color, authenticated_str)
    cli.info_1("Host Status:", enabled_color, enabled_str)
    cli.info_1("Configured Writers:", configured_readers_color, str(configured_readers))

    display_menu("Choose:", menu=menu)
