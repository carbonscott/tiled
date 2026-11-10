"""Big-endian 0-d registered datasets over HTTP: /array/full, /array/block, zarr v2/v3, client reads.

python -I http_byteorder.py <datadir> <storage>
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

datadir, storage = sys.argv[1], sys.argv[2]
p = f"{datadir}/be.h5"
with h5py.File(p, "w") as f:
    f.create_dataset("vec", data=numpy.arange(256, 266, dtype=">i2"))
    f.create_dataset("m", data=numpy.arange(256, 268, dtype=">f8").reshape(3, 4))
    f.create_dataset("s5", data=numpy.array([b"hello", b"ab", b"xyz"], dtype="S5"))
    f.create_dataset("vs", data=["hello", "ab", "xyz"], dtype=h5py.string_dtype())
uri = ensure_uri(p)

nodes = {
    "vec_squeezed": {"dataset": "vec", "slice": "2:3", "squeeze": True},  # registered value 258
    "vec_int": {"dataset": "vec", "slice": "2"},  # registered value 258
    "m_squeezed": {"dataset": "m", "slice": "1:2,2:3", "squeeze": True},  # registered value 262.0
    "s5_squeezed": {"dataset": "s5", "slice": "1:2", "squeeze": True},  # registered value b"ab" (S5)
    "s5_int": {"dataset": "s5", "slice": "1"},
    "vs_squeezed": {"dataset": "vs", "slice": "1:2", "squeeze": True},
}
tree = in_memory(writable_storage=storage, readable_storage=[datadir])
with Context.from_app(build_app(tree)) as context:
    client = from_context(context)
    http = context.http_client
    for name, params in nodes.items():
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
        dt = structure.data_type.to_numpy_dtype()
        print(f"--- {name} {params} structure dtype={dt.str} shape={structure.shape}")
        def get(url, **kw):
            try:
                return http.get(url, **kw)
            except Exception as e:
                print(f"  {url:40} raised {type(e).__name__}: {str(e)[:80]}")
                return None
        for url in [f"/api/v1/array/full/{name}", f"/api/v1/array/block/{name}?block="]:
            r = get(url, headers={"Accept": "application/octet-stream"})
            if r is not None:
                try:
                    val = numpy.frombuffer(r.content, dtype=dt) if r.status_code == 200 else None
                except Exception as e:
                    val = f"<frombuffer failed: {e}>"
                print(f"  {url:40} {r.status_code} bytes={r.content.hex()} decoded-with-structure-dtype={val}")
        for url in [f"/zarr/v2/{name}/0", f"/zarr/v3/{name}/c/0"]:
            r = get(url)
            if r is not None:
                print(f"  {url:40} {r.status_code} bytes={r.content.hex()}")
        za = get(f"/zarr/v2/{name}/.zarray")
        if za is not None:
            print(f"  .zarray {za.status_code} {za.content[:200]}")
        c = client[name]
        for label, fn in [("client.read()", lambda: c.read()), ("client[()]", lambda: c[()]), ("client.read_block(())", lambda: c.read_block(()))]:
            try:
                v = fn()
                print(f"  {label:24} -> {v!r}")
            except Exception as e:
                print(f"  {label:24} -> raised {type(e).__name__}: {str(e)[:120]}")
        try:
            import zarr  # noqa

            from tiled.client.utils import get_asset_filepaths  # noqa
        except Exception:
            pass
