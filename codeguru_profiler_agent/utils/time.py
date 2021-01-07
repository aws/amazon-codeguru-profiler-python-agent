from __future__ import absolute_import

import time
from datetime import datetime

def to_iso(epoch_milli):
    try:
        return datetime.fromtimestamp(epoch_milli / 1000).isoformat()
    except ValueError:
        return str(epoch_milli)

def current_milli_time(clock=time.time):
    return int(clock() * 1000)
