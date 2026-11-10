import sys, types, warnings
warnings.simplefilter("ignore")
import h5py, numpy
from tiled.adapters.hdf5 import HDF5ArrayAdapter
from tiled.structures.array import ArrayStructure
from tiled.structures.data_source import Asset, DataSource
from tiled.utils import ensure_uri
p = sys.argv[1] + "/i0.h5"
with h5py.File(p, "w") as f:
    f.create_dataset("x", data=numpy.arange(12, dtype="int32").reshape(4, 3))
uri = ensure_uri(p)
st = ArrayStructure.from_array(numpy.zeros((4, 3), dtype="int32"))  # structure as stored when slice=0 (int) was ignored
ds = DataSource(structure_family="array", structure=st, mimetype="application/x-hdf5",
                parameters={"dataset": "x", "slice": 0}, assets=[Asset(data_uri=uri, is_directory=False, parameter="data_uris")], management="external")
a = HDF5ArrayAdapter.from_catalog(ds, types.SimpleNamespace(metadata_={}, specs=[]), dataset="x", slice=0)
try:
    print("from_catalog(slice=0 int, structure (4,3)).read() ->", a.read().tolist())
except Exception as e:
    print("from_catalog(slice=0 int, structure (4,3)).read() raised", type(e).__name__, e)
