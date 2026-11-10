"""Minimal repro: a dataset registered with `squeeze` down to 0-d loses its dtype on read.

Run with either tree's interpreter:  python -I repro_squeeze_dtype.py <empty dir>
"""

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

d = sys.argv[1]
path = f"{d}/f.h5"
with h5py.File(path, "w") as f:
    f.create_dataset("be", data=numpy.array([256, 258, 260], dtype=">i2"))  # big-endian
    f.create_dataset("s5", data=numpy.array([b"hello", b"ab", b"xyz"], dtype="S5"))
uri = ensure_uri(path)

tree = in_memory(writable_storage=f"{d}/storage", readable_storage=[d])
with Context.from_app(build_app(tree)) as context:
    client = from_context(context)
    for name in ["be", "s5"]:
        params = {"dataset": name, "slice": "1:2", "squeeze": True}
        adapter = HDF5ArrayAdapter.from_uris(uri, **params)
        r = adapter.read()
        print(f"[{name}] structure dtype {adapter.structure().data_type.to_numpy_dtype().str} shape {adapter.structure().shape};"
              f" adapter.read() -> {type(r).__name__} dtype {numpy.asarray(r).dtype.str}")
        client.new(
            structure_family=StructureFamily.array,
            data_sources=[
                DataSource(
                    mimetype="application/x-hdf5",
                    assets=[Asset(data_uri=uri, is_directory=False, parameter="data_uris")],
                    structure_family=StructureFamily.array,
                    structure=adapter.structure(),
                    parameters=params,
                    management=Management.external,
                )
            ],
            key=name,
        )
        print(f"[{name}] client.read()          -> {client[name].read()!r}")
        try:
            print(f"[{name}] client.read_block(()) -> {client[name].read_block(())!r}")
        except Exception as e:
            print(f"[{name}] client.read_block(()) -> raised {type(e).__name__}: {e}")
        r = context.http_client.get(f"/zarr/v2/{name}/0")
        print(f"[{name}] GET /zarr/v2/{name}/0 -> {r.status_code}, last bytes {r.content[16:].hex()}")
