"""Differential property test: HDF5ArrayAdapter at head (421569c4) vs PR #2 (514dc33a) vs numpy.

Usage: python driver.py --examples N --seed S [--fail] [--out mismatches.jsonl]
"""

import argparse
import itertools
import json
import os
import pickle
import shutil
import struct
import subprocess
import sys
import tempfile
import warnings
from collections import Counter

import h5py
import numpy as np
from hypothesis import HealthCheck, given, seed, settings
from hypothesis import strategies as st

warnings.simplefilter("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
TREES = {
    "head": os.path.join(REVIEW, "tiled"),
    "pr2": os.path.join(REVIEW, "tiled-pr2"),
}


class Worker:
    def __init__(self, tree):
        py = os.path.join(tree, ".venv", "bin", "python")
        self.p = subprocess.Popen(
            [py, "-I", os.path.join(HERE, "worker.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=tree,
        )

    def call(self, cmd):
        b = pickle.dumps(cmd)
        self.p.stdin.write(struct.pack("<I", len(b)) + b)
        self.p.stdin.flush()
        (n,) = struct.unpack("<I", self.p.stdout.read(4))
        return pickle.loads(self.p.stdout.read(n))


WORKERS = {}


def workers():
    if not WORKERS:
        for k, t in TREES.items():
            WORKERS[k] = Worker(t)
    return WORKERS


TMP = tempfile.mkdtemp(prefix="hdf5review-", dir=os.environ.get("SCRATCH"))
COUNTER = itertools.count()

# ---------------------------------------------------------------- strategies

DTYPES = ["<i4", "<f8", "|u1", ">i2"]


@st.composite
def dataset_specs(draw):
    ndim = draw(st.integers(0, 4))
    nfiles = draw(st.sampled_from([1, 1, 1, 2, 3]))
    dim = st.sampled_from([0, 1, 1, 2, 3, 4, 5])
    trailing = tuple(draw(dim) for _ in range(max(ndim - 1, 0)))
    if ndim == 0:
        shapes = [()] * nfiles
    else:
        shapes = [(draw(dim),) + trailing for _ in range(nfiles)]
    storage = draw(st.sampled_from(["contiguous", "chunked", "gzip"]))
    chunks = None
    if ndim and storage != "contiguous":
        # chunk shape: common for all files, >= 1 in each dim
        chunks = tuple(
            draw(st.integers(1, max(1, max(s[i] for s in shapes)))) for i in range(ndim)
        )
    dtype = draw(st.sampled_from(DTYPES))
    return dict(ndim=ndim, shapes=shapes, storage=storage, chunks=chunks, dtype=dtype)


def write_files(spec):
    uris, arrays = [], []
    offset = 0
    for i, shape in enumerate(spec["shapes"]):
        n = int(np.prod(shape))
        data = (np.arange(offset, offset + n) % 120 + 1).astype(spec["dtype"]).reshape(shape)
        offset += n
        path = os.path.join(TMP, f"f{next(COUNTER)}.h5")
        with h5py.File(path, "w") as f:
            kw = {}
            if spec["chunks"] is not None:
                kw["chunks"] = spec["chunks"]
                kw["maxshape"] = (None,) * len(shape)
                if spec["storage"] == "gzip":
                    kw["compression"] = "gzip"
                # 0-length dims need resizable maxshape? h5py accepts chunks with 0 dims
            f.create_dataset("g/x", data=data, **kw)
        uris.append("file://localhost" + path)
        arrays.append(data)
    try:
        if all((not a.shape) or (0 in a.shape) for a in arrays):
            full = np.stack(arrays)
        else:
            full = np.concatenate(arrays, axis=0)
    except ValueError:
        full = None
    return uris, full


def one_dim_index(draw, n, allow_oob):
    kind = draw(st.sampled_from(["full", "int", "slice", "slice", "slice"]))
    lim = n + 2
    if kind == "full":
        return slice(None)
    if kind == "int":
        if n == 0 or (allow_oob and draw(st.integers(0, 9)) == 0):
            return draw(st.integers(-lim - 1, lim))
        return draw(st.integers(-n, n - 1))
    bound = st.one_of(st.none(), st.integers(-lim, lim))
    step = draw(st.sampled_from([None, 1, 2, 3, -1, -2, -3, 5, -7]))
    return slice(draw(bound), draw(bound), step)


def nd_index(draw, shape, allow_oob, allow_extra):
    idx = [one_dim_index(draw, n, allow_oob) for n in shape]
    if draw(st.integers(0, 3)) == 0:
        # an Ellipsis standing for a run of dims (those dims become full slices)
        pos = draw(st.integers(0, len(idx)))
        drop = draw(st.integers(0, len(idx) - pos))
        idx = idx[:pos] + [Ellipsis] + idx[pos + drop :]
    elif idx and draw(st.booleans()):
        # omit trailing dims
        idx = idx[: draw(st.integers(0, len(idx)))]
    if allow_extra and draw(st.integers(0, 15)) == 0:
        idx = idx + [0]
    return tuple(idx)


# ---------------------------------------------------------------- comparison

def numpy_eval(fn):
    try:
        r = fn()
        return ("ok", type(r).__name__, np.asarray(r), str(np.asarray(r).dtype), tuple(np.shape(r)))
    except Exception as e:
        return ("err", type(e).__name__, [c.__name__ for c in type(e).__mro__], str(e)[:300])


def same(a, b, check_type=True):
    if a[0] != b[0]:
        return False
    if a[0] == "err":
        return a[1] == b[1]
    if a[3] != b[3] or a[4] != b[4]:
        return False
    if not np.array_equal(a[2], b[2]):
        return False
    return True


def same_vs_numpy(t, n):
    """tiled result t vs numpy reference n: errors compare only as 'error' (types differ by design)."""
    if t[0] != n[0]:
        return False
    if t[0] == "err":
        return True
    return (
        t[4] == n[4]
        and np.dtype(t[3]).newbyteorder("=") == np.dtype(n[3]).newbyteorder("=")
        and np.array_equal(t[2], n[2])
    )


def short(r):
    if r[0] == "err":
        return f"err:{r[1]}:{r[3][:120]}"
    return f"ok:{r[1]}:{r[3]}:{r[4]}"


def fmt_idx(t):
    def f(s):
        if s is Ellipsis:
            return "..."
        if isinstance(s, slice):
            return f"{'' if s.start is None else s.start}:{'' if s.stop is None else s.stop}" + (
                "" if s.step is None else f":{s.step}"
            )
        return str(s)

    if t is None:
        return "None"
    return "(" + ",".join(f(s) for s in t) + ")"


def check_bytes(op, hr, pr, case, d, mode):
    if hr[0] != "ok" or mode not in ("uris", "catalog", "catalog_chunks"):
        return
    if case["spec"]["ndim"] == 0 or any(0 in s for s in case["spec"]["shapes"]):
        return  # scalar / empty files are read eagerly at construction
    nb = int(np.asarray(hr[2]).nbytes)
    STATS["bytes_checked"] += 1
    if hr[5] != nb:
        record(op + "_bytes", case, dict(d, head_bytes=hr[5], result_nbytes=nb, pr2_bytes=pr[5] if pr[0] == "ok" else None), False)


MISMATCHES = []
STATS = Counter()


def record(kind, case, detail, fail):
    entry = dict(kind=kind, **case, **detail)
    MISMATCHES.append(entry)
    if fail:
        raise AssertionError(json.dumps(entry, default=str, indent=1))


def run_case(data, fail):
    from tiled.ndslice import NDSlice  # head's, for to_numpy_str

    spec = data.draw(dataset_specs(), label="spec")
    uris, full = write_files(spec)
    reg = None
    if data.draw(st.integers(0, 4)) > 0:
        reg = nd_index(data.draw, (3,) * spec["ndim"] if full is None else full.shape, allow_oob=True, allow_extra=False)
    squeeze = data.draw(st.booleans(), label="squeeze")
    if reg is None:
        reg_param = None
    else:
        nds = NDSlice(*reg)  # noqa
        s = nds.to_numpy_str()
        try:
            rt = NDSlice.from_numpy_str(s)
        except Exception:
            rt = None
        reg_param = s if rt == nds else nds
    mode = data.draw(st.sampled_from(["uris", "uris", "catalog", "catalog_chunks", "grown", "reshape", "notready", "incompatible"]), label="mode")

    # numpy reference for the registered array
    def registered():
        a = full if reg is None else full[reg]
        return np.squeeze(a) if squeeze else a

    regd = numpy_eval(registered)
    cmd = dict(uris=uris, dataset="g/x", slice=reg_param, squeeze=squeeze, mode="uris" if mode == "uris" else "catalog")
    case = dict(spec=spec, full_shape=None if full is None else full.shape, reg=fmt_idx(reg), reg_param=str(reg_param), squeeze=squeeze, mode=mode)

    probe = workers()["head"].call(dict(cmd, requests=[], blocks=[]))
    if "fatal" in probe:
        record("fatal_head", case, dict(tb=probe["fatal"]), fail)
        return
    if probe["construct"][0] != "ok":
        # construction error: compare with pr2 and numpy
        pr = workers()["pr2"].call(dict(cmd, requests=[], blocks=[]))
        STATS["construct_err"] += 1
        if pr["construct"][0] != "err" or pr["construct"][1] != probe["construct"][1]:
            record("construct_differs", case, dict(head=str(probe["construct"]), pr2=str(pr["construct"])), fail)
        if regd[0] == "ok":
            record("construct_err_but_numpy_ok", case, dict(head=str(probe["construct"])), fail)
        return
    if regd[0] != "ok":
        record("construct_ok_but_numpy_err", case, dict(numpy=short(regd)), fail)
        return
    reg_arr = regd[2]
    shape, chunks, dt = probe["structure"]
    if mode == "catalog_chunks" and shape:
        new_chunks = []
        for n in shape:
            parts, left = [], n
            while left > 0:
                c = data.draw(st.integers(1, left))
                parts.append(c)
                left -= c
            new_chunks.append(tuple(parts) if parts else (0,))
        cmd["chunks"] = tuple(new_chunks)
        chunks = cmd["chunks"]
    if mode == "grown":
        if not shape or shape[0] == 0:
            mode = "catalog"
        else:
            k = data.draw(st.integers(1, shape[0]))
            new0 = shape[0] - k
            cmd["shape"] = (new0,) + tuple(shape[1:])
            # rebuild chunks along axis 0
            # simple: one chunk along axis 0 (or (0,) if empty)
            cmd["chunks"] = ((new0,) if new0 else (0,),) + tuple(chunks[1:])
            shape = cmd["shape"]
            chunks = cmd["chunks"]
            reg_arr = reg_arr[:new0]
    if mode == "reshape":
        size = int(np.prod(shape)) if shape else 1
        cands = [(size,), (1, size), (size, 1)] + ([(shape[0] // 2, 2 * int(np.prod(shape[1:])))] if shape and shape[0] % 2 == 0 and shape[0] else [])
        cands = [c for c in cands if tuple(c) != tuple(shape)]
        if not shape or not cands:
            mode = "catalog"
        else:
            new = tuple(data.draw(st.sampled_from(cands)))
            cmd["shape"] = new
            cmd["chunks"] = tuple((n,) for n in new)
            shape, chunks = new, cmd["chunks"]
            reg_arr = reg_arr.reshape(new)
    if mode in ("notready", "incompatible"):
        if not shape or (mode == "incompatible" and len(shape) < 2):
            mode = "catalog"
        else:
            new = list(shape)
            if mode == "notready":
                new[0] += data.draw(st.integers(1, 3))
            else:
                new[-1] += data.draw(st.integers(1, 3))
            new = tuple(new)
            cmd["shape"] = new
            cmd["chunks"] = tuple((n,) for n in new)
            shape, chunks = new, cmd["chunks"]
            reg_arr = None  # reads must fail
    case["mode"] = mode
    case["structure"] = (shape, chunks)

    # requests
    reqs = [None, ()]
    for _ in range(data.draw(st.integers(1, 4))):
        reqs.append(nd_index(data.draw, shape, allow_oob=True, allow_extra=True))
    # blocks: every block, with a random sub-request
    blocks = []
    if shape:
        nblocks = [len(c) for c in chunks]
        all_blocks = list(itertools.product(*[range(n) for n in nblocks]))
        for b in all_blocks[:12]:
            bshape = tuple(c[i] for c, i in zip(chunks, b))
            sub = data.draw(st.booleans())
            if sub:
                blocks.append((b, nd_index(data.draw, bshape, allow_oob=True, allow_extra=False)))
            else:
                blocks.append((b, None))
        # also a multi-block slice block, e.g. slice(0, nblocks) in dim 0
        if nblocks[0] >= 2:
            b = (slice(0, nblocks[0]),) + tuple(0 for _ in nblocks[1:])
            bshape = (shape[0],) + tuple(c[0] for c in chunks[1:])
            blocks.append((b, nd_index(data.draw, bshape, allow_oob=False, allow_extra=False)))
    full_cmd = dict(cmd, requests=reqs, blocks=blocks)
    res = {k: w.call(full_cmd) for k, w in workers().items()}
    for k, r in res.items():
        if "fatal" in r:
            record("fatal_" + k, case, dict(tb=r["fatal"]), fail)
            return
    h, p = res["head"], res["pr2"]
    if h["structure"] != p["structure"]:
        record("structure_differs", case, dict(head=str(h["structure"]), pr2=str(p["structure"])), fail)
    for req, hr, pr in zip(reqs, h["reads"], p["reads"]):
        STATS["reads"] += 1
        def rref():
            if reg_arr is None:
                raise RuntimeError("expected failure")
            return reg_arr[req] if req is not None else reg_arr

        nr = numpy_eval(rref)
        d = dict(op="read", req=fmt_idx(req), head=short(hr), pr2=short(pr), numpy=short(nr))
        if not same(hr, pr):
            record("read_head_vs_pr2", case, d, fail)
        elif hr[0] == "ok" and hr[1] != pr[1]:
            record("read_type_differs", case, d, False)
        if not same_vs_numpy(hr, nr):
            record("read_head_vs_numpy", case, d, fail)
        check_bytes("read", hr, pr, case, d, mode)
    for (blk, sub), hr, pr in zip(blocks, h["blocks"], p["blocks"]):
        STATS["blocks"] += 1

        def ref():
            bsl = []
            for b, c in zip(blk, chunks):
                if isinstance(b, int):
                    s0 = sum(c[:b])
                    bsl.append(slice(s0, s0 + c[b]))
                else:
                    bsl.append(slice(sum(c[: b.start]), sum(c[: b.stop])))
            a = reg_arr[tuple(bsl)]
            return a[sub] if sub is not None else a

        nr = numpy_eval(ref)
        d = dict(op="read_block", block=str(blk), req=fmt_idx(sub), head=short(hr), pr2=short(pr), numpy=short(nr))
        if not same(hr, pr):
            record("block_head_vs_pr2", case, d, fail)
        elif hr[0] == "ok" and hr[1] != pr[1]:
            record("block_type_differs", case, d, False)
        if not same_vs_numpy(hr, nr):
            record("block_head_vs_numpy", case, d, fail)
        check_bytes("block", hr, pr, case, d, mode)
    STATS["cases"] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "mismatches.jsonl"))
    args = ap.parse_args()

    @seed(args.seed)
    @settings(
        max_examples=args.examples,
        deadline=None,
        database=None,
        suppress_health_check=list(HealthCheck),
        derandomize=False,
    )
    @given(st.data())
    def prop(data):
        run_case(data, args.fail)

    try:
        prop()
    finally:
        with open(args.out, "w") as f:
            for m in MISMATCHES:
                f.write(json.dumps(m, default=str) + "\n")
        kinds = Counter(m["kind"] for m in MISMATCHES)
        print("STATS", dict(STATS))
        print("MISMATCH KINDS", dict(kinds))
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
