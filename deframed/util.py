"""
This module contains various helper functions and classes.
"""
from collections.abc import Mapping

import logging
logger = logging.getLogger(__name__)


def singleton(cls):
    return cls()


class TimeOnlyFormatter(logging.Formatter):
    default_time_format = "%H:%M:%S"
    default_msec_format = "%s.%03d"


@singleton
class NotGiven:
    """Placeholder value for 'no data' or 'deleted'."""

    def __getstate__(self):
        raise ValueError("You may not serialize this object")

    def __repr__(self):
        return "<*NotGiven*>"


def combine_dict(*d, cls=dict):
    """
    Returns a dict with all keys+values of all dict arguments.
    The first found value wins.

    This recurses if values are dicts.

    Args:
      cls (type): a class to instantiate the result with. Default: dict.
        Often used: :class:`attrdict`.
    """
    res = cls()
    keys = {}
    if len(d) <= 1:
        return d
    for kv in d:
        for k, v in kv.items():
            if k not in keys:
                keys[k] = []
            keys[k].append(v)
    for k, v in keys.items():
        if len(v) == 1:
            res[k] = v[0]
        elif not isinstance(v[0], Mapping):
            for vv in v[1:]:
                assert not isinstance(vv, Mapping)
            res[k] = v[0]
        else:
            res[k] = combine_dict(*v, cls=cls)
    return res


class attrdict(dict):
    """A dictionary which can be accessed via attributes, for convenience"""

    def __getattr__(self, a):
        if a.startswith("_"):
            return object.__getattr__(self, a)
        try:
            return self[a]
        except KeyError:
            raise AttributeError(a) from None

    def __setattr__(self, a, b):
        if a.startswith("_"):
            super(attrdict, self).__setattr__(a, b)
        else:
            self[a] = b

    def __delattr__(self, a):
        try:
            del self[a]
        except KeyError:
            raise AttributeError(a) from None

