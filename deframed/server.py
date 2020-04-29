import os
import trio
from typing import Optional, Any
from functools import partial
from quart_trio import QuartTrio as Quart
from hypercorn.config import Config as HyperConfig
from hypercorn.trio import serve as hyper_serve
from quart.logging import create_serving_logger
from quart import jsonify, websocket
from quart.static import send_from_directory
import chevron

from .util import attrdict, combine_dict
from .default import CFG
from .worker import Worker

from deframed import __file__ as _deframed_path

class App:
    """
    This is deframed's main code.

    You probably don't need to subclass this.
    """
    def __init__(self, cfg: dict, worker: Worker):
        cfg = combine_dict(cfg, CFG, cls=attrdict)
        self.cfg = cfg
        self.main = None # Nursery
        self.clients = {}
        self.worker = worker

        self.app = Quart(cfg.server.name,
                # no, we do not want any of those default folders and whatnot
                static_folder=None,template_folder=None,root_path="/nonexistent",
                )

        @self.app.route("/<path:p>", methods=['GET'])
        @self.app.route("/", defaults={"p":None}, methods=['GET'])
        async def index(p):
            mainpage = os.path.join(os.path.dirname(_deframed_path), self.cfg.mainpage)
            with open(mainpage, 'r') as f:
                return chevron.render(f, self.cfg.data)

        @self.app.websocket('/ws')
        async def ws():
            await self.main.start(self._main, websocket._get_current_object())

        static = os.path.join(os.path.dirname(_deframed_path), cfg.data.static)
        @self.app.route("/static/<path:filename>", methods=['GET'])
        async def send_static(filename):
            print("GET",filename)
            return await send_from_directory(static, filename)

    async def _main(self, ws, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        """
        async with trio.open_nursery() as n:
            w = self.worker(n,ws)
            await w.init()
            await n.start(w.ws_in)
            await n.start(w.ws_out)
            self.worker[w.uuid] = w
            try:
                task_status.started()
                await w.run()
            finally:
                del self.clients[w.uuid]

    async def run (self) -> None:
        """
        Run this application.

        This is a simple Hypercorn runner.
        You should use something more elaborate. in a production setting
        """
        config = HyperConfig()
        cfg = self.cfg.server
        config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"
        config.access_logger = create_serving_logger()  # type: ignore
        config.bind = [f"{cfg.host}:{cfg.port}"]
        config.ca_certs = cfg.ca_certs
        config.certfile = cfg.certfile
#   if debug is not None:
#       config.debug = debug
        config.error_logger = config.access_logger  # type: ignore
        config.keyfile = cfg.keyfile
        config.use_reloader = cfg.use_reloader

        scheme = "http" if config.ssl_enabled is None else "https"

        await hyper_serve(self.app, config)


