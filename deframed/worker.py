"""
Base "worker" class that handles client comm
"""

import uuid
import trio
from typing import Optional,Dict,List
from .codec import pack, unpack

from contextvars import ContextVar
processing = ContextVar("processing", default=None)


class ClientError(RuntimeError):
    def __init__(self, _error, **kw):
        self.error = _error
        self.args = kw

    def __repr__(self):
        return 'ClientError(%r,%r)' % (self.error, self.args)

    def __str__(self):
        return 'ClientError(%s%s)' % (self.error, "".join(" %s=%r" % (k,v) for k,v in self.args.items()))


class _Talker:
    """
    This internal class encapsulates the client's websocket connection.
    """
    def __init__(self, worker, websocket):
        self.w = worker
        self.ws = websocket
        self.n = 1
        self.req = {}
        self.cancel = lambda:None

    async def run(self):
        """
        Run the read/write loop on this websocket,
        parallel to some client code.
        """
        async with trio.open_nursery() as n:
            self.cancel = n.cancel_scope.cancel
            await n.start(self.ws_in)
            await n.start(self.ws_out)
            await self.w.connected()

    async def ws_in(*, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background task for reading from the web socket.
        """
        task_status.started()
        while True:
            data = await self._ws.receive()
            action,data = unpack(data)
            if action == "reply":
                self._reply(*data)
                continue

            res = getattr(self.w, 'msg_'+action)
            tk = processing.set((action,n))
            try:
                await res(data)
            finally:
                processing.reset(tk)

    async def _reply(self,n,data):
        if isinstance(data,Mapping) and '_error' in data:
            data = ClientError(**data)
        evt,self.req[n] = self.req[n],data
        evt.set()

    async def ws_out(*, task_status=trio.TASK_STATUS_IGNORED):
        """
        Background task for sending to the web socket
        """
        self._send_q, send_q = trio.open_memory_channel(10)
        task_status.started()
        while True:
            action,data = await send_q.receive()
            data = pack([action,data])
            await self.ws.send(data)

    async def send(self, action,data):
        """
        Send a message to the client
        """
        if action == "req":
            raise RuntimeError("Use '.request' for that!")
        await self.send_q.put((action,data))

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
    def __init__(self, nursery):
        self._nursery = nursery
        self.uuid = uuid.uuid1()

    async def init(self):
        """
        Setup code. Call this supermethod when overriding.

        Note that you can't yet talk to the client here!
        """
        pass

    async def talk(self, websocket):
        """
        Use this socket to talk.
        """
        t, self._talk = self._talk, _Talker(self, websocket)
        if t is not None:
            t.cancel()
        try:
            await self._talk.run()
        finally:
            if self._talk is not None and self._talk.ws is websocket:
                self._talk = None
                await self.interrupted()

    async def disconnect(self):
        if self._talk is None:
            return

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
        Called when the client says Hello.

        """
        if data['uuid'] != self.uuid:
            raise RuntimeError(f"UUID error: want {self.uuid} got {data['uuid']}")
        await self.send_alert("info","So you want to log in?")
        await self.show_main(data['token'])


    async def send_alert(self, level, text):
        await self.send("info", {"level":level, "text":text})

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

    async def run(self):
        """
        Main code of your application, running in the background.

        It's OK for this to be empty.
        """
        pass

    async def connected(self):
        """
        Called when the client connects or reconnects.

        This async function doesn't need to return. It will get cancelled
        when the current websocket disconnects.

        The default does nothing.
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
