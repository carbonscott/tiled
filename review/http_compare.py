"""Register HDF5 datasets with slice/squeeze parameters and hit the HTTP endpoints.

python -I http_compare.py <datadir> <out.pkl>
Writes {(node, url, accept): (status, content_type, body_bytes)} for comparison across trees.
"""

import pickle
import sys
import warnings

warnings.simplefilter("ignore")

import h5py  # noqa: E402
import numpy  # noqa: E402

from tiled.adapters.hdf5 import HDF5ArrayAdapter  # noqa: E402
from tiled.catalog import in_memory  # noqa: E402
from tiled.client import Context, from_context  # noqa: E402
from tiled.server.app import build_app  # noqa: E402
from tiled.structures.core import StructureFamily  # noqa: E402
from tiled.structures.data_source import Asset, DataSource, Management  # noqa: E402
from tiled.utils import ensure_uri  # noqa: E402

datadir, outpath, storage = sys.argv[1], sys.argv[2], sys.argv[3]


def mkfile(name, data, **kw):
    p = f"{datadir}/{name}.h5"
    with h5py.File(p, "w") as f:
        f.create_dataset("x", data=data, **kw)
    return ensure_uri(p)


files = {
    "scalar": mkfile("scalar", numpy.int64(42)),
    "vec10": mkfile("vec10", numpy.arange(10, dtype="int32")),
    "m45": mkfile("m45", numpy.arange(20, dtype="float64").reshape(4, 5)),
    "m82": mkfile("m82", numpy.arange(16, dtype="int16").reshape(8, 2)),
    "m82c": mkfile("m82c", numpy.arange(16, dtype="int16").reshape(8, 2), chunks=(4, 2)),
    "t151": mkfile("t151", numpy.arange(15, dtype="uint8").reshape(1, 5, 3)),
}

nodes = {
    # name: (file, parameters)
    "scalar_sq": ("scalar", {"dataset": "x", "squeeze": True}),
    "scalar_nosq": ("scalar", {"dataset": "x"}),
    "vec_int": ("vec10", {"dataset": "x", "slice": "3"}),
    "vec_rev": ("vec10", {"dataset": "x", "slice": "::-1"}),
    "m45_row_sq": ("m45", {"dataset": "x", "slice": "2:3", "squeeze": True}),
    "m45_col": ("m45", {"dataset": "x", "slice": ":,4"}),
    "m45_rev": ("m45", {"dataset": "x", "slice": "::-1,1:4"}),
    "m82": ("m82", {"dataset": "x"}),
    "m82c": ("m82c", {"dataset": "x"}),
    "t151_sq": ("t151", {"dataset": "x", "squeeze": True}),
    "t151_sq_rev": ("t151", {"dataset": "x", "slice": ":,::-2", "squeeze": True}),
    "t151_cell_sq": ("t151", {"dataset": "x", "slice": "0,4:5,2", "squeeze": True}),
}

requests = {
    "scalar_sq": [("full", None), ("block", ""), ("zarr2", "0"), ("zarr3", "0")],
    "scalar_nosq": [("full", None), ("full", "0"), ("block", "0"), ("zarr2", "0"), ("zarr3", "0")],
    "vec_int": [("full", None), ("block", ""), ("zarr2", "0"), ("zarr3", "0")],
    "vec_rev": [("full", None), ("full", "-3::-1"), ("full", "::-3"), ("full", "-11:2:-1"), ("full", "20"), ("full", "-11"), ("block", "0"), ("zarr2", "0"), ("zarr3", "0")],
    "m45_row_sq": [("full", None), ("full", "::-2"), ("full", "-9::-1"), ("full", "7"), ("block", "0"), ("zarr2", "0")],
    "m45_col": [("full", None), ("full", "1::-1"), ("full", "-1"), ("block", "0")],
    "m45_rev": [("full", None), ("full", "-9:1:-1,::-1"), ("full", "0,0"), ("full", "1:3,-1"), ("full", "4,0"), ("block", "0,0"), ("zarr2", "0.0"), ("zarr3", "0/0")],
    "m82": [("full", "2:2"), ("full", "3:5:-1"), ("full", ":,1:1"), ("full", ":,0:1:-1"), ("full", "-9:2:-1,::-1"), ("full", "::-1,-3::-1"), ("full", "8"), ("full", "-9"), ("full", "0,0,0"), ("block", "0,0"), ("block", "1,0"), ("zarr2", "0.0"), ("zarr2", "1.0"), ("zarr2", "5.0")],
    "m82c": [("full", "-9:2:-1,::-1"), ("full", "::-1,-3::-1"), ("block", "0,0"), ("block", "1,0"), ("block", "2,0"), ("zarr2", "0.0"), ("zarr2", "1.0"), ("zarr2", "5.0"), ("zarr3", "1/0")],
    "t151_sq": [("full", None), ("full", "::-1,-4::-1"), ("block", "0,0"), ("zarr2", "0.0")],
    "t151_sq_rev": [("full", None), ("full", "::-1"), ("block", "0,0")],
    "t151_cell_sq": [("full", None), ("block", ""), ("zarr2", "0"), ("zarr3", "0")],
}
ACCEPTS = ["application/octet-stream", "application/json", "text/csv"]

tree = in_memory(writable_storage=storage, readable_storage=[datadir])
out = {}
with Context.from_app(build_app(tree)) as context:
    client = from_context(context)
    http = context.http_client
    for name, (fkey, params) in nodes.items():
        uri = files[fkey]
        structure = HDF5ArrayAdapter.from_uris(uri, **params).structure()
        client.new(
            structure_family=StructureFamily.array,
            data_sources=[
                DataSource(
                    mimetype="application/x-hdf5",
                    assets=[Asset(data_uri=uri, is_directory=False, parameter="data_uris")],
                    structure_family=StructureFamily.array,
                    structure=structure,
                    parameters=params,
                    management=Management.external,
                )
            ],
            key=name,
        )
        out[(name, "structure")] = (tuple(structure.shape), tuple(map(tuple, structure.chunks)))
        for kind, arg in requests[name]:
            if kind == "full":
                url = f"/api/v1/array/full/{name}" + ("" if arg is None else f"?slice={arg}")
                accepts = ACCEPTS
            elif kind == "block":
                url = f"/api/v1/array/block/{name}?block={arg}"
                accepts = ACCEPTS
            elif kind == "zarr2":
                url = f"/zarr/v2/{name}/{arg}"
                accepts = [None]
            else:
                url = f"/zarr/v3/{name}/c/{arg}"
                accepts = [None]
            for acc in accepts:
                headers = {"Accept": acc} if acc else {}
                try:
                    r = http.get(url, headers=headers)
                    out[(name, url, acc)] = (r.status_code, r.headers.get("content-type"), r.content[:2000])
                except Exception as e:
                    out[(name, url, acc)] = ("EXC", type(e).__name__, str(e)[:300].encode())
        # also the python client read
        try:
            a = client[name].read()
            out[(name, "client.read")] = ("ok", numpy.asarray(a).dtype.str, numpy.asarray(a).shape, numpy.asarray(a).tobytes())
        except Exception as e:
            out[(name, "client.read")] = ("EXC", type(e).__name__, str(e)[:300])
        # zarr v3 metadata (fill_value read for 0-d)
        try:
            r = http.get(f"/zarr/v3/{name}/zarr.json")
            out[(name, "zarr.json")] = (r.status_code, r.content[:2000])
        except Exception as e:
            out[(name, "zarr.json")] = ("EXC", type(e).__name__, str(e)[:300].encode())

with open(outpath, "wb") as f:
    pickle.dump(out, f)
print("wrote", len(out))
