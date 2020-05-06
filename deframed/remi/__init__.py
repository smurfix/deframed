"""
Worker mix-in class that supports Remi.
"""

import os
import trio
import weakref

from . import gui as remi
from .server import runtimeInstances
from ..worker import SubWorker

import deframed

import logging
logger = logging.getLogger(__name__)

class _Remi:
    """
    A mix-in with various default handlers.

    A class using this mix-in needs to have valid 'gui' and 'worker' attributes.
    """

    _update_new = None

    def __init__(self,*a,**k):
        self._update_evt = trio.Event()
        super().__init__(*a,**k)

    def _need_update(self):
        """Callback for updating the client"""
        self._update_evt.set()

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

    def set_root_widget(self,w):
        self._update_new = w
        self._update_evt.set()

    async def update_loop(self):
        while True:
            await self._update_evt.wait()
            self._update_evt = trio.Event()
            logger.debug("Update")
            if self._update_new is None:
                changed = {}
                self.gui.repr(changed)
                for widget,html in changed.items():
                    logger.debug("Updating %s",widget)
                    __id = str(widget.identifier)
                    await self.worker.set_element(str(widget.identifier),html)
            else:
                self.gui = self._update_new
                await self.worker.set_content(self.gui_id, self.gui.repr({}))
                self._update_new = None


    async def talk(self):
        pass


class RemiSupport:
    """
    A mix-in which forwards Remi events to its handler.

    Use this in your app.
    """

    async def msg_remi_event(self, data):
        widget_id, function_name, params = data
        callback = getattr(runtimeInstances[widget_id], function_name, None)
        if not params:
            params = {}
        if callback is not None:
            callback(**params)
        else:
            logger.debug("Unknown callback: %s %s %r", *data)


class RemiHandler(_Remi):
    """
    The class controlling a Remi GUI instance when attached to a standard
    element.

    Args:
      worker:
        The worker to attach to.
      gui:
        The Remi GUI to display.
    """

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.gui = self.main()
        worker._remi = weakref.ref(self)

    @property
    def root(self):
        return self.gui

    async def show(self, id:str="df_main"):
        """
        Show this Remi GUI (the object you'd usually return from ``main``
        in your Remi ``App`` subclass) in this element (it should be a
        DIV).

        Call "hide_embed" when you're done.
        """
        self._task = await self.worker.spawn(self._show,id, persistent=False)

    async def _show(self,id):
        w = self.worker
        self.gui._parent = self
        self.gui_id = id

        await w.add_class(id, 'remi-main')
        await w.set_content(id, self.gui.repr({}))

        async with trio.open_nursery() as n:
            n.start_soon(self.update_loop)
            inf = await w.elem_info(id)
            self.onload(None)
            self.onpageshow(None, inf['width'],inf['height'])
            await self.talk()
            # TODO: hook up self.onresize()

    async def hide(self, id:str="df_main"):
        """
        Stop showing this Remi GUI.

        This removes the content and the REMI class.
        """
        w = self.worker
        self._task.cancel()
        await w.set_content(id, '')
        await w.remove_class(id, 'remi-main')


class _RemiWorker(_Remi, SubWorker):
    """
    The internal worker used for IFRAMEs.
    """
    def __init__(self, worker, gui, name):
        self.gui = gui
        self._update_evt = trio.Event()
        self._update_loop = None

        _Remi.init(worker,gui)
        SubWorker.__init__(worker)

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

        js = js.replace("@UUID@", str(self.uuid))
        js = js.replace("@MUUID@", str(self.master.uuid))

        head.add_child("uuid_js", """
            <script>
            window.DF_uuid="{uuid}";
            window.DF_master_uuid="{master}";
            </script>
            """.format(uuid=self.uuid, master=self.master.uuid))
        head.add_child('internal_js', "<script src='/static/main.js' type='text/javascript' />\n")

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
        # await self.set_content(self.root.identifier, self.page.children['body'].innerHTML({}))
        self._update_loop = await self.spawn(self.update_loop)

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


class RemiWorker(SubWorker):
    """
    This is a handler that supports showing the Remi GUI in (part of) your
    web page as an IFRAME.
    """
    _sub_worker = None


    async def show(self, id:str="df_main", height=400, width=500, name="embedded GUI", busy=False):
        """
        Show this Remi GUI (the object you'd usually return from ``main``
        in your Remi ``App`` subclass) in an IFRAME as the sole child of
        the given element.

        Args:
          gui:
            the toplevel element to show.
          id:
            the element to show it in. Defaults to ``df_main``.
          name:
            the title to use in the iframe.

        You need to call :meth:`hide_frame` to release the GUI data.
        """
        if hasattr(self.gui,'_sw_id'):
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
        await self.set_content(id, f'<iframe src="/sub/{w.sub_id}" height="{height}" width="{width}" />')
        if busy is not None:
            await self.busy(busy)
    
    async def hide(self):
        """
        remove the GUI
        """
        sw_id = gui._sw_id
        await self.set_content(sw_id, "")
        w = self._sub_worker.pop(sw_id)
        w.close()

        del gui._sw_id
        del gui._sw_subid


