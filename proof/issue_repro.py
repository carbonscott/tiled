"""Count the bytes h5py returns while HDF5ArrayAdapter serves a few requests."""

import tempfile
from pathlib import Path

import h5py
import numpy

from tiled.adapters.hdf5 import HDF5ArrayAdapter
from tiled.ndslice import NDSlice
from tiled.utils import ensure_uri

nbytes = []
getitem = h5py.Dataset.__getitem__


def counting_getitem(self, *args, **kwargs):
    out = getitem(self, *args, **kwargs)
    nbytes.append(numpy.asarray(out).nbytes)
    return out


h5py.Dataset.__getitem__ = counting_getitem

path = Path(tempfile.mkdtemp()) / "stack.h5"
data = numpy.arange(1000 * 256 * 512, dtype="float64").reshape(1000, 256, 512)
with h5py.File(path, "w") as f:
    f.create_dataset("x", data=data)  # contiguous: 1000 entities x 1 MiB

uri = ensure_uri(path)
cases = [
    ("whole dataset, 10x10 corner of entity 5", None, NDSlice(5, slice(0, 10), slice(0, 10))),
    ("registered row 5, its 10x10 corner", "5", NDSlice(slice(0, 10), slice(0, 10))),
    ("whole dataset, entity 5 reversed", None, NDSlice(5, slice(None, None, -1))),
]
print(f"{'case':42} {'requested':>12} {'h5py read':>14}")
for name, registered, request in cases:
    adapter = HDF5ArrayAdapter.from_uris(uri, dataset="x", slice=registered)
    nbytes.clear()
    out = adapter.read(request)
    print(f"{name:42} {out.nbytes:>12,} {sum(nbytes):>14,}")
