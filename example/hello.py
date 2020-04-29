#!/usr/bin/python3

import trio
from deframed import App,Worker
from deframed.default import CFG

import logging
from logging.config import dictConfig as logging_config

class Work(Worker):
	pass

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
