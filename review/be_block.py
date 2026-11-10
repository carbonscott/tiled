import sys, warnings
warnings.simplefilter("ignore")
import h5py, numpy
from tiled.adapters.hdf5 import HDF5ArrayAdapter
from tiled.ndslice import NDSlice, NDBlock
from tiled.utils import ensure_uri
p = sys.argv[1] + "/be2.h5"
with h5py.File(p, "w") as f:
    f.create_dataset("m", data=numpy.arange(256, 268, dtype=">f8").reshape(3, 4))
    f.create_dataset("mc", data=numpy.arange(256, 268, dtype=">f8").reshape(3, 4), chunks=(1, 2))
for ds in ["m", "mc"]:
    for params in [{}, {"slice": "1:3"}, {"slice": "1:2", "squeeze": True}]:
        a = HDF5ArrayAdapter.from_uris(ensure_uri(p), dataset=ds, **params)
        sh = a.structure().shape
        req = NDSlice(*([0] * len(sh)))
        r1 = a.read(req)
        r2 = a.read_block(NDBlock(*([0] * len(sh))), req)
        print(ds, params, "structure", a.structure().data_type.to_numpy_dtype().str, sh, "| read(all-int)", type(r1).__name__, numpy.asarray(r1).dtype.str, "| read_block(all-int)", type(r2).__name__, numpy.asarray(r2).dtype.str)
