"""
Worker mix-in class that supports Remi.
"""

import os
import trio

from . import gui as remi
from .server import runtimeInstances
from ..worker import SubWorker

import deframed

import logging
logger = logging.getLogger(__name__)

class _RemiWorker(SubWorker):
    def __init__(self, worker, gui, name):
        self.gui = gui
        self._update_evt = trio.Event()
        self._update_loop = None
        super().__init__(worker)

        head = remi.HEAD(name)
        # use the default css, but append a version based on its hash, to stop browser caching
        head.add_child('internal_css', "<link href='/res:style.css' rel='stylesheet' />\n")
        
        body = remi.BODY()
        body.onload.connect(self.onload)
        body.onerror.connect(self.onerror)
        body.ononline.connect(self.ononline)
        body.onpagehide.connect(self.onpagehide)
        body.onpageshow.connect(self.onpageshow)
        body.onresize.connect(self.onresize)
        self.page = remi.HTML()
        self.page.add_child('head', head)
        self.page.add_child('body', body)

        js_path = os.path.join(os.path.dirname(deframed.__file__), "static/remi.js")
        with open(js_path,"r") as f:
            js = f.read()

        msgp = self._app.cfg.data.loc.msgpack
        self.page.children['head'].add_child("msgpack", f'<script type="text/javascript" src="{msgp}" crossorigin="anonymous"></script>');
        self.page.children['head'].add_child("internal_js", "<script>"+js+"</script>");
        #set_internal_js(net_interface_ip, pending_messages_queue_length,      + websocket_timeout_timer_ms)

        self._need_update_flag = False
        self._stop_update_flag = False

        self.page.children['body'].append(gui, 'root')
        self.root = gui
        self.root.disable_refresh()
        self.root.attributes['data-parent-widget'] = str(id(self))
        self.root._parent = self
        self.root.enable_refresh()

        runtimeInstances[str(id(self))] = self

    async def index(self):
        return self.page.innerHTML({})

    async def talk(self):
        # await self.send_set(self.root.identifier, self.page.children['body'].innerHTML({}))
        self._update_loop = await self.spawn(self.update_loop)

    async def msg_callback(self, widget_id, function_name, params):
        callback = getattr(runtimeInstances[widget_id], function_name, None)
        if not params:
            params =  {}
        if callback is not None:
            callback(**params)
        else:
            logger.debug("Unknown callback: %s %s %r", *data)

    def _need_update(self):
        """Callback for updating the client"""
        self._update_evt.set()

    async def update_loop(self):
        while True:
            await self._update_evt.wait()
            self._update_evt = trio.Event()
            logger.debug("Update")

            changed = {}
            self.root.repr(changed)
            for widget,html in changed.items():
                logger.debug("Updating %s",widget)
                __id = str(widget.identifier)
                await self.send(['update',[str(widget.identifier),html]])

    async def data_in(self,data):
        p,m = data
        await getattr(self,'msg_'+p)(*m)

    def cancel(self):
        if self._update_loop is not None:
            self._update_loop.cancel()
            self._update_loop = None
        super().cancel()

    def close(self):
        """ Called by the server when the App have to be terminated
        """
        self._stop_update_flag = True
        self._talk.cancel()
        self.cancel()

    def onload(self, emitter):
        """ WebPage Event that occurs on webpage loaded
        """
        logger.debug('App.onload event occurred')

    def onerror(self, emitter, message, source, lineno, colno):
        """ WebPage Event that occurs on webpage errors
        """
        logger.debug("""App.onerror event occurred in webpage: 
            \nMESSAGE:%s\nSOURCE:%s\nLINENO:%s\nCOLNO:%s\n"""%(message, source, lineno, colno))

    def ononline(self, emitter):
        """ WebPage Event that occurs on webpage goes online after a disconnection
        """
        logger.debug('App.ononline event occurred')

    def onpagehide(self, emitter):
        """ WebPage Event that occurs on webpage when the user navigates away
        """
        logger.debug('App.onpagehide event occurred')

    def onpageshow(self, emitter, width, height):
        """ WebPage Event that occurs on webpage gets shown
        """
        logger.debug('App.onpageshow event occurred')

    def onresize(self, emitter, width, height):
        """ WebPage Event that occurs on webpage gets resized
        """
        logger.debug('App.onresize event occurred. Width:%s Height:%s'%(width, height))


class Remi:
    """
    This is a mix-in class for `deframed.worker.Worker` that supports
    showing the Remi GUI in (part of) your web page.
    """
    _sub_worker = None

    async def show_gui(self, gui, id:str="df_main", height=400, width=500, name="embedded GUI", busy=False):
        """
        Show this Remi GUI (the object you'd usually return from ``main``
        in your Remi ``App`` subclass) in the given element.

        Args:
          gui:
            the toplevel element to show.
          id:
            the element to show it in. Defaults to ``df_main``.
          name:
            the title to use in the iframe.

        You need to call :meth:`hide_gui` to release the GUI data.
        """
        if hasattr(gui,'_sw_id'):
            raise RuntimeError("You're already showing this GUI.")

        if self._sub_worker is None:
            self._sub_worker = {}

        if isinstance(height, int):
            height = str(height)+"px"
        if isinstance(width, int):
            width = str(width)+"px"
        
        w = _RemiWorker(self, gui, name)
        gui._sw_id = id
        gui._sw_subid = w.sub_id
        await self.send_set(id, f'<iframe src="/sub/{w.sub_id}" height="{height}" width="{width}" />')
        if busy is not None:
            await self.send_busy(busy)
    
    async def hide_gui(self, gui):
        """
        remove the GUI
        """
        sw_id = gui._sw_id
        await self.send_set(sw_id, "")
        w = self._sub_worker.pop(sw_id)
        w.close()

        del gui._sw_id
        del gui._sw_subid


    def set_root_widget(self,w):
        if self.main_container is w:
            return
        raise RuntimeError("Replacing the main page is not yet supported")

