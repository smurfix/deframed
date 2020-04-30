"""
Base "worker" class that handles client comm
"""

import uuid
import trio
from typing import Optional,Dict,List,Union
from .codec import pack, unpack
from functools import partial

from contextvars import ContextVar
processing = ContextVar("processing", default=None)

import logging
logger = logging.getLogger(__name__)


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
    This internal class encapsulates the client's websocket connection.
    """
    w = None # Worker
    _scope = None

    def __init__(self, websocket):
        self.ws = websocket
        self.n = 1
        self.req = {}

        global _talk_id
        self._id = _talk_id
        _talk_id += 1

    async def run(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Run the read/write loop on this websocket,
        parallel to some client code.
        """
        logger.debug("START %d", self._id)
        try:
            async with trio.open_nursery() as n:
                self._scope = n.cancel_scope
                await n.start(self.ws_in)
                await n.start(self.ws_out)
                task_status.started()
        except Exception as exc:
            logger.exception("Owch")
            with trio.move_on_after(2) as s:
                s.shield = True
                try:
                    if self.w:
                        await self._send("fatal",self.w.fatal_msg)
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
            data = unpack(data)
            logger.debug("IN %r",data)
            action,data = data
            if action == "reply":
                self._reply(*data)
                continue

            try:
                res = getattr(self.w, 'msg_'+action)
            except AttributeError:
                res = partial(self.w.any_msg,action)
            tk = processing.set((action,data))
            try:
                await res(data)
            finally:
                processing.reset(tk)

    async def _reply(self, n, data):
        if isinstance(data,Mapping) and '_error' in data:
            data = ClientError(**data)
        evt,self.req[n] = self.req[n],data
        evt.set()

    async def ws_out(self, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background task for sending to the web socket
        """
        self._send_q, send_q = trio.open_memory_channel(10)
        task_status.started()
        if isinstance(self.w, trio.Event):
            await self.w.wait()
        while True:
            action,data = await send_q.receive()
            await self._send(action,data)

    async def _send(self, action, data):
        data = [action,data]
        logger.debug("OUT %r",data)
        data = pack(data)
        await self.ws.send(data)

    async def send(self, action,data):
        """
        Send a message to the client.
        """
        if action == "req":
            raise RuntimeError("Use '.request' for that!")
        await self._send_q.send((action,data))

    async def request(self, action,data):
        """
        Send a request to the client, await+return the reply
        """
        if processing.get():
            raise RuntimeError("You cannot call this from within the receiver",processing.get())

        self.n += 1
        n = self.n
        self.req[n] = evt = trio.Event()
        try:
            await self.send_q.put(("ask",[action,n,data]))
            await evt.wait()
        except BaseException:
            self.req.pop(n)
            raise
        else:
            res = self.req.pop(n)
            if isinstance(res,Exception):
                raise res
            return res


class Worker:
    """
    This is the base class for a client session. It might be interrupted
    (page reload, network glitch, or whatever).

    The worker's read loop calls ``.msg_{action}`` methods with the
    incoming message. Code in those methods must not call ``.request``
    because that would cause a deadlock. (Don't worry, DeFramed catches
    those.) Start a separate task with ``.spawn`` if you need to do this.
    """
    _talk = None
    _scope = None
    _nursery = None

    title = "You forgot to set a title"
    fatal_msg = "The server had a fatal error.<br />It was logged and will be fixed soon."
    version = None # The server uses DeFramed's version if not set here

    def __init__(self, app):
        self._app = app
        self.uuid = uuid.uuid1()
        app.clients[self.uuid] = self

    async def init(self):
        """
        Setup code. Call this supermethod when overriding.

        Note that you can't yet talk to the client here!
        """
        pass

    async def attach(self, talker):
        """
        Use this socket to talk. Called by the app.

        The previous websocket is left alone; in fact it may still deliver
        incoming messages.

        """
        talker.attach(self)
        self._talk = talker


    async def talk(self):
        """
        Connection-specific main code. The default does nothing.

        This task will get cancelled when the websocket terminates.
        """
        pass

    def cancel(self):
        if self._scope is None:
            return
        self._scope.cancel()

    async def spawn(self, task, *args, persistent=True, log_exc=True):
        """
        Start a new task. Returns a cancel scope which you can use to stop
        the task.

        By default, the task persists even if the client websocket
        reconnects. Set ``persistent=False`` if you don't want that.

        By default, errors get logged but don't propagate. Set ``log_exc=False``
        if you don't want that. Or set "log_exc" to the exception, or list of
        exceptions, you want to have logged.
        """
        async def _spawn(task, args, *, task_status=trio.TASK_STATUS_IGNORED):
            with trio.CancelScope() as sc:
                task_status.started(sc)
                try:
                    await task(*args)
                except Exception as exc:
                    if log_exc is False:
                        raise
                    if log_exc is not True and not isinstance(exc, log_exc):
                        raise
                    logger.exception("Error in %r %r", task, args)

        await (self.app.main if persistent else self._nursery).start(_spawn,task,args)
        

    async def maybe_disconnect(self, talker):
        """internal method, only called by the App"""
        if self._talk is talker:
            await self.disconnect()

    async def disconnect(self):
        """
        The client websocket disconnected. This method may not be called
        when a client reattaches.
        """
        self.cancel()

    async def getattr(self, **a: Dict[str,List[str]]) -> Dict[str,Optional[List[str]]]:
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
        return (await self.getattr({id:{}}))[id] is not None

    async def msg_first(self, data) -> bool:
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

        await self.send_first();

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

        Defaults to raising `UnknownActionError`.
        """
        raise UnknownActionError(name)

    async def any_form(self, name, data):
        """
        Handle unknown forms.

        Defaults to raising `UnknownActionError`.
        """
        raise UnknownActionError(name, data)

    async def send_first(self):
        """
        Send initial data to the client.

        Called by `msg_first`.
        You probably should not override this.
        """
        await self.send("first", version=self._app.version, uuid=str(self.uuid))

    async def send_alert(self, level, text, **kw):
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

    async def send_set(self, id, html):
        await self.send("set", id=id, content=html);

    async def send_busy(self, busy: bool):
        await self.send("busy", busy)

    async def send_debug(self, val: Union[bool,str]):
        await self.send("debug", val)

    async def ping(self, token, wait=False):
        """
        Send a 'ping' to the client. Echoed back by calling 'msg_pong'.

        Use this as a sync mechanism, or to measure roundtrip speed.

        Returns the previous token when waiting, otherwise calls 'msg_pong'
        with the token you just sent.
        """
        if wait:
            return await self.request("ping", token)
        else:
            await self.send("ping", token)

    async def msg_pong(self, data):
        """
        Called sometime after you ping the client without waiting.
        """
        pass

    async def any_msg(self, action, data):
        """
        Catch-all for unknown messages, i.e. the 'msg_{action}' handler
        does not exist.

        The default raises an UnknownActionError.
        """
        raise UnknownActionError(action,data)

    async def send(self, action, data=None, **kw):
        """
        Send a message to the client.

        Does not wait for a reply.
        """
        if kw:
            if data:
                kw.update(data)
            else:
                data = kw

        await self._talk.send(action,data)

    async def request(self, action, data):
        """
        Send a request to the client.

        Returns the reply, or raises an error.
        """
        return await self._talk.request(action,data)

    async def run(self, websocket):
        """
        Main entry point. Takes a websocket, sets up everything, then calls
        ".talk".

        You probably don't want to override this. Your main code should be
        in ".talk", your setup code in ".init".
        """
        t = Talker(websocket)
            
        try:
            async with trio.open_nursery() as n:
                self._nursery = n
                await n.start(t.run)    
                await self.attach(t)
                with trio.CancelScope() as sc:
                    self._scope = sc
                    try:
                        await self.talk()
                    finally:
                        self._scope = None
        finally:
            with trio.fail_after(2) as sc:
                sc.shield=True
                await self.maybe_disconnect(t)


    async def interrupted(self):
        """
        Called when the client disconnects.

        This may or may not be called when a cllient reconnects.
        """
        pass

    async def show_main(self, token=None):
        """
        Override me to show the main window or whatever.

        'token' is the value from the last 'pong'. It is None initially.
        You can use this to distinguish a client reload (empty main page) 
        from a websocket reconnect (client state is the same as when you
        sent the last Ping, assuming that you didn't subsequently change
        anything).
        """
        pass

    def set_uuid(self, uuid) -> bool:
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
            self.cancel()
            return True


