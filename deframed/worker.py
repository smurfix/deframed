"""
Base "worker" class that handles client comm
"""

import uuid
import trio
from typing import Optional,Dict,List
from .codec import pack, unpack

from contextvars import ContextVar
processing = ContextVar("processing", default=None)

import logging
logger = logging.getLogger(__name__)

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
        self.w = trio.Event()
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
        async with trio.open_nursery() as n:
            self._scope = n.cancel_scope
            await n.start(self.ws_in)
            await n.start(self.ws_out)
            task_status.started()

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

            res = getattr(self.w, 'msg_'+action)
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
    """
    _talk = None
    _scope = None

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

    async def talk(self, talker, *, task_status=trio.TASK_STATUS_IGNORED):
        """
        Use this socket to talk. Called by the app.

        The previous websocket is left alone; in fact it may still deliver
        incoming messages.

        """
        talker.attach(self)
        self._talk = talker
        self.cancel()

        with trio.CancelScope() as sc:
            self._scope = sc
            task_status.started()
            try:
                await self.connected()
            finally:
                self._scope = None

    def cancel(self):
        if self._scope is None:
            return
        self._scope.cancel()

    async def spawn(self, task, *args):
        async def _spawn(task, args, *, task_status=trio.TASK_STATUS_IGNORED):
            task_status.started()
            try:
                await task(*args)
            except Exception:
                logger.exception("Error in %r %r", task, args)
        await self.app.main.start(_spawn,task,args)
        

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

    async def msg_first(self, data):
        """
        Called when the client is connected and says Hello.

        """
        uuid = data.get('uuid')
        if uuid is None or not await self.set_uuid(uuid):
            await self.show_main(token=data['token'])


    async def send_alert(self, level, text, **kw):
        kw['level'] = level
        kw['text'] = text
        await self.send("info", kw)

    async def send_set(self, id, html):
        await self.send("set", {"id":id,"content":html});

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

    async def send(self, action, data):
        await self._talk.send(action,data)

    async def request(self, action, data):
        return await self._talk.request(action,data)

    async def run(self):
        """
        Main code of your application, running in the background.

        It's OK for this to be empty.
        """
        pass

    async def connected(self, token=None):
        """
        Called when the client connects or reconnects.

        This async function doesn't need to return. It will get cancelled
        when the current websocket disconnects.

        The default does nothing.

        This code runs in the context of the current websocket connection.
        If you want to start a long-running task, use "self.spawn".
        """
        pass

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
        """
        if self.uuid == uuid:
            return False
        del app.clients[self.uuid]
        w = app.clients.get(uuid)
        if w is None:
            self.uuid = uuid
            return False
        else:
            w.attach(self._talk)
            self.cancel()
            return True


