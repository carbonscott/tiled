"""Reference worker: run HDF5ArrayAdapter reads under whichever tiled is importable.

Reads pickled commands from stdin (length-prefixed), writes pickled results to stdout.
"""

import pickle
import struct
import sys
import traceback
import types
import warnings

warnings.simplefilter("ignore")

import numpy  # noqa: E402

from tiled.adapters.hdf5 import HDF5ArrayAdapter  # noqa: E402
from tiled.ndslice import NDBlock, NDSlice  # noqa: E402
from tiled.structures.array import ArrayStructure, BuiltinDtype  # noqa: E402
from tiled.structures.data_source import Asset, DataSource  # noqa: E402

import h5py  # noqa: E402

NBYTES = []
_getitem = h5py.Dataset.__getitem__


def _counting_getitem(self, *args, **kwargs):
    o = _getitem(self, *args, **kwargs)
    NBYTES.append(numpy.asarray(o).nbytes)
    return o


h5py.Dataset.__getitem__ = _counting_getitem

out = sys.stdout.buffer
inp = sys.stdin.buffer
sys.stdout = sys.stderr  # keep stray prints off the protocol pipe


def recv():
    hdr = inp.read(4)
    if not hdr:
        return None
    (n,) = struct.unpack("<I", hdr)
    return pickle.loads(inp.read(n))


def send(obj):
    b = pickle.dumps(obj)
    out.write(struct.pack("<I", len(b)) + b)
    out.flush()


def describe_exc(e):
    return ("err", type(e).__name__, [c.__name__ for c in type(e).__mro__], str(e)[:300])


def describe_result(r):
    return (
        "ok",
        type(r).__name__,
        numpy.asarray(r).copy(),
        str(numpy.asarray(r).dtype),
        tuple(numpy.shape(r)),
        sum(NBYTES),
    )


def make_adapter(cmd):
    mode = cmd["mode"]
    kw = dict(dataset=cmd["dataset"], slice=cmd["slice"], squeeze=cmd["squeeze"])
    if mode == "uris":
        return HDF5ArrayAdapter.from_uris(*cmd["uris"], **kw)
    # catalog mode: structure given (shape, chunks) or derived from uris
    base = HDF5ArrayAdapter.from_uris(*cmd["uris"], **kw)
    st = base.structure()
    shape = tuple(cmd.get("shape") or st.shape)
    chunks = cmd.get("chunks") or st.chunks
    structure = ArrayStructure(
        data_type=st.data_type, shape=shape, chunks=tuple(map(tuple, chunks))
    )
    assets = [
        Asset(data_uri=u, is_directory=False, parameter="data_uris", num=i)
        for i, u in enumerate(cmd["uris"])
    ]
    ds = DataSource(
        structure_family="array",
        structure=structure,
        mimetype="application/x-hdf5",
        parameters=dict(kw),
        assets=assets,
        management="external",
    )
    node = types.SimpleNamespace(metadata_={}, specs=[])
    return HDF5ArrayAdapter.from_catalog(ds, node, **kw)


def handle(cmd):
    try:
        adapter = make_adapter(cmd)
    except Exception as e:
        return {"construct": describe_exc(e)}
    res = {"construct": ("ok",)}
    st = adapter.structure()
    res["structure"] = (tuple(st.shape), tuple(map(tuple, st.chunks)), str(st.data_type.to_numpy_dtype()))
    reads = []
    for req in cmd.get("requests", []):
        NBYTES.clear()
        try:
            if req is None:
                r = adapter.read()
            else:
                r = adapter.read(NDSlice(*req))
            reads.append(describe_result(r))
        except Exception as e:
            reads.append(describe_exc(e))
    res["reads"] = reads
    blocks = []
    for blk, req in cmd.get("blocks", []):
        NBYTES.clear()
        try:
            if req is None:
                r = adapter.read_block(NDBlock(*blk))
            else:
                r = adapter.read_block(NDBlock(*blk), NDSlice(*req))
            blocks.append(describe_result(r))
        except Exception as e:
            blocks.append(describe_exc(e))
    res["blocks"] = blocks
    return res


while True:
    cmd = recv()
    if cmd is None:
        break
    try:
        send(handle(cmd))
    except Exception:
        send({"fatal": traceback.format_exc()})
