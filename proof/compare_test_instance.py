#!/usr/bin/env python3
"""Serve test-instance datasets from their SOURCE HDF5 files with tiled's stock
HDF5ArrayAdapter, and prove they equal what the Tiled test instance serves.

The Tiled test instance (https://lcls-data-portal.slac.stanford.edu/tiled-test) holds
UPLOADED copies of these arrays. This script registers the same arrays into a LOCAL tiled
server as EXTERNAL data sources pointing at the original files on disk, so the local server
reads them through the stock `HDF5ArrayAdapter` -- including its `slice` parameter, which
selects one entity's row of a stacked dataset. It then reads the same head / middle / tail
slices from both servers and compares them element for element.

Inputs
------
* the JSON written by the survey (STATE/testinstance_datasets.json): one entry per
  artifact with dataset_key, entity_key, artifact, shape, dtype, source_file, h5_dataset,
  row (int = row of a stacked dataset, null = the whole dataset), source_layout, slices.
* a local tiled server that may READ the source files, e.g.

      export LOCAL_TILED_API_KEY=<a throwaway key, never printed>
      tiled serve catalog --temp --api-key "$LOCAL_TILED_API_KEY" --port 8011 \\
          -r /sdf/data/lcls/ds/prj/prjmaiqmag01/scratch/cwang31/tilewright-bench

  The `-r` root is compared to the asset path WITHOUT resolving symlinks, so pass the
  same prefix the JSON's source_file values use.
* the test instance URL and the read-only key in TILED_API_KEY
  (`export TILED_API_KEY=$(cat <key file>)`; never on a command line).

What it does, per artifact
--------------------------
1. Opens the source with h5py (metadata only) and checks it against the JSON: the
   dataset exists, its shape (minus axis 0 when `row` is set) and dtype equal the
   entry's, the row is in range, the chunk shape equals source_layout.chunks.
2. Registers it into the local server at the SAME path as on the test instance,
   <dataset_key>/<entity_key>/<artifact>, as
       mimetype   application/x-hdf5
       asset      file://<source_file>, parameter "data_uris", num 0
       parameters {"dataset": h5_dataset, "slice": "<row>"}   ("slice" omitted when row is null)
       structure  shape/dtype of the registered selection; chunks = the source's HDF5
                  chunk shape on the kept axes (the whole axis when contiguous).
   An existing node with the same parameters and asset is reused; a different one is an
   error (start from a fresh `--temp` catalog).
3. Test instance: records the HTTP status of the node's metadata and of a one-element
   read, checks the entity's TileWright locators (path_/dataset_/index_<artifact>)
   against the JSON, and checks the node's shape and dtype.
4. Reads each slice from the local server and from the test instance with the Python
   client, and compares: `yes` = byte-identical, `yes(values)` = equal values (NaN==NaN)
   but not byte-identical, `NO` otherwise. A third witness, a direct h5py read of the
   same selection from the source file, is compared with the local server (column
   `h5py`), so a mismatch says which side is wrong. `nonzero` counts the nonzero
   elements of the test-instance slice, so an all-zero match is visible as such.

Prints a table (dataset key | array path | slice | shape | dtype | equal | h5py |
nonzero | test-instance URL) and a tally. Exit status is 0 only when every compared slice
is equal, nothing errored, and at least --require-datasets datasets matched on every
slice; otherwise 1.

Needs only tiled's Python client, h5py and numpy (hdf5plugin if present); it never
imports TileWright, so what serves the local arrays is the stock adapter of whatever
tiled build the local server runs.

Negative control: `--perturb <dataset_key>` flips one bit of the test-instance array of
that dataset before comparing; the run must then report NO for it and exit 1.

Pre-flight: `--ti-only` needs no local server. It records the test instance's HTTP
statuses and locators for every node and reads every slice from it (equal = `read`,
plus `nonzero`), exiting 0 only when every node answered 200 and every slice read with
the expected shape. Run it first on the node that will do the comparison.

Real run (on a Slurm node, inside the campaign allocation):

    export TILED_API_KEY=$(cat .../_tiledtest/tt-readonly.key)
    export LOCAL_TILED_API_KEY=$(cat <throwaway key file>)
    python compare_test_instance.py STATE/testinstance_datasets.json --ti-only
    tiled serve catalog --temp --api-key "$LOCAL_TILED_API_KEY" --port 8011 \\
        -r /sdf/data/lcls/ds/prj/prjmaiqmag01/scratch/cwang31/tilewright-bench &
    python compare_test_instance.py STATE/testinstance_datasets.json \\
        --local-url http://127.0.0.1:8011 --out results.json
"""
import argparse
import json
import math
import os
import sys
import time
import traceback
from urllib.parse import quote

