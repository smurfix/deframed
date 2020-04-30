from .server import App
from .worker import Worker

from importlib.metadata import version as _version, PackageNotFoundError
try:
	__version__ = _version('deframed')
except PackageNotFoundError:
	import subprocess
	import io
	c = subprocess.run("git describe --tags".split(" "), capture_output=True)
	__version__ = c.stdout.decode("utf-8").strip()


