import sys, warnings
warnings.simplefilter("ignore")
import numpy, zarr
from tiled.adapters.zarr import ZarrArrayAdapter
from tiled.ndslice import NDSlice, NDBlock
from tiled.structures.array import ArrayStructure
d = sys.argv[1]
data = numpy.arange(10, dtype="int32")
z = zarr.open_array(d + "/z.zarr", mode="w", shape=(10,), chunks=(4,), dtype="int32")
z[:] = data
st = ArrayStructure.from_array(data)
st = ArrayStructure(data_type=st.data_type, shape=(10,), chunks=((4, 4, 2),))
a = ZarrArrayAdapter(z, st)
for s in [NDSlice(slice(None, None, -1)), NDSlice(slice(5, None, -2)), NDSlice(slice(-11, 2, -1)), NDSlice(slice(None, None, -3)), NDSlice(-1)]:
    exp = data[tuple(s)]
    try:
        got = a.read(s)
        print("read", s, "->", list(numpy.atleast_1d(got)), "OK" if numpy.array_equal(got, exp) else f"WRONG (expected {list(numpy.atleast_1d(exp))})")
    except Exception as e:
        print("read", s, "-> raised", type(e).__name__, str(e)[:100])
for b, s in [((0,), NDSlice(slice(None, None, -1))), ((1,), NDSlice(slice(None, None, -1)))]:
    bs = NDBlock(*b).slice_from_chunks(st.chunks)
    exp = data[tuple(bs)][tuple(s)]
    try:
        got = a.read_block(NDBlock(*b), s)
        print("read_block", b, s, "->", list(got), "OK" if numpy.array_equal(got, exp) else f"WRONG (expected {list(exp)})")
    except Exception as e:
        print("read_block", b, s, "-> raised", type(e).__name__, str(e)[:100])
