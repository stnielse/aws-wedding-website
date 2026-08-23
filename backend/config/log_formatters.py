"""JSON log formatter for CloudWatch-friendly structured logging.

Emits one JSON object per record with a stable core shape:

    {"timestamp": "2026-08-02T14:30:00.123Z",
     "level": "INFO",
     "logger": "rsvp.views",
     "message": "rsvp_submitted",
     "guest_ids": [1, 2],
     "attending_count": 2}

Any ``extra={}`` kwargs passed to a logger call appear at the top level of
the JSON payload. Exception info nests under an ``exception`` key.

Hand-rolled rather than pulling in ``python-json-logger`` — the whole
implementation is small and the transitive-dep audit doesn't pay off for a
wedding site.
"""

import datetime as _dt
import json
import logging

# Attributes present on every ``LogRecord`` — anything else on the record's
# ``__dict__`` came from ``extra=`` and should surface in the JSON output.
_LOGRECORD_ATTRS = {
    'args',
    'asctime',
    'created',
    'exc_info',
    'exc_text',
    'filename',
    'funcName',
    'levelname',
    'levelno',
    'lineno',
    'message',
    'module',
    'msecs',
    'msg',
    'name',
    'pathname',
    'process',
    'processName',
    'relativeCreated',
    'stack_info',
    'taskName',
    'thread',
    'threadName',
}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': _dt.datetime.fromtimestamp(record.created, tz=_dt.UTC)
            .isoformat(timespec='milliseconds')
            .replace('+00:00', 'Z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _LOGRECORD_ATTRS or key.startswith('_'):
                continue
            payload[key] = value

        if record.exc_info:
            exc_type, exc_value, _tb = record.exc_info
            payload['exception'] = {
                'type': exc_type.__name__ if exc_type else None,
                'message': str(exc_value) if exc_value else None,
                'stack': self.formatException(record.exc_info),
            }

        return json.dumps(payload, default=str)


class SkipClient4xx(logging.Filter):
    """Drop 4xx records from the ``django.request`` logger.

    Django emits ``Resolver404`` misses as WARNINGs on ``django.request``
    with ``status_code=404``. A public origin gets scanned constantly for
    ``/.env``, ``/wp-admin/*``, and hundreds of appliance paths; the 404s
    are correct behavior and add nothing actionable. 5xx records still
    pass -- those are the ones the ``django-errors`` metric filter cares
    about. Records without ``status_code`` (non-request logs routed
    through a shared handler) also pass through unchanged.
    """

    def filter(self, record):
        status = getattr(record, 'status_code', None)
        if status is None:
            return True
        return status >= 500
