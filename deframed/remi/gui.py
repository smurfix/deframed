from . import server
import sys
sys.modules['remi.server'] = sys.modules['deframed.remi.server']

from remi.gui import *


