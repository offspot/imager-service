from datetime import datetime
from uuid import UUID

from bson.objectid import ObjectId
from flask.json import JSONEncoder


class Encoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat() + "Z"
        elif isinstance(o, UUID):
            return str(o)
        elif isinstance(o, ObjectId):
            return str(o)
        else:
            super().default(o)


def ensure_objectid(object_id):
    if not isinstance(object_id, ObjectId):
        object_id = ObjectId(object_id)
    return object_id
