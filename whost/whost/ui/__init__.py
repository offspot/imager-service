#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys

from whost.ui import cli


CANCEL = "CANCEL"
CANCEL_LIST = [CANCEL]


def handle_cancel(value):
    """ print and exit if value i cancel """
    if value == CANCEL:
        display_success("Canceling ; exiting.")
        sys.exit(1)


def display_menu(label, choices=None, menu=None, launch=True, with_cancel=False):

    # built list of choices if from menu
    if choices is None:
        choices = list(menu.keys())

    if with_cancel:
        choices += CANCEL_LIST

    choices_t = list(choices)

    def _func_name(x):
        if menu is None:
            return x
        return menu.get(x, (CANCEL,))[0]

    def _func_desc(x):
        return choices_t.index(x)

    selected = cli.ask_choice(
        label, choices=choices, func_name=_func_name, func_desc=_func_desc
    )
    handle_cancel(selected)
    if menu is not None and launch:
        return menu.get(selected)[1]()
    return selected


def display_success(*message):
    """ standardized way of displaying a success message """
    cli.info_2(*message)


def display_error(*message):
    """ standardized way of displaying an error message """
    cli.info(cli.red, *message)


def restart_line():
    """ reset a single printed line (useful for loader) """
    sys.stdout.write("\r")
    sys.stdout.flush()


def get_valid_string(label, validator, default=None):
    """ shortcut to request a string validated via a callback """
    value, error = None, None
    while value is None:
        if error:
            cli.info(cli.yellow, error)
        value, error = validator(cli.ask_string(label, default=default))
    return value


def nonempty_validator(value):
    """ validator ensuring value is not empty """
    if not value:
        return None, "Empty value not allowed"
    return (value, None)
