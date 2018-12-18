#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import ipaddress
import subprocess

import yaml
import netifaces
import requests

from whost.common import getLogger, NETPLAN_CONF

logger = getLogger(__name__)
BLANK_CONF = {"network": {"ethernets": {}, "version": 2}}
NAME_SERVERS = ["8.8.8.8", "8.8.4.4"]
NETPLAN_NS = {"nameservers": {"addresses": NAME_SERVERS}}


def read_netplan():
    """ read netplan config file (yaml) """
    with open(str(NETPLAN_CONF), "r") as fd:
        return yaml.load(fd.read())


def save_netplan(config, apply_conf=True):
    """ save netplan config file (yaml) """
    with open(str(NETPLAN_CONF), "w") as fd:
        yaml.safe_dump(config, fd)
    if apply_conf:
        return subprocess.run(["netplan", "try", "--timeout", "1"]).returncode == 0
    return True


def update_netplan(data, apply_conf=True):
    """ update values into netplan config file """
    config = read_netplan()
    config.update(data)
    save_netplan(config, apply_conf=apply_conf)


def reset_netplan():
    """ replace netplan config with blank one """
    return save_netplan(BLANK_CONF, apply_conf=True)


def get_iface_config(iface):
    """ simple address/netmask/gateway access to real netplan conf for an iface """
    conf = read_netplan()["network"]["ethernets"].get(iface, {})
    addresses = conf.get("addresses", [])
    address = addresses[0] if addresses else None
    address_str = netmask_str = None
    if address:
        try:
            aif = ipaddress.ip_interface(address)
            address_str = aif.ip.compressed
            netmask_str = aif.hostmask.compressed
        except Exception:
            pass
    return {
        "address": address_str,
        "netmask": netmask_str,
        "gateway": conf.get("gateway4"),
    }


def get_interfaces(skip_loopback=True):
    """ list of available network interfaces """
    all_ifaces = netifaces.interfaces()
    if skip_loopback:
        return filter(
            lambda x: not x.startswith("lo") if skip_loopback else x, all_ifaces
        )
    return all_ifaces


def is_internet_connected():
    """ boolean whether kiwix website is avail via HTTP (hence internet OK) """
    try:
        requests.head("http://kiwix.org")
        return True
    except Exception as exp:
        logger.error(exp)
        return False


def save_network_config(iface, dhcp, address=None, netmask=None, gateway=None):
    if dhcp:
        return configure_dhcp(iface)
    return configure_static(iface, address=address, netmask=netmask, gateway=gateway)


def configure_dhcp(iface):
    dhcp_conf = {"addresses": [], "dhcp4": True, "optional": True}
    dhcp_conf.update(NETPLAN_NS)
    netplan = read_netplan()
    netplan["network"]["ethernets"].update({iface: dhcp_conf})
    return save_netplan(netplan)


def configure_static(iface, address, netmask, gateway):
    nma = ipaddress.ip_interface("{a}/{m}".format(a=address, m=netmask))
    fixed_conf = {
        "addresses": [nma.compressed],
        "gateway4": gateway,
        "dhcp4": False,
        "optional": True,
    }
    fixed_conf.update(NETPLAN_NS)
    netplan = read_netplan()
    netplan["network"]["ethernets"].update({iface: fixed_conf})
    return save_netplan(netplan)
