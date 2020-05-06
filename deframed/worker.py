"""
This module specifies the worker that's responsible for handling
communication with the client.
"""

from uuid import uuid1,UUID
import trio
from collections.abc import Mapping
from typing import Optional,Dict,List,Union,Any
from .codec import pack, unpack
from functools import partial

from contextvars import ContextVar
processing = ContextVar("processing", default=None)

import logging
logger = logging.getLogger(__name__)

async def _spawn(task, *args, task_status=trio.TASK_STATUS_IGNORED):
    processing.set(None)

    with trio.CancelScope() as sc:
        task_status.started(sc)
        await task(*args)


class UnknownActionError(RuntimeError):
    """
    The client sent a message which I don't understand.
    """
    pass


class ClientError(RuntimeError):
    def __init__(self, _error, **kw):
        self.error = _error
        self.args = kw

    def __repr__(self):
        return 'ClientError(%r,%r)' % (self.error, self.args)

    def __str__(self):
        return 'ClientError(%s%s)' % (self.error, "".join(" %s=%r" % (k,v) for k,v in self.args.items()))


_talk_id = 0

class Talker:
    """
    This class encapsulates the client's websocket connection.

    It is instantiated by the server. You probably should not touch it.
    """
    w = None # Worker
    _scope = None

    def __init__(self, websocket):
        self.ws = websocket

        global _talk_id
        self._id = _talk_id
        _talk_id += 1

    async def run(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Runs the read/write loop on this websocket.
        parallel to some client code.

        This sends the worker's ``fatal_msg`` attribute to the server
        in a ``fatal`` message if the message reader raises an exception.
        """
        logger.debug("START %d", self._id)
        try:
            async with trio.open_nursery() as n:
                self._scope = n.cancel_scope
                await n.start(self.ws_in)
                await n.start(self.ws_out)
                task_status.started()
        finally:
            with trio.fail_after(2) as sc:
                sc.shield=True
                await self.w.maybe_disconnect(self)

    async def died(self, msg):
        """
        Send a "the server has died" message to the client.

        Called from the worker when the connection terminates due to an
        uncaught error.
        """
        logger.exception("Owch")
        with trio.move_on_after(2) as s:
            s.shield = True
            try:
                if self.w:
                    await self._send(["info",["danger",msg]])
            except Exception:
                logger.exception("Terminal message")
                pass

    def cancel(self):
        if self._scope is None:
            return
        self._scope.cancel()

    def attach(self, worker):
        """
        Attach this websocket to an existing worker. Used when a client
        reconnects and presents an existing session ID.
        """
        if isinstance(self.w, trio.Event):
            self.w.set()
        self.w = worker

    async def ws_in(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background task for reading from the web socket.
        """
        task_status.started()
        if isinstance(self.w, trio.Event):
            await self.w.wait()
        while True:
            data = await self.ws.receive()
            try:
                data = unpack(data)
            except TypeError:
                logger.error("IN X %r",data)
                raise
            logger.debug("IN %r",data)
            await self.w.data_in(data)

    async def ws_out(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background task for sending to the web socket
        """
        self._send_q, send_q = trio.open_memory_channel(10)
        task_status.started()
        if isinstance(self.w, trio.Event):
            await self.w.wait()
        while True:
            data = await send_q.receive()
            await self._send(data)

    async def _send(self, data):
        logger.debug("OUT %r",data)
        data = pack(data)
        await self.ws.send(data)

    async def send(self, data:Any):
        """
        Send a message to the client.
        """
        await self._send_q.send(data)


class BaseWorker:
    """
    This is the base class for a client session. It might be interrupted
    (page reload, network glitch, or whatever).

    The talker's read loop calls :meth:`data_in` with the incoming message.
    """
    _talk = None
    _scope = None
    _nursery = None

    title = "You forgot to set a title"
    fatal_msg = "The server had a fatal error.<br />It was logged and will be fixed soon."
    version = None # The server uses DeFramed's version if not set here

    def __init__(self, app):
        self._p_lock = trio.Lock()
        self._app = app
        self.uuid = uuid1()
        app.clients[self.uuid] = self

    async def init(self):
        """
        Setup code. Called by the server for async initialization.

        Note that you can't yet talk to the client here!
        """
        pass

    def attach(self, talker):
        """
        Use this socket to talk. Called by the app.

        The worker's previous websocket is cancelled.
        """
        if self._talk is not None:
            self._talk.cancel()
        self._talk = talker
        talker.attach(self)

    async def _monitor(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background monitor. Don't override externally.
        """
        task_status.started()
        pass

    async def run(self, websocket):
        """
        Main entry point. Takes a websocket, sets up everything, then calls
        ".talk".

        You don't want to override this. Your main code should be in
        `talk`, your setup code (called by the server) in `init`.
        """
        t = Talker(websocket)

        try:
            async with trio.open_nursery() as n:
                self._nursery = n
                await n.start(self._monitor)
                await n.start(t.run)
                self.attach(t)
                with trio.CancelScope() as sc:
                    self._scope = sc
                    try:
                        await self.talk()
                    finally:
                        self._scope = None
        except Exception:
            await t.died(self.fatal_msg)
            raise
        # not on BaseException, as in that case we close the connection and
        # expect the client to try reconnecting
        else:
            await t.died(self.fatal_msg)


    async def talk(self):
        """
        Connection-specific main code. The default does nothing.

        This task will get cancelled when the websocket terminates.
        """
        pass

    def cancel(self):
        if self._scope is not None:
            self._scope.cancel()

        if self._scope is None:
            return
        self._scope.cancel()

    async def spawn(self, task, *args):
        """
        Start a new task. Returns a cancel scope which you can use to stop
        the task.

        By default, errors get logged but don't propagate. Set ``log_exc=False``
        if you don't want that. Or set "log_exc" to the exception, or list of
        exceptions, you want to have logged.
        """
        return await self._nursery.start(_spawn,task,*args)

    async def maybe_disconnect(self, talker):
        """internal method, called by the Talker"""
        if self._talk is talker:
            logger.debug("DISCONNECT")
            await self.disconnect()

    async def disconnect(self):
        """
        The client websocket disconnected. This method might not be called
        when a client reattaches.
        """
        self.cancel()

    async def send(self, data:Any):
        """
        Send a message to the client.
        """
        await self._talk.send(data)

    async def data_in(self, data):
        """
        Process incoming data
        """
        pass


class Worker(BaseWorker):
    """
    This is the main class for a client session.

    The talker's read loop calls ``.msg_{action}`` methods with the
    incoming message. Code in those methods must not call ``.request``
    because that would cause a deadlock. (Don't worry, DeFramed catches
    those.) Start a separate task with ``.spawn`` if you need to do this.
    """
    _persistent_nursery = None
    _kill_exc = None
    _kill_flag = None

    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self._n = 1
        self._req = {}

    async def data_in(self, data):
        """
        Process incoming data. Must be structured [type,data].

        Replies are special:["reply",[assoc_nr,data]].
        """
        action,data = data
        if action == "reply":
            await self._reply(*data)
            return
        try:
            res = getattr(self, 'msg_'+action)
        except AttributeError:
            res = partial(self.any_msg,action)
        tk = processing.set((action,data))
        try:
            await res(data)
        finally:
            processing.reset(tk)

    async def _reply(self, n, data):
        if isinstance(data,Mapping) and '_error' in data:
            data = ClientError(**data)
        evt,self._req[n] = self._req[n],data
        evt.set()

    def cancel(self, persistent=False):
        if persistent and self._persistent_nursery is not None:
            self._persistent_nursery.cancel_scope.cancel()
        super().cancel()

    async def spawn(self, task, *args, persistent=True):
        """
        Start a new task. Returns a cancel scope which you can use to stop
        the task.

        By default, the task persists even if the client websocket
        reconnects. Set ``persistent=False`` if you don't want that.

        By default, errors get logged but don't propagate. Set ``log_exc=False``
        if you don't want that. Or set "log_exc" to the exception, or list of
        exceptions, you want to have logged.
        """
        if persistent:
            return await self._run(_spawn,task,*args)
        else:
            return await self._nursery.start(_spawn,task,*args)

    async def get_attr(self, **a: Dict[str,List[str]]) -> Dict[str,Optional[List[str]]]:
        """
        Returns a list of attributes for some element.
        The element is identified by its ID.

        Returns: a dict with corresponding values, or None if the element
        does not exist.
        """

    async def exists(self, id) -> bool:
        """
        Check whether the DOM element with this ID exists.
        """
        return (await self.get_attr({id:{}}))[id] is not None

    async def elem_info(self, id) -> dict:
        """
        Return information about this element (size, position)
        """
        return await self.request("elem_info", id)

    async def msg_setup(self, data) -> bool:
        """
        Called when the client is connected and says Hello.

        This calls ``.show_main``, thus you should override that instead.

        Returns True when the client either has a version mismatch (and is
        reloaded) or sends a known UUID (and is reassigned).
        """
        v = data.get('version')
        if v is not None and v != self._app.version:
            await self.send('reload',True)
            return True

        await self._setup();

        uuid = data.get('uuid')
        if uuid is None or not self.set_uuid(uuid):
            await self.show_main(token=data['token'])
        else:
            return True

    async def msg_form(self, data):
        """
        Process form submissions.

        The default calls ``.form_{name}(**data)`` or ``.any_form(name,data)``.
        """
        name, data = data
        try:
            p = getattr(self,"form_"+name)
        except AttributeError:
            await self.any_form(name, data)
        else:
            await p(**data)

    async def msg_button(self, name):
        """
        Process button presses.

        The default calls ``.button_{name}()`` or ``.any_button(name)``.
        """
        try:
            p = getattr(self,"button_"+name)
        except AttributeError:
            await self.any_button(name)
        else:
            await p()

    async def any_button(self, name):
        """
        Handle unknown buttons.

        If you don't override it, this method raises an `UnknownActionError`.
        """
        raise UnknownActionError(name)

    async def any_form(self, name, data):
        """
        Handle unknown forms.

        If you don't override it, this method raises an `UnknownActionError`.
        """
        raise UnknownActionError(name, data)

    async def _setup(self):
        """
        Send initial data to the client.

        Called by `msg_setup`.
        You probably should not override this.
        """
        await self.send("setup", version=self._app.version, uuid=str(self.uuid))

    async def alert(self, level, text, **kw):
        """
        Send a pop-up message to the client.

        Levels correspond to Bootstrap contexts:
        primary/secondary/success/danger/warning/info/light/dark.

        The ID of the message is "df_ann_{id}". ``id`` defaults to the
        message type, but you can supply your own.

        A message with any given ID replaces the previous one.
        Messages without text are deleted.

        Text may contain HTML.

        Pass ``timeout`` in seconds to make the message go away by itself.
        Messages can also be closed by the user unless you pass a negative
        timeout.
        """
        await self.send("info", level=level, text=text, **kw)

    async def modal_show(self, id: str = "df_modal", **opts):
        """
        Show a modal window.

        If the ID is not given, use the built-in ``df_modal``.

        Any further parameters are as described in
        https://getbootstrap.com/docs/4.4/components/modal/.
        """
        if not opts:
            opts = True

        await self.send("modal",[id,opts])

    async def modal_hide(self, id: str = "df_modal"):
        """
        Hide a modal window.

        If the ID is not given, use the built-in ``df_modal``.
        """
        await self.send("modal",[id,False])


    async def set_content(self, id: str, html: str, prepend: Optional[bool]=None):
        """
        Set or extend an element's innerHTML content.

        If you set ``prepend`` to `True`, ``html`` will be inserted as
        the first child node(s) of the modified element. Set to `False`,
        it will be added at the end.

        Otherwise the old content will be replaced.

        Args:
          id:
            the modified HTML element's ID.
          html:
            the element's new HTML content.
          prepend:
            Flag whether to add the data in front (``True``), back (``False``) or
            instead of (``None``) the existing content. The default is
            ``None``.
        """
        await self.send("set", [id, html, prepend]);

    async def set_element(self, id: str, html: str):
        """
        Replace an element.

        Args:
          id:
            the old element's ID.
          html:
            the element's replacement.
        """
        await self.send("elem", [id, html]);

    async def load_style(self, id, url):
        """
        Load a stylesheet.

        The ID is used for disambiguation.
        """
        await self.send("load_style", [id, url])

    async def set_attr(self, id: str, **attrs):
        """
        Set or extend an element's attribute(s).
        Args:
          id:
            the modified HTML element's ID.
          attr=value:
            the element's changed attributes.
        """
        await self.send("set_attr", [id, attrs]);

    async def add_class(self, id: str, *cls):
        """
        Add the given classes to an element.

        Args:
          id:
            the modified HTML element's ID.
          cls:
            the class to add.
        """
        await self.send("add_class", [id, cls]);

    async def remove_class(self, id: str, *cls):
        """
        Remove the given classes from an element.

        Args:
          id:
            the modified HTML element's ID.
          cls:
            the class(es) to remove.
        """
        await self.send("remove_class", [id, cls]);

    async def busy(self, busy: bool):
        """
        Show/hide the client's spinner.

        Args:
          busy:
            Flag whether to show the spinner.
        """
        await self.send("busy", busy)

    async def debug(self, val: Union[bool,str]):
        """
        Set/clear the client's debug flag, or log a message on its console.

        While the flag is set, all WebSocket messages are logged on the
        client's console.

        Args:
          val:
            either a `bool` to control the server's debug flag, or a `str`
            to log a message there.
        """
        await self.send("debug", val)

    async def ping(self, token: str, wait: bool = False) -> Optional[str]:
        """
        Send a 'ping' to the client. Echoed back by calling :meth:`msg_pong`.

        If you set ``wait``, the call is synchronous. The client returns
        the token's previous value.

        If you do not set ``wait``, the call returns immediately. The client
        sends a ``pong`` message back; the content is the current (not the
        previous) token.

        Args:
          token:
            Anything packable, but should probably be a string.
          wait:
            Flag whether this call should be synchronous.
        """
        if wait:
            return await self.request("ping", token)
        else:
            await self.send("ping", token)

    async def msg_pong(self, data: Any):
        """
        Called by the client, sometime after you ping it asynchronously.

        Args:
          data:
            the token value you sent with :meth:`send_ping`.
        """
        pass

    async def msg_size(self, evt):
        """
        The main window's size.

        This is informational.
        """
        pass

    async def any_msg(self, action: str, data):
        """
        Catch-all for unknown messages, i.e. the 'msg_{action}' handler
        does not exist.

        If you don't override it, this method raises an UnknownActionError.

        """
        raise UnknownActionError(action,data)

    async def send(self, action:str, data:Any=None, **kw):
        """
        Send a message to the client.

        This method does not wait for a reply.

        You should probably call one of the specific ``send_*` methods instead.
        """
        if action == "req":
            raise RuntimeError("Use '.request' for that!")
        if kw:
            if data:
                data.update(kw)
            else:
                data = kw

        await super().send([action,data])

    async def request(self, action:str, data:Any=None, **kw):
        """
        Send a request to the client, await+return the reply
        """
        if processing.get():
            raise RuntimeError("You cannot call this from within the receiver",processing.get())

        self._n += 1
        n = self._n
        self._req[n] = evt = trio.Event()

        if kw:
            if data:
                data.update(kw)
            else:
                data = kw
        try:
            await super().send(["req",[action,n,data]])
            await evt.wait()
        except BaseException:
            self._req.pop(n)
            raise
        else:
            res = self._req.pop(n)
            if isinstance(res,Exception):
                raise res
            return res

    async def _monitor(self, *, task_status=trio.TASK_STATUS_IGNORED):
        self._kill_wait = trio.Event()
        task_status.started()
        await self._kill_wait.wait()
        raise RuntimeError("Global task died") from self._kill_exc

    async def _run(self, proc, *args, task_status=trio.TASK_STATUS_IGNORED):
        """
        This is the starter for the worker's Websocket-independent nursery.

        If :meth:`spawn` is called with ``persistent`` set, this helper
        starts a background task off the server's nursery which holds it.

        Exceptions are propagated back to the worker.
        """
        async def _work(proc, *args, task_status=trio.TASK_STATUS_IGNORED):
            try:
                async with trio.open_nursery() as n:
                    self._persistent_nursery = n
                    res = await n.start(proc, *args)
                    task_status.started(res)
            except Exception as exc:
                self._kill_exc = exc
                self._kill_flag.set()
            finally:
                self._persistent_nursery = None

        if self._persistent_nursery is None:
            async with self._p_lock:
                return await self._app.main.start(_work,proc,*args)
        else:
            return await self._persistent_nursery.start(proc, *args)

    async def interrupted(self):
        """
        Called when the client disconnects.

        This may or may not be called when a client reconnects.
        """
        pass

    async def show_main(self, token:str=None):
        """
        Override me to show the main window or whatever.

        'token' is the value from the last 'pong'. It is None initially.
        You can use this to distinguish a client reload (empty main page)
        from a websocket reconnect (client state is the same as when you
        sent the last Ping, assuming that you didn't subsequently change
        anything).

        This method may run concurrently with `talk`.
        """
        pass

    def set_uuid(self, uuid:UUID) -> bool:
        """
        Set this worker's UUID.

        If there already is a worker with that UUID, the current worker
        (more specifically, its "connected" subtask) is cancelled.

        Use this to attach a websocket to a running worker after
        exchanging credentials.

        Returns True if the socket has been reassigned.
        """
        if self.uuid == uuid:
            return False
        del self._app.clients[self.uuid]
        w = self._app.clients.get(uuid)
        if w is None:
            self._app.clients[self.uuid] = self
            self.uuid = uuid
            return False
        else:
            w.attach(self._talk)
            self.cancel(True)
            return True


class SubWorker(BaseWorker):
    """
    This is a worker that attaches to another via an iframe.
    """
    def __init__(self, worker):
        self.master = worker
        super().__init__(worker._app)
        self.sub_id = self._app.attach_sub(self)

    async def index(self):
        """
        Render the main page
        """
        raise RuntimeError("You need to override sending the main page")

