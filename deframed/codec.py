"""
This module contains helper functions for packing+unpacking of single messages,
plus an unpacker factory for streams.
"""

import msgpack
from functools import partial

from .util import attrdict

__all__ = ["pack", "unpack", #"stream_unpacker"
        ]

# single message packer
pack = msgpack.Packer().packb

# single message unpacker
unpack = partial(
    msgpack.unpackb, object_hook=attrdict, use_list=False
)

## stream unpacker factory
#stream_unpacker = partial(msgpack.Unpacker,
#    object_pairs_hook=attrdict, raw=False, use_list=False
#)

