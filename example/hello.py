#!/usr/bin/python3

import trio
from deframed import App,Worker
from deframed.default import CFG

import logging
from logging.config import dictConfig as logging_config

class Work(Worker):
    async def msg_first(self, data):
        await super().msg_first(data);
        await self.send_set("df_footer_left", "'Hello' demo example")
        await self.send_set("df_footer_right", "via DeFramed, the non-framework")
        await self.send_set("df_main", """
<p>
This is a toy test program which shows how to talk to your browser.
</p>
<p>
It doesn't do much yet. That will change.
</p>
            """)
        await self.send_alert("info","Ready!", busy=False, timeout=2)


async def main():
    del CFG.logging.handlers.logfile
    CFG.logging.handlers.stderr["level"]="DEBUG"
    CFG.logging.root["level"]="DEBUG"
    CFG.server.host="0.0.0.0"
    CFG.server.port=50080

    logging_config(CFG.logging)
    app=App(CFG,Work)
    await app.run()
trio.run(main)

# See "deframed.default.CFG" for defaults and whatnot
