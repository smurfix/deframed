"""
This module contains the default values for configuring DeFramed.
"""

from .util import attrdict

__all__ = ["CFG"]

CFG = attrdict(
    logging=attrdict( # a magic incantation
        version=1,
        loggers=attrdict(
            #"asyncari": {"level":"INFO"},
        ),
        root=attrdict(
            handlers= ["stderr",],
            level="INFO",
        ),
        handlers=attrdict(
            logfile={
                "class":"logging.FileHandler",
                "filename":"/var/log/deframed.log",
                "level":"INFO",
                "formatter":"std",
            },
            stderr={
                "class":"logging.StreamHandler",
                "level":"INFO",
                "formatter":"std",
                "stream":"ext://sys.stderr",
            },
        ),
        formatters=attrdict(
            std={
                "class":"deframed.util.TimeOnlyFormatter",
                "format":'%(asctime)s %(levelname)s:%(name)s:%(message)s',
            },
        ),
        disable_existing_loggers=False,
    ),
    server=attrdict( # used to setup the hypercorn toy server
        host="127.0.0.1",
        port=8080,
        prio=0,
        name="test me",
        use_reloader=False,
        ca_certs=None,
        certfile=None,
        keyfile=None,
    ),
    mainpage="templates/layout.mustache",
    data=attrdict( # passed to main template
        title="Test page. Do not test!",
        loc=attrdict(
            msgpack="/static/ext/msgpack.min.js",
            cash="/static/ext/cash.min.js",
            mustache="/static/ext/mustache.min.js",
        ),
        static="static", # path
    ),
)
