#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from manager.scheduler import query_api, GET, fix_id


class APIQuerySet(object):
    """ QuerySet-like object for an API request's results """

    def __init__(self, query, method=GET, params={}):
        self.method = method
        self.query = query
        self.params = params
        self.count = 0
        self.execute()

    def execute(self, skip=None, limit=None):
        success, code, response = query_api(
            GET, self.query, params={"skip": skip, "limit": limit}
        )
        if success and "items" in response:
            self.count = response["meta"]["count"]
            return self.process(response.get("items", []))
        else:
            self.count = 0
            return []

    def __len__(self):
        return self.count

    def __repr__(self):
        return str(self.query)

    def __getitem__(self, sliced):
        start = sliced.start or 0
        stop = sliced.stop
        limit = (stop - start) if stop else None
        return self.execute(skip=start, limit=limit)

    def process(self, results):
        return map(fix_id, results)