import h5py
import numpy as np

try:
    import hdf5plugin  # noqa: F401  registers LZ4/Bitshuffle/... filters h5py lacks
except ImportError:
    pass

import tiled
from tiled.client import from_uri
from tiled.ndslice import NDSlice
from tiled.structures.array import ArrayStructure, BuiltinDtype
from tiled.structures.core import StructureFamily
from tiled.structures.data_source import Asset, DataSource, Management
from tiled.utils import ensure_uri

TEST_INSTANCE = "https://lcls-data-portal.slac.stanford.edu/tiled-test"
POSITIONS = ("head", "middle", "tail")


# ----------------------------------------------------------------------------- helpers
def split_axis(n, c):
    """Chunk sizes along one axis of length n for a chunk length c."""
    if n == 0:
        return (0,)
    c = max(1, min(int(c), int(n)))
    sizes = [c] * (n // c)
    if n % c:
        sizes.append(n % c)
    return tuple(sizes)


def http_status(exc):
    """The HTTP status carried by a tiled/httpx error, else None."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


def short_err(exc):
    s = f"{type(exc).__name__}: {exc}"
    return s.splitlines()[0][:160] if s else type(exc).__name__


def same(a, b):
    """'yes' byte-identical, 'yes(values)' equal values only, else 'NO(...)'."""
    if a.shape != b.shape:
        return f"NO(shape {a.shape}!={b.shape})"
    if a.dtype != b.dtype:
        return f"NO(dtype {a.dtype}!={b.dtype})"
    if a.tobytes() == b.tobytes():
        return "yes"
    if np.array_equal(a, b, equal_nan=a.dtype.kind in "fc"):
        return "yes(values)"
    ndiff = int(np.count_nonzero(a != b))
    return f"NO({ndiff} differ)"


def is_equal(verdict):
    """A passing slice: equal ('yes', 'yes(values)'), or 'read' under --ti-only."""
    return verdict.startswith("yes") or verdict == "read"


def flip_one_bit(a):
    """A copy of `a` with the lowest bit of its first element flipped (negative control)."""
    b = np.array(a, copy=True)
    if b.size:
        u = b.reshape(-1).view(np.dtype(f"u{b.dtype.itemsize}"))
        u[0] ^= 1
    return b


def compact(s):
    return s.replace(" ", "")


# ------------------------------------------------------------------- source / structure
def inspect_source(e):
    """Check the source file against the entry; return (ArrayStructure, notes)."""
    notes = []
    src = e["source_file"]
    row = e["row"]
    if not os.path.exists(src):
        raise FileNotFoundError(f"source not found: {src}")
    if e.get("file_size") is not None and os.path.getsize(src) != e["file_size"]:
        notes.append(f"file size {os.path.getsize(src)} != survey {e['file_size']}")
    with h5py.File(src, "r") as f:
        if e["h5_dataset"] not in f:
            raise KeyError(f"{e['h5_dataset']} not in {src}")
        d = f[e["h5_dataset"]]
        shape = tuple(d.shape[1:] if row is not None else d.shape)
        if row is not None and not (0 <= row < d.shape[0]):
            raise IndexError(f"row {row} out of range for {d.shape}")
        if list(shape) != list(e["shape"]):
            raise ValueError(f"source selection shape {shape} != JSON {tuple(e['shape'])}")
        if d.dtype != np.dtype(e["dtype"]):
            raise ValueError(f"source dtype {d.dtype} != JSON {e['dtype']}")
        want_chunks = (e.get("source_layout") or {}).get("chunks", "unset")
        got_chunks = list(d.chunks) if d.chunks else None
        if want_chunks != "unset" and want_chunks != got_chunks:
            raise ValueError(f"source chunks {got_chunks} != JSON {want_chunks}")
        src_chunks = d.chunks or d.shape
        kept = src_chunks[1:] if row is not None else src_chunks
        chunks = tuple(split_axis(n, c) for n, c in zip(shape, kept))
        structure = ArrayStructure(
            data_type=BuiltinDtype.from_numpy_dtype(d.dtype), chunks=chunks, shape=shape
        )
    return structure, notes


def read_h5py(e, nd):
    """Direct h5py read of the same selection: ds[(row,) + slice]."""
    with h5py.File(e["source_file"], "r") as f:
        d = f[e["h5_dataset"]]
        key = ((e["row"],) if e["row"] is not None else ()) + tuple(nd)
        return np.asarray(d[key])


# ----------------------------------------------------------------------- local server
def child(node, key, create):
    if key in node:
        return node[key]
    if not create:
        raise KeyError(key)
    return node.create_container(key=key)


def register_local(local, e, structure):
    """Register one artifact as an external HDF5 data source; return 'new' or 'reused'."""
    params = {"dataset": e["h5_dataset"]}
    if e["row"] is not None:
        params["slice"] = str(e["row"])
    uri = ensure_uri(e["source_file"])
    ent = child(child(local, e["dataset_key"], True), e["entity_key"], True)
    if e["artifact"] in ent:
        (ds,) = ent[e["artifact"]].data_sources()
        got = (ds.mimetype, dict(ds.parameters), [a.data_uri for a in ds.assets])
        want = ("application/x-hdf5", params, [uri])
        if got != want:
            raise RuntimeError(f"local node exists with a different source: {got} != {want}")
        return "reused"
    ent.new(
        StructureFamily.array,
        [
            DataSource(
                structure_family=StructureFamily.array,
                structure=structure,
                mimetype="application/x-hdf5",
                parameters=params,
                management=Management.external,
                assets=[Asset(data_uri=uri, is_directory=False, parameter="data_uris", num=0)],
            )
        ],
        key=e["artifact"],
        metadata={"source_file": e["source_file"], "h5_dataset": e["h5_dataset"],
                  "row": e["row"], "test_instance_path": e["test_instance_path"]},
    )
    return "new"


def prepare_local(local, e, row, verbose):
    """Check the source, register it, return the local node (None on error, noted in row)."""
    try:
        structure, notes = inspect_source(e)
        row["registered"] = register_local(local, e, structure)
        row["structure_chunks"] = [len(c) for c in structure.chunks]
        row["notes"] = notes
        lnode = local[e["dataset_key"]][e["entity_key"]][e["artifact"]]
        if tuple(lnode.shape) != tuple(e["shape"]) or lnode.dtype != np.dtype(e["dtype"]):
            raise ValueError(f"local node {lnode.shape} {lnode.dtype} != JSON")
        return lnode
    except Exception as exc:
        row["local_error"] = short_err(exc)
        if verbose:
            traceback.print_exc()
        return None


# ---------------------------------------------------------------------- test instance
def ti_probe(ti, e):
    """HTTP statuses of metadata + a one-element read, the locator check, the node."""
    out = {"meta_status": None, "tiny_status": None, "locators": None, "node": None}
    path = "/".join(quote(p, safe="") for p in
                    (e["dataset_key"], e["entity_key"], e["artifact"]))
    http = ti.context.http_client
    try:
        r = http.get(f"{ti.uri.split('/metadata/')[0]}/metadata/{path}")
        out["meta_status"] = r.status_code
        tiny = ",".join("0:1" for _ in e["shape"]) or ""
        r = http.get(f"{ti.uri.split('/metadata/')[0]}/array/full/{path}",
                     params={"slice": tiny} if tiny else {},
                     headers={"Accept": "application/octet-stream"})
        out["tiny_status"] = r.status_code
    except Exception as exc:  # network-level failure
        out["probe_error"] = short_err(exc)
    try:
        ent = ti[e["dataset_key"]][e["entity_key"]]
        meta = dict(ent.metadata)
        a = e["artifact"]
        if f"path_{a}" in meta and f"dataset_{a}" in meta:
            idx = meta.get(f"index_{a}")
            idx = None if idx is None or (isinstance(idx, float) and math.isnan(idx)) else int(idx)
            got = (meta[f"path_{a}"], meta[f"dataset_{a}"], idx)
            want = (e.get("source_file_relative", got[0]), e["h5_dataset"], e["row"])
            out["locators"] = "ok" if got == want else f"MISMATCH {got} != {want}"
        else:
            out["locators"] = "absent"
        out["node"] = ent[e["artifact"]]
    except Exception as exc:
        out["node_error"] = short_err(exc)
        out["node_status"] = http_status(exc)
    return out


# ------------------------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("json", help="STATE/testinstance_datasets.json")
    p.add_argument("--local-url", help="local tiled server, e.g. http://127.0.0.1:8011")
    p.add_argument("--local-key-env", default="LOCAL_TILED_API_KEY",
                   help="env var holding the local server's API key (default LOCAL_TILED_API_KEY)")
    p.add_argument("--ti-url", default=TEST_INSTANCE, help=f"test instance (default {TEST_INSTANCE})")
    p.add_argument("--ti-key-env", default="TILED_API_KEY",
                   help="env var holding the test instance's read-only key (default TILED_API_KEY)")
    p.add_argument("--only", action="append", default=[], metavar="DATASET_KEY",
                   help="compare only these dataset keys (repeatable)")
    p.add_argument("--source-override", action="append", default=[], metavar="KEY=PATH",
                   help="read DATASET_KEY's source from PATH instead (dry runs on a copied file)")
    p.add_argument("--perturb", action="append", default=[], metavar="DATASET_KEY",
                   help="negative control: corrupt the test-instance array of this dataset")
    p.add_argument("--require-datasets", type=int, default=5,
                   help="datasets that must match on every slice (default 5)")
    p.add_argument("--out", help="write per-slice results and HTTP statuses as JSON here")
    p.add_argument("--verbose", action="store_true", help="print tracebacks of local errors")
    p.add_argument("--ti-only", action="store_true",
                   help="pre-flight only: probe and read every slice from the test instance "
                        "(HTTP statuses, locators, shape/dtype, nonzero); no local server, no comparison")
    a = p.parse_args(argv)
    if not a.ti_only and not a.local_url:
        p.error("--local-url is required unless --ti-only")

    entries = json.load(open(a.json))
    if a.only:
        entries = [e for e in entries if e["dataset_key"] in a.only]
    overrides = dict(s.split("=", 1) for s in a.source_override)
    for e in entries:
        if e["dataset_key"] in overrides:
            e["source_file"] = overrides[e["dataset_key"]]
            e["file_size"] = None  # a copy; its size is checked by the caller
    if not entries:
        sys.exit("no entries selected")

    for env in ((a.ti_key_env,) if a.ti_only else (a.local_key_env, a.ti_key_env)):
        if not os.environ.get(env):
            sys.exit(f"environment variable {env} is not set (load it with export {env}=$(cat <file>))")

    t0 = time.time()
    print(f"tiled client {tiled.__version__}; h5py {h5py.__version__}; numpy {np.__version__}")
    local = None
    if not a.ti_only:
        local = from_uri(a.local_url, api_key=os.environ[a.local_key_env])
        print(f"local server   {a.local_url}  tiled {local.context.server_info.library_version}")
    ti, ti_error = None, None
    try:
        ti = from_uri(a.ti_url, api_key=os.environ[a.ti_key_env])
        print(f"test instance  {a.ti_url}  tiled {ti.context.server_info.library_version}")
    except Exception as exc:
        ti_error = (http_status(exc), short_err(exc))
        print(f"test instance  {a.ti_url}  UNREACHABLE: HTTP {ti_error[0]} {ti_error[1]}")
    print()

    results, preflight = [], []
    for e in entries:
        path = e["test_instance_path"]
        row = {"dataset_key": e["dataset_key"], "path": path, "row": e["row"]}
        # 1-2. source check + local registration
        lnode = None
        if a.ti_only:
            row["registered"] = "skipped(--ti-only)"
        else:
            lnode = prepare_local(local, e, row, a.verbose)
        # 3. test instance probe
        tnode = None
        if ti is not None:
            probe = ti_probe(ti, e)
            tnode = probe.pop("node")
            row.update(probe)
            if tnode is not None and (tuple(tnode.shape) != tuple(e["shape"])
                                      or tnode.dtype != np.dtype(e["dtype"])):
                row["ti_error"] = f"test-instance node {tnode.shape} {tnode.dtype} != JSON"
                tnode = None
        else:
            row["meta_status"] = row["tiny_status"] = ti_error[0]
            row["ti_error"] = ti_error[1]
        preflight.append(row)

        # 4. slices
        for pos in POSITIONS:
            s = e["slices"][pos]
            nd = NDSlice.from_numpy_str(s)
            exp_shape = nd.shape_after_slice(tuple(e["shape"]))
            url = f"{a.ti_url}/api/v1/array/full/{path}?slice={quote(compact(s), safe=':,')}"
            r = {"dataset_key": e["dataset_key"], "path": path, "pos": pos, "slice": compact(s),
                 "shape": "x".join(map(str, exp_shape)) or "()", "dtype": e["dtype"], "url": url,
                 "equal": "ERROR", "h5py": "-", "nonzero": "-"}
            try:
                if a.ti_only:
                    if tnode is None:
                        raise RuntimeError(f"test instance: {row.get('ti_error') or row.get('node_error')}")
                    tv = np.asarray(tnode.read(slice=nd))
                    r["nonzero"] = int(np.count_nonzero(tv))
                    r["equal"] = ("read" if tuple(tv.shape) == tuple(exp_shape)
                                  else f"NO(shape {tv.shape} != expected {exp_shape})")
                    results.append(r)
                    continue
                if lnode is None:
                    raise RuntimeError(f"local: {row.get('local_error')}")
                lv = np.asarray(lnode.read(slice=nd))
                hv = read_h5py(e, nd)
                r["h5py"] = same(lv, hv)
                if tnode is None:
                    raise RuntimeError(f"test instance: {row.get('ti_error') or row.get('node_error')}")
                tv = np.asarray(tnode.read(slice=nd))
                if e["dataset_key"] in a.perturb:
                    tv = flip_one_bit(tv)
                r["equal"] = same(lv, tv)
                r["nonzero"] = int(np.count_nonzero(tv))
                if tuple(tv.shape) != tuple(exp_shape):
                    r["equal"] = f"NO(shape {tv.shape} != expected {exp_shape})"
            except Exception as exc:
                r["error"] = short_err(exc)
            results.append(r)

    # --------------------------------------------------------------------- report
    print("PRE-FLIGHT (test instance HTTP status: metadata / one-element read; locators; local registration)")
    for row in preflight:
        print(f"  {row['path']}: meta={row.get('meta_status')} tiny={row.get('tiny_status')} "
              f"locators={row.get('locators')} local={row.get('registered', 'ERROR')}"
              + (f" row={row['row']}" if row["row"] is not None else " row=null")
              + "".join(f"\n      {k}: {row[k]}" for k in
                        ("local_error", "ti_error", "node_error", "probe_error", "notes") if row.get(k)))
    print()

    cols = [("dataset key", "dataset_key"), ("array path", "path"), ("slice", "slice"),
            ("shape", "shape"), ("dtype", "dtype"), ("equal", "equal"), ("h5py", "h5py"),
            ("nonzero", "nonzero"), ("test-instance URL", "url")]
    widths = [max(len(h), *(len(str(r[k])) for r in results)) for h, k in cols]
    line = lambda vals: "| " + " | ".join(str(v).ljust(w) for v, w in zip(vals, widths)) + " |"
    print(line([h for h, _ in cols]))
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for r in results:
        print(line([r[k] for _, k in cols]))
    errs = [r for r in results if "error" in r]
    for r in errs:
        print(f"  ERROR {r['path']} [{r['slice']}]: {r['error']}")

    n_eq = sum(is_equal(r["equal"]) for r in results)
    n_mis = sum(r["equal"].startswith("NO") for r in results)
    n_h5bad = sum(r["h5py"].startswith("NO") for r in results)
    by_ds = {}
    for r in results:
        by_ds.setdefault(r["dataset_key"], []).append(is_equal(r["equal"]))
    ds_ok = sorted(k for k, v in by_ds.items() if all(v))
    bad_http = [row["path"] for row in preflight
                if ti is not None and (row.get("meta_status") != 200 or row.get("tiny_status") != 200)]
    passed = (n_mis == 0 and not errs and n_h5bad == 0 and not bad_http
              and len(ds_ok) >= a.require_datasets)
    print()
    what = ("slices read from the test instance with the expected shape" if a.ti_only
            else "slices equal (local stock adapter == test instance)")
    print(f"{what}: {n_eq}/{len(results)}; "
          f"mismatches: {n_mis}; errors: {len(errs)}; local != direct h5py: {n_h5bad}")
    print(f"datasets {'read' if a.ti_only else 'equal'} on every slice: {len(ds_ok)}/{len(by_ds)} "
          f"(required >= {a.require_datasets}): {', '.join(ds_ok) or '-'}")
    if bad_http:
        print(f"test-instance HTTP status not 200 for: {', '.join(bad_http)}")
    mode = "test-instance pre-flight (--ti-only), NO comparison" if a.ti_only else "comparison"
    print(f"RESULT: {'PASS' if passed else 'FAIL'} [{mode}]   ({time.time() - t0:.1f} s)")

    if a.out:
        with open(a.out, "w") as fh:
            json.dump({"local_url": a.local_url, "ti_url": a.ti_url,
                       "local_tiled": local.context.server_info.library_version if local else None,
                       "ti_tiled": ti.context.server_info.library_version if ti else None,
                       "client_tiled": tiled.__version__, "perturb": a.perturb,
                       "preflight": preflight, "slices": results, "pass": passed},
                      fh, indent=1, default=str)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
