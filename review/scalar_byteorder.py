import sys, warnings
warnings.simplefilter("ignore")
import h5py, numpy
from tiled.adapters.hdf5 import HDF5ArrayAdapter
from tiled.ndslice import NDSlice, NDBlock
from tiled.utils import ensure_uri
d = sys.argv[1]
p = d + "/be.h5"
with h5py.File(p, "w") as f:
    f.create_dataset("scalar", data=numpy.array(258, dtype=">i2"))
    f.create_dataset("vec", data=numpy.arange(256, 266, dtype=">i2"))
    f.create_dataset("m", data=numpy.arange(256, 268, dtype=">f8").reshape(3, 4))
uri = ensure_uri(p)
for ds, params in [("scalar", {"squeeze": True}), ("scalar", {}), ("vec", {"slice": "2"}), ("vec", {"slice": "2:3", "squeeze": True}), ("m", {"slice": "1,2"}), ("m", {"slice": "1:2,2:3", "squeeze": True})]:
    a = HDF5ArrayAdapter.from_uris(uri, dataset=ds, **params)
    st = a.structure()
    r = a.read()
    print(f"{ds:6} {str(params):36} structure dtype {st.data_type.to_numpy_dtype().str} shape {st.shape} | read() -> {type(r).__name__} dtype {numpy.asarray(r).dtype.str} value {r!r} bytes {numpy.asarray(r).tobytes().hex()}")
