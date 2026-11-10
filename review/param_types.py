import sys, types, warnings
warnings.simplefilter("ignore")
import h5py, numpy
from tiled.adapters.hdf5 import HDF5ArrayAdapter
from tiled.structures.array import ArrayStructure
from tiled.structures.data_source import Asset, DataSource
from tiled.utils import ensure_uri
from tiled.ndslice import NDSlice
p = sys.argv[1] + "/pt.h5"
data = numpy.arange(12, dtype="int32").reshape(4, 3)
with h5py.File(p, "w") as f:
    f.create_dataset("x", data=data)
uri = ensure_uri(p)
for sl in [0, 2, [1, 2], "0", ""]:
    try:
        a = HDF5ArrayAdapter.from_uris(uri, dataset="x", slice=sl)
        print(f"from_uris slice={sl!r:8} structure {a.structure().shape} read -> {a.read().tolist()}")
    except Exception as e:
        print(f"from_uris slice={sl!r:8} raised {type(e).__name__}: {str(e)[:80]}")
# compose_slices with an unexpanded reversed left slice whose stop is negative
arr = numpy.arange(10)
left = NDSlice(slice(5, -3, -1))
try:
    comp = left[NDSlice(slice(None))]
    print("NDSlice(slice(5,-3,-1))[NDSlice(slice(None))] ->", comp, "selects", arr[tuple(comp)].tolist(), "; numpy arr[5:-3:-1][:] =", arr[5:-3:-1][:].tolist())
except Exception as e:
    print("NDSlice(slice(5,-3,-1))[NDSlice(slice(None))] raised", type(e).__name__, str(e)[:80])
