#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import ipaddress
from collections import OrderedDict

from whost.ui import cli, display_menu, get_valid_string, display_error, display_success
from whost.network import get_interfaces, save_network_config, reset_netplan, get_iface_config


def ipadress_validator(value):
    """ IPv4 address validator """
    try:
        ipaddress.ip_address(value).compressed
    except ValueError:
        return None, "Invalid IPv4 address format"
    return (value, None)


def reset_network_config():
    """ restore initial blank /etc/network/configure """

    if reset_netplan():
        display_success("Network configuration has been reset via netplan.")
    else:
        display_error("Failed to reset network config via netplan.")


def configure_network():

    cli.info_2("You need one, direct, ethernet Internet connection.")
    menu = OrderedDict(
        [
            (
                "reset-network-config",
                ("Reset network config (remove ALL interfaces)", reset_network_config),
            ),
            ("configure-iface", ("Configure Interface", configure_iface)),
        ]
    )

    display_menu("Choose:", menu=menu, with_cancel=True)


def configure_iface():

    # pick interface
    ifaces = list(get_interfaces())
    iface = display_menu("Choose Interface:", choices=ifaces, with_cancel=True)
    cli.info("You selected", cli.bold, iface)
    iface_config = get_iface_config(iface)
    from pprint import pprint as pp

    pp(iface_config)

    # select method (dhcp, fixed)
    dhcp = "dhcp"
    fixed = "fixed"
    methods = [dhcp, fixed]
    method = display_menu("Connection method:", choices=methods, with_cancel=True)

    if method == dhcp:
        if save_network_config(iface, dhcp=True):
            cli.info_2(
                "Saved your",
                cli.bold,
                iface,
                cli.reset,
                "configuration as",
                cli.bold,
                "DHCP",
            )
        else:
            display_error("Unable to save DHCP network config for", cli.bold, iface)
        return

    # fixed method config

    # get address
    address = get_valid_string(
        "IP Address", ipadress_validator, default=iface_config["address"]
    )
    cli.info("You entered", cli.bold, address)

    netmask = get_valid_string(
        "Netmask", ipadress_validator, default=iface_config["netmask"]
    )
    cli.info("You entered", cli.bold, netmask)

    gateway = get_valid_string(
        "Gateway", ipadress_validator, default=iface_config["gateway"]
    )
    cli.info("You entered", cli.bold, gateway)

    if save_network_config(
        iface, dhcp=False, address=address, netmask=netmask, gateway=gateway
    ):
        cli.info_2(
            "Saved your",
            cli.bold,
            iface,
            cli.reset,
            "configuration as",
            cli.bold,
            address,
            cli.reset,
            "/",
            cli.bold,
            netmask,
            cli.reset,
            "/",
            cli.bold,
            gateway,
        )
    else:
        display_error("Unable to save fixed network config for", cli.bold, iface)
