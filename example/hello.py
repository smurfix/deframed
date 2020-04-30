#!/usr/bin/python3

import trio
from deframed import App,Worker
from deframed.default import CFG
from wtforms import Form, BooleanField, StringField, validators
from wtforms.widgets import TableWidget

class TestForm(Form):
    username     = StringField('Username', [validators.Length(min=4, max=25)])
    email        = StringField('Email Address', [validators.Length(min=6, max=35)])
    accept_rules = BooleanField('I accept the site rules', [validators.InputRequired()])

import logging
from logging.config import dictConfig as logging_config
logger = logging.getLogger("hello")

class Work(Worker):
    title="Hello!"
    # version="1.2.3" -- uses DeFramed's version if not set

    async def show_main(self, token):
        await self.send_debug(True)
        if token != "A1":
            await self.send_set("df_footer_left", "'Hello' demo example")
            await self.send_set("df_footer_right", "via DeFramed, the non-framework")
            await self.send_set("df_main", """
<p>
This is a toy test program which shows how to talk to your browser.
</p>
<p>
It doesn't do much yet. That will change.
</p>
<form id="form1">
    <table id="plugh"></table>
    <div>
        <button type=submit class="btn btn-primary">✔</button>
    </div>
</form>
            """)

            f=TestForm()
            f.id="plugh"
            fw=TableWidget()
            await self.send_set("plugh", fw(f))

            await self.send_alert("info","Ready!", busy=False, timeout=2)
            await self.ping("A1")
        else:
            await self.send_busy(False)
            await self.send_alert("info", None)

    async def form_form1(self, **kw):
        logger.debug("GOT %r",kw)
        await self.send_set("df_main", "<p>Success! Yeah! <button id=\"butt1\">Do it!</button></p>")

    async def button_butt1(self, **kw):
        logger.debug("GOT %r",kw)
        await self.send_set("df_main", "<p>Aww … you pressed the button!</p>")



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
