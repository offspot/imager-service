#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu


from django.core.management.commands import makemessages


class Command(makemessages.Command):
    xgettext_options = [  # noqa: RUF012
        *makemessages.Command.xgettext_options,
        "--keyword=_lz",
    ]
