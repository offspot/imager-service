from datetime import datetime
from uuid import UUID

from bson.objectid import ObjectId
from flask.json.provider import DefaultJSONProvider


class SchedulerJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat() + "Z"
        elif isinstance(o, UUID):
            return str(o)
        elif isinstance(o, ObjectId):
            return str(o)
        return DefaultJSONProvider.default(o)


def ensure_objectid(object_id):
    if not isinstance(object_id, ObjectId):
        object_id = ObjectId(object_id)
    return object_id
