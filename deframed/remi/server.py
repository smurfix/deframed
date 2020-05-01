
# An unfortunate global. Oh well.

import weakref
runtimeInstances = weakref.WeakValueDictionary()

# dummies for GUI
App = None
Server = None
start = None
