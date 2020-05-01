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
    debug=False,
    data=attrdict( # passed to main template
        title="Test page. Do not test!",
        loc=attrdict(
            #msgpack="https://github.com/ygoe/msgpack.js/raw/master/msgpack.min.js",
            msgpack="/static/ext/msgpack.min.js",
            #mustache="https://github.com/janl/mustache.js/raw/master/mustache.min.js",
            mustache="/static/ext/mustache.min.js",
            bootstrap_css="https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/css/bootstrap.min.css",
            bootstrap_js="https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/js/bootstrap.min.js",
            poppler="https://cdn.jsdelivr.net/npm/popper.js@1.16.0/dist/umd/popper.min.js",
            jquery="https://code.jquery.com/jquery-3.4.1.slim.min.js",
        ),
        static="static", # path
    ),
)
