# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""End-to-end proof: how many bytes does h5py read for one Tiled HTTP request?

Compares builds of carbonscott/tiled on synthetic HDF5 files, through a real
`tiled serve catalog` server and the build's own Python client, with h5py byte
counting injected into the server process (tiled itself is not modified).

    uv run tiled_e2e.py setup  --workdir W --build base=<sha> --build pr2=<sha> ...
    uv run tiled_e2e.py data   --workdir W --kind matrix
    uv run tiled_e2e.py matrix --workdir W --build base --build pr2 ...
    uv run tiled_e2e.py data   --workdir W --kind bench [--scale full|small|tiny]
    uv run tiled_e2e.py bench  --workdir W --build base --build pr2 ... [--requests 20]

`serve` and `register` start one server and fill it, for poking at by hand.
Only `setup` needs the network. Everything else runs offline (UV_OFFLINE=1).

What "h5py bytes" means: the server's h5py.Dataset.__getitem__ and read_direct
are wrapped, and each call logs the size of the array h5py hands back (selected
elements x itemsize). The client takes the log lines that one request added. This
shows which selection tiled asked h5py for. It does not show disk I/O: HDF5 reads
and decompresses whole chunks, the OS reads ahead, and file metadata is not counted.

A matrix cell PASSES when the values, dtype and shape equal the oracle (numpy on
the file read with h5py in the client, never via the server) AND h5py bytes ==
the bytes of the answer.

Layout of W:
    src/              clone of the repository (git worktrees hang off it)
    builds/LABEL/     detached worktree of one build, with its venv in .venv/
    builds.json       label -> {ref, sha}, written by setup
    resolution.json   the --exclude-newer time every build's venv resolves at
    data/matrix/      small files for the correctness/bytes matrix
    data/bench/       about 1 GB per file for the benchmark (at --scale full)
    instrument/       sitecustomize.py, put on the SERVER's PYTHONPATH only
    run/LABEL/        server log (API key redacted), h5py read log, api_key (0600)
    results/          matrix.{txt,tsv,json}, bench.{md,json}

The orchestrating commands (setup, matrix, bench) use only the standard library.
The work that needs numpy, h5py or tiled re-runs this file under the build's venv.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_URL = "https://github.com/carbonscott/tiled"
SCRIPT = Path(__file__).resolve()
DATASET = "/x"  # every synthetic file holds one 3-D stack at this path
LOG_ENV = "TILED_E2E_H5LOG"  # names the server's h5py read log

# ----------------------------------------------------------------------------
# The instrumentation. Written to W/instrument/sitecustomize.py and put first
# on the PYTHONPATH of the server process only. Python imports sitecustomize at
# startup, so this wraps h5py's reads before tiled imports h5py.
# ----------------------------------------------------------------------------
SITECUSTOMIZE = r'''"""h5py read counter for the tiled_e2e.py server (tiled itself is unmodified).

Active only when TILED_E2E_H5LOG names a log file. Appends one JSON line per
top-level h5py.Dataset.__getitem__ or Dataset.read_direct call, with the bytes
h5py returned (nbytes of the result, i.e. selected elements x itemsize).
"""
import os

_LOG = os.environ.get("TILED_E2E_H5LOG")
if _LOG:
    import json
    import threading
    import time

    import h5py

    _fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    _tls = threading.local()

    def _emit(record):
        # One write() per line on an O_APPEND fd: lines from threads do not interleave.
        os.write(_fd, (json.dumps(record) + "\n").encode())

    def _counted(method, measure):
        def wrapper(self, *args, **kwargs):
            if getattr(_tls, "busy", False):  # nested call: counted by the outer one
                return method(self, *args, **kwargs)
            _tls.busy = True
            t0 = time.perf_counter()
            try:
                out = method(self, *args, **kwargs)
            finally:
                _tls.busy = False
            nbytes, selection = measure(self, out, *args, **kwargs)
            _emit({
                "call": method.__name__,
                "file": os.path.basename(self.file.filename),
                "dataset": self.name,
                "selection": repr(selection)[:200],
                "nbytes": int(nbytes),
                "ms": round(1e3 * (time.perf_counter() - t0), 3),
            })
            return out
        wrapper.__wrapped__ = method
        return wrapper

    def _getitem(self, out, args, *_, **__):
        return getattr(out, "nbytes", 0), args

    def _read_direct(self, out, dest, source_sel=None, dest_sel=None):
        if source_sel is None:
            return self.size * self.dtype.itemsize, None
        from h5py._hl import selections
        n = selections.select(self.shape, source_sel, self).nselect
        return n * self.dtype.itemsize, source_sel

    h5py.Dataset.__getitem__ = _counted(h5py.Dataset.__getitem__, _getitem)
    h5py.Dataset.read_direct = _counted(h5py.Dataset.read_direct, _read_direct)
    _emit({"event": "installed", "pid": os.getpid(), "h5py": h5py.__version__})
'''


# ============================================================================
# Small helpers (standard library only)
# ============================================================================


def sh(*cmd, cwd=None, env=None, capture=False) -> str:
    """Run a command, echo it, fail loudly."""
    print("+", " ".join(str(c) for c in cmd), flush=True)
    res = subprocess.run(
        [str(c) for c in cmd],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return (res.stdout or "").strip()


def venv_python(W: Path, label: str) -> Path:
    py = W / "builds" / label / ".venv" / "bin" / "python"
    if not py.exists():
        sys.exit(f"no venv for build {label!r} at {py}; run `setup` first")
    return py


def builds_json(W: Path) -> dict:
    path = W / "builds.json"
    return json.loads(path.read_text()) if path.exists() else {}


def labels_or_all(W: Path, labels: list[str] | None) -> list[str]:
    labels = labels or list(builds_json(W))
    if not labels:
        sys.exit("no builds given and none set up; run `setup` first")
    return labels


def in_venv(W: Path, label: str) -> bool:
    return Path(sys.prefix).resolve() == (W / "builds" / label / ".venv").resolve()


def reexec_in_venv(W: Path, label: str) -> None:
    """Replace this process with the same command under the build's venv python."""
    if not in_venv(W, label):
        py = venv_python(W, label)
        os.execv(py, [str(py), str(SCRIPT), *sys.argv[1:]])


def run_worker(W: Path, label: str, *argv: str) -> None:
    """Run one hidden worker subcommand of this file under the build's venv python."""
    cmd = [venv_python(W, label), SCRIPT, *argv]
    print(f"\n=== build {label}: {' '.join(argv[:1])} ===", flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fmt_bytes(n) -> str:
    if n is None:
        return "-"
    for unit, size in (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if n >= size:
            return f"{n / size:.2f} {unit}"
    return f"{n} B"


def aligned(rows: list[list], header: list[str]) -> str:
    cells = [header] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(header))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in cells]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


# ============================================================================
# setup: clone, one detached worktree + venv per build
# ============================================================================


def cmd_setup(args) -> None:
    W = Path(args.workdir).resolve()
    src = W / "src"
    W.mkdir(parents=True, exist_ok=True)
    if not (src / ".git").exists():
        sh("git", "clone", "--quiet", args.repo, src)
    else:
        sh("git", "-C", src, "fetch", "--quiet", "--tags", "origin")
    print("uv cache:", os.environ.get("UV_CACHE_DIR", "(uv default)"))

    # Every build resolves its dependencies as of one moment, fixed at the first
    # setup, so the builds differ in tiled only (checked again in the results).
    pin = W / "resolution.json"
    if not pin.exists():
        when = args.exclude_newer or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pin.write_text(json.dumps({"exclude_newer": when}) + "\n")
    exclude_newer = json.loads(pin.read_text())["exclude_newer"]
    print("resolving dependencies as of", exclude_newer)

    recorded = builds_json(W)
    for spec in args.build:
        label, _, ref = spec.partition("=")
        if not ref:
            sys.exit(f"--build wants LABEL=REF, got {spec!r}")
        sha = resolve_ref(src, ref)
        tree = W / "builds" / label
        if not tree.exists():
            sh("git", "-C", src, "worktree", "add", "--detach", "--quiet", tree, sha)
        else:
            sh("git", "-C", tree, "checkout", "--detach", "--quiet", sha)
        venv = tree / ".venv"
        if not venv.exists():
            sh("uv", "venv", "--quiet", "--python", args.python, venv)
        env = dict(
            os.environ, TILED_BUILD_SKIP_UI="1"
        )  # no npm: the web UI is not needed
        py = venv / "bin" / "python"
        sh(
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            py,
            "--exclude-newer",
            exclude_newer,
            "-e",
            f"{tree}[server,client]",
            "h5py",
            "hdf5plugin",
            "numpy",
            env=env,
        )
        # Prove the venv works without the network and record exactly what is in it.
        sh(
            py,
            "-c",
            "import tiled, h5py, hdf5plugin, numpy, uvicorn;"
            "from tiled.adapters.hdf5 import HDF5ArrayAdapter;"
            "from tiled.client import from_uri;"
            "print('tiled', tiled.__version__, 'h5py', h5py.__version__,"
            "'HDF5', h5py.version.hdf5_version, 'numpy', numpy.__version__)",
        )
        freeze = sh("uv", "pip", "freeze", "--quiet", "--python", py, capture=True)
        (tree.parent / f"{label}.freeze.txt").write_text(freeze + "\n")
        recorded[label] = {"ref": ref, "sha": sha}
        print(f"build {label}: {sha} ready at {tree}")
    (W / "builds.json").write_text(json.dumps(recorded, indent=2) + "\n")


def resolve_ref(src: Path, ref: str) -> str:
    def rev(r):
        res = subprocess.run(
            [
                "git",
                "-C",
                str(src),
                "rev-parse",
                "--verify",
                "--quiet",
                f"{r}^{{commit}}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        return res.stdout.strip() if res.returncode == 0 else None

    sha = rev(ref) or rev(f"origin/{ref}")
    if sha is None:  # e.g. a commit only reachable from a pull-request ref
        sh("git", "-C", src, "fetch", "--quiet", "origin", ref)
        sha = rev("FETCH_HEAD")
    if sha is None:
        sys.exit(f"cannot resolve {ref!r} in {REPO_URL}")
    return sha


# ============================================================================
# data: synthetic files (needs numpy + h5py, so runs under a build venv)
# ============================================================================

MATRIX_SHAPE = (48, 96, 128)  # entities x H x W
MATRIX_CHUNKS = (8, 40, 48)  # spans 8 entities; partial chunks at the H and W edges

BENCH_SCALES = {
    # entities, H, W (float64), entities per chunk in the "chunks_many" file
    "full": (
        1000,
        256,
        512,
        64,
    ),  # 1 MiB per entity, ~1 GiB per file (as PR #2's benchmark)
    "small": (200, 128, 256, 32),  # 256 KiB per entity
    "tiny": (40, 32, 64, 8),  # 16 KiB per entity
}


def middle_row(n: int) -> int:
    """The registered row: off the middle, so it does not start a chunk."""
    return min(n - 1, n // 2 + 3)


def entity_values(i0: int, i1: int, h: int, w: int, dtype: str):
    """Entities i0..i1-1. Every element differs within an entity, and so does each
    entity's offset: float64 holds i*h*w + j*w + k exactly; int16 holds that with
    the entity offset i*7919 instead, wrapped into the int16 range."""
    import numpy as np

    i = np.arange(i0, i1, dtype=np.int64)[:, None, None]
    jk = np.arange(h * w, dtype=np.int64).reshape(1, h, w)
    if dtype == "float64":
        return (i * h * w + jk).astype(np.float64)
    return ((i * 7919 + jk) % 65536 - 32768).astype(np.int16)


def write_stack(
    path: Path,
    shape,
    dtype: str,
    chunks=None,
    compression=None,
    batch: int = 64,
    attrs=None,
    force: bool = False,
) -> None:
    import h5py

    n, h, w = shape
    if path.exists() and not force:  # keep a file that already has this layout
        with h5py.File(path, "r") as f:
            ds = f.get(DATASET)
            if ds is not None and (ds.shape, ds.dtype, ds.chunks, ds.compression) == (
                tuple(shape),
                dtype,
                chunks,
                compression,
            ):
                print(f"  {path.name}: exists with this layout, kept")
                return
    tmp = path.with_suffix(".tmp")
    with h5py.File(tmp, "w") as f:
        ds = f.create_dataset(
            DATASET, shape=shape, dtype=dtype, chunks=chunks, compression=compression
        )
        for i0 in range(0, n, batch):
            i1 = min(n, i0 + batch)
            ds[i0:i1] = entity_values(i0, i1, h, w, dtype)
        ds.attrs.update(attrs or {})
        ds.attrs["row"] = middle_row(n)
    with open(tmp, "rb+") as fh:  # dirty pages cannot be evicted for the cold runs
        os.fsync(fh.fileno())
    tmp.rename(path)
    print(
        f"  {path.name}: shape={shape} dtype={dtype} chunks={chunks} "
        f"compression={compression} size={fmt_bytes(path.stat().st_size)}"
    )


def cmd_data(args) -> None:
    W = Path(args.workdir).resolve()
    try:
        import h5py  # noqa: F401
    except ImportError:
        reexec_in_venv(W, next(iter(labels_or_all(W, None))))
    out = W / "data" / args.kind
    out.mkdir(parents=True, exist_ok=True)
    print(f"writing {args.kind} files under {out}")
    if args.kind == "matrix":
        for dtype in ("float64", "int16"):
            for layout, chunks, comp in (
                ("contiguous", None, None),
                ("chunked", MATRIX_CHUNKS, None),
                ("compressed", MATRIX_CHUNKS, "gzip"),
            ):
                write_stack(
                    out / f"m_{layout}_{dtype}.h5",
                    MATRIX_SHAPE,
                    dtype,
                    chunks,
                    comp,
                    attrs={"layout": layout},
                    force=args.force,
                )
    else:
        n, h, w, many = BENCH_SCALES[args.scale]
        for layout, chunks, comp in (
            ("contiguous", None, None),
            ("chunks_many", (many, h, w), None),
            ("chunks_one", (1, h, w), None),
            ("compressed", (1, h, w), "gzip"),
        ):
            write_stack(
                out / f"b_{layout}.h5",
                (n, h, w),
                "float64",
                chunks,
                comp,
                attrs={"layout": layout, "scale": args.scale},
                force=args.force,
            )


# ============================================================================
# The server: tiled serve catalog --temp, instrumented, key never shown
# ============================================================================


class Server:
    """`tiled serve catalog --temp` from one build's venv, with the h5py counter.

    The API key is random, reaches the server only through its environment, and
    is redacted from everything the server prints (tiled prints the key at startup
    when it was not given with --api-key, and a command line is visible to others).
    """

    def __init__(self, W: Path, label: str, port: int | None = None):
        self.W, self.label = W, label
        self.port = port or free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.key = secrets.token_hex(32)
        self.run = W / "run" / label
        self.h5log = self.run / "h5py.log"
        self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self, timeout: float = 180.0) -> None:
        self.run.mkdir(parents=True, exist_ok=True)
        (self.run / "tmp").mkdir(exist_ok=True)
        inst = self.W / "instrument"
        inst.mkdir(exist_ok=True)
        (inst / "sitecustomize.py").write_text(SITECUSTOMIZE)
        self.h5log.write_bytes(b"")
        (self.W / "data").mkdir(exist_ok=True)
        tiled = self.W / "builds" / self.label / ".venv" / "bin" / "tiled"
        env = dict(os.environ)
        env.pop("TILED_API_KEY", None)
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [str(inst), env.get("PYTHONPATH")])
                ),
                LOG_ENV: str(self.h5log),
                "TILED_SINGLE_USER_API_KEY": self.key,
                "TMPDIR": str(self.run / "tmp"),  # where --temp puts its catalog
            }
        )
        cmd = [
            str(tiled),
            "serve",
            "catalog",
            "--temp",
            "--read",
            str((self.W / "data").resolve()),  # may be a symlink
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        print(f"[{self.label}] starting: {' '.join(cmd)}", flush=True)
        self.proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=self.run,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        threading.Thread(target=self._copy_log, daemon=True).start()
        deadline = time.monotonic() + timeout
        while True:
            if self.proc.poll() is not None:
                self._fail("server exited before it was ready")
            try:
                urllib.request.urlopen(self.url + "/api/v1/", timeout=2).read()
                break
            except urllib.error.HTTPError:
                break  # it answered
            except OSError:
                if time.monotonic() > deadline:
                    self._fail("server not ready in time")
                time.sleep(0.25)
        if b'"installed"' not in self.h5log.read_bytes():
            self._fail("h5py instrumentation did not load in the server")
        print(
            f"[{self.label}] ready at {self.url} (pid {self.proc.pid}); "
            f"log {self.run / 'server.log'}",
            flush=True,
        )

    def _copy_log(self) -> None:
        secret = self.key.encode()
        with open(self.run / "server.log", "wb") as log:
            for line in self.proc.stdout:
                log.write(line.replace(secret, b"<redacted>"))
                log.flush()

    def _fail(self, why: str):
        self.stop()
        tail = (self.run / "server.log").read_text(errors="replace")[-4000:]
        sys.exit(f"[{self.label}] {why}. Server log tail:\n{tail}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    # The read log ----------------------------------------------------------
    def log_offset(self) -> int:
        return self.h5log.stat().st_size

    def reads_since(self, offset: int) -> list[dict]:
        with open(self.h5log, "rb") as f:
            f.seek(offset)
            lines = f.read().splitlines()
        return [r for r in map(json.loads, lines) if "event" not in r]


# ============================================================================
# Registration (runs under the build venv: uses the build's own client)
# ============================================================================


def provenance(W: Path, label: str) -> dict:
    """What actually ran: the worktree's commit and the versions in its venv."""
    import platform

    import dask
    import h5py
    import numpy
    import tiled

    sha = subprocess.run(
        ["git", "-C", str(W / "builds" / label), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "sha": sha,
        "tiled": tiled.__version__,
        "dask": dask.__version__,
        "h5py": h5py.__version__,
        "hdf5": h5py.version.hdf5_version,
        "numpy": numpy.__version__,
        "python": platform.python_version(),
        "host": socket.gethostname(),
    }


def provenance_lines(parts: dict) -> str:
    keys = ("sha", "tiled", "dask", "h5py", "hdf5", "numpy", "python", "host")
    lines = [
        f"{label}: " + " ".join(f"{k}={d.get(k)}" for k in keys)
        for label, d in parts.items()
    ]
    for k in keys[2:]:  # everything but tiled itself should be the same
        if len({d.get(k) for d in parts.values()}) > 1:
            lines.append(f"WARNING: builds differ in {k}, not only in tiled")
    return "\n".join(lines)


def connect(url: str, key: str):
    from tiled.client import from_uri

    return from_uri(url, api_key=key)


def register_files(client, W: Path, kind: str) -> dict:
    """Register every file in W/data/KIND twice, as nodes '<stem>-whole' and
    '<stem>-row' (the registered `slice` is the file's middle row)."""
    import h5py
    from tiled.structures.array import ArrayStructure, BuiltinDtype
    from tiled.structures.core import StructureFamily
    from tiled.structures.data_source import Asset, DataSource, Management
    from tiled.utils import ensure_uri

    files = sorted(p.resolve() for p in (W / "data" / kind).glob("*.h5"))
    if not files:
        sys.exit(f"no files in {W / 'data' / kind}; run `data --kind {kind}` first")
    nodes = {}
    for path in files:
        with h5py.File(path, "r") as f:
            ds = f[DATASET]
            shape, dtype, row = ds.shape, ds.dtype, int(ds.attrs["row"])
            layout = str(ds.attrs["layout"])
            file_chunks = ds.chunks or ds.shape
        # The Dask chunks every build's HDF5ArrayAdapter makes: whole file chunks
        # with a remainder at the end (tiled.adapters.utils.split_chunks).
        chunks = tuple(
            tuple([c] * (n // c) + ([n % c] if n % c else []))
            for n, c in zip(shape, file_chunks)
        )
        for reg in ("whole", "row"):
            params = {"dataset": DATASET}
            s_shape, s_chunks = shape, chunks
            if reg == "row":
                params["slice"] = str(row)
                s_shape, s_chunks = shape[1:], chunks[1:]
            source = DataSource(
                structure_family=StructureFamily.array,
                mimetype="application/x-hdf5",
                structure=ArrayStructure(
                    data_type=BuiltinDtype.from_numpy_dtype(dtype),
                    chunks=s_chunks,
                    shape=s_shape,
                ),
                parameters=params,
                management=Management.external,
                assets=[
                    Asset(
                        data_uri=ensure_uri(str(path)),
                        is_directory=False,
                        parameter="data_uris",
                        num=0,
                    )
                ],
            )
            key = f"{path.stem}-{reg}"
            client.new(
                structure_family=StructureFamily.array,
                data_sources=[source],
                key=key,
                metadata={"layout": layout, "registration": reg},
            )
            nodes[key] = {
                "path": str(path),
                "layout": layout,
                "dtype": str(dtype),
                "registration": reg,
                "row": row,
                "shape": list(s_shape),
                "chunks": [list(c) for c in s_chunks],
            }
    print(f"registered {len(nodes)} nodes from {len(files)} files in data/{kind}")
    return nodes


class ClientSlices:
    """Records the query string of every request the tiled client sends."""

    def __init__(self, client):
        self.sent = []
        client.context.http_client.event_hooks["request"].append(self._hook)

    def _hook(self, request):
        q = request.url.params
        self.sent.append({k: q[k] for k in ("slice", "block") if k in q})

    def take(self) -> list[dict]:
        out, self.sent = self.sent, []
        return out


def timed_read(server: Server, node, how: str, arg):
    """One client read. Returns (array, ms, h5py reads made by the server)."""
    offset = server.log_offset()
    t0 = time.perf_counter()
    out = node.read_block(arg) if how == "block" else node[arg]
    ms = 1e3 * (time.perf_counter() - t0)
    return out, ms, server.reads_since(offset)


def sel_str(sel) -> str:
    def one(s):
        if isinstance(s, slice):
            return ":".join(
                "" if v is None else str(v)
                for v in (s.start, s.stop) + ((s.step,) if s.step else ())
            )
        return str(s)

    sel = sel if isinstance(sel, tuple) else (sel,)
    return "[" + ",".join(one(s) for s in sel) + "]"


# ============================================================================
# matrix: 3 layouts x 2 registrations x 5 requests x 2 dtypes = 60 cells
# ============================================================================


def matrix_requests(node: dict):
    """The five requests for one node, as (name, how, client arg, oracle).

    The oracle maps the file's full array (read with h5py in this client process,
    never through the server) to the expected answer with numpy indexing.
    """
    r, chunks = node["row"], node["chunks"]
    H, W = node["shape"][-2:]
    subs = {
        "window": (slice(H // 5, H // 5 + 10), slice(W // 3, W // 3 + 10)),
        "strided": (slice(1, H - 6, 3), slice(2, W - 8, 4)),
        # Reversed on both axes. The second reaches index 0, which the client sends
        # with a stop below -W (e.g. "64:-129:-4"), the canonical form ndindex makes.
        "negstep": (slice(None, None, -2), slice(W // 2, None, -4)),
    }
    mid = tuple(len(c) // 2 for c in chunks[-2:])  # a block in the middle of H and W
    if node["registration"] == "whole":  # the node is the stack; ask for entity r
        view, entity, lead = (lambda a: a), r, (r,)
        block = (r // chunks[0][0], *mid)  # the block that holds entity r
    else:  # the node is entity r already (registered slice)
        view, entity, lead = (lambda a: a[r]), slice(None), ()
        block = mid
    bsel = tuple(slice(sum(c[:b]), sum(c[: b + 1])) for b, c in zip(block, chunks))
    reqs = [("entity", "slice", entity, lambda a: view(a)[entity])]
    for name, sub in subs.items():
        reqs.append((name, "slice", lead + sub, lambda a, sel=lead + sub: view(a)[sel]))
    reqs.append(("block", "block", block, lambda a: view(a)[bsel]))
    return reqs


def worker_matrix(args) -> None:
    import h5py
    import numpy as np

    W = Path(args.workdir).resolve()
    with Server(W, args.build, args.port) as server:
        client = connect(server.url, server.key)
        nodes = register_files(client, W, "matrix")
        sent = ClientSlices(client)
        client[next(iter(nodes))][0]  # warm-up (imports, first adapter); not recorded
        full, cells = {}, []
        for key, node in nodes.items():
            if node["path"] not in full:
                with h5py.File(node["path"], "r") as f:
                    full[node["path"]] = f[DATASET][...]
            arr = full[node["path"]]
            remote = client[key]
            sent.take()
            for name, how, arg, oracle in matrix_requests(node):
                expected = oracle(arr)
                cell = {
                    "build": args.build,
                    "layout": node["layout"],
                    "registration": node["registration"],
                    "request": name,
                    "dtype": node["dtype"],
                    "client_call": (
                        f"read_block({arg})" if how == "block" else f"arr{sel_str(arg)}"
                    ),
                }
                try:
                    got, ms, reads = timed_read(server, remote, how, arg)
                except Exception as err:  # noqa: BLE001 -- a rejected request is a result
                    cell.update(
                        equal=False,
                        h5py_bytes=None,
                        requested_bytes=None,
                        ms=None,
                        error=f"{type(err).__name__}: {err}"[:300],
                        sent=sent.take(),
                    )
                    cells.append(cell)
                    continue
                cell.update(
                    equal=bool(
                        got.shape == expected.shape
                        and got.dtype == expected.dtype
                        and np.array_equal(got, expected)
                    ),
                    h5py_bytes=sum(r["nbytes"] for r in reads),
                    requested_bytes=int(got.nbytes),
                    ms=round(ms, 2),
                    h5py_calls=len(reads),
                    h5py_selections=[r["selection"] for r in reads][:8],
                    sent=sent.take(),
                )
                cells.append(cell)
    Path(args.out).write_text(
        json.dumps(
            {"build": args.build, **provenance(W, args.build), "cells": cells}, indent=1
        )
    )


def verdict(c: dict) -> str:
    if c.get("error"):
        return "ERROR"
    if not c["equal"]:
        return "FAIL(value)"
    return "PASS" if c["h5py_bytes"] == c["requested_bytes"] else "FAIL(bytes)"


def cmd_matrix(args) -> None:
    W = Path(args.workdir).resolve()
    labels = labels_or_all(W, args.build)
    res = W / "results"
    res.mkdir(exist_ok=True)
    cells, ran = [], {}
    for label in labels:
        part = res / f"matrix-{label}.json"
        run_worker(
            W,
            label,
            "_matrix-worker",
            "--workdir",
            str(W),
            "--build",
            label,
            "--out",
            str(part),
            *(["--port", str(args.port)] if args.port else []),
        )
        ran[label] = json.loads(part.read_text())
        cells += ran[label].pop("cells")
    order = {
        v: i
        for i, v in enumerate(
            (
                "contiguous",
                "chunked",
                "compressed",
                "whole",
                "row",
                "float64",
                "int16",
                "entity",
                "window",
                "strided",
                "negstep",
                "block",
            )
        )
    }
    cells.sort(
        key=lambda c: (
            labels.index(c["build"]),
            order[c["layout"]],
            order[c["registration"]],
            order[c["dtype"]],
            order[c["request"]],
        )
    )

    header = [
        "build",
        "layout",
        "registration",
        "request",
        "dtype",
        "equal",
        "h5py_bytes",
        "requested_bytes",
        "ms",
        "verdict",
    ]
    rows = [
        [
            c["build"],
            c["layout"],
            c["registration"],
            c["request"],
            c["dtype"],
            c["equal"],
            c["h5py_bytes"],
            c["requested_bytes"],
            c["ms"],
            verdict(c),
        ]
        for c in cells
    ]
    table = aligned(rows, header)
    tally = {}
    for label in labels:
        mine = [c for c in cells if c["build"] == label]
        v = [verdict(c) for c in mine]
        tally[label] = {
            "cells": len(mine),
            "PASS": v.count("PASS"),
            "FAIL": len(mine) - v.count("PASS"),
            "equal_only": v.count("FAIL(bytes)"),
            "not_equal": v.count("FAIL(value)"),
            "error": v.count("ERROR"),
        }
    tally_txt = "\n".join(
        f"{label}: PASS {t['PASS']}/{t['cells']}  FAIL {t['FAIL']}  "
        f"(equal but extra bytes: {t['equal_only']}, wrong values: {t['not_equal']}, "
        f"errors: {t['error']})"
        for label, t in tally.items()
    )
    errors = "\n".join(
        f"{c['build']} {c['layout']} {c['registration']} {c['request']} "
        f"{c['dtype']}: {c['error']}"
        for c in cells
        if c.get("error")
    )
    text = (
        provenance_lines(ran) + "\n\n" + table + "\n\n"
        "PASS = equal values, dtype and shape AND h5py bytes == requested bytes\n"
        + tally_txt
        + ("\n\nErrors:\n" + errors if errors else "")
        + "\n"
    )
    print("\n" + text)
    (res / "matrix.txt").write_text(text)
    (res / "matrix.tsv").write_text(
        "\n".join("\t".join(map(str, r)) for r in [header] + rows) + "\n"
    )
    (res / "matrix.json").write_text(
        json.dumps({"builds": ran, "tally": tally, "cells": cells}, indent=1)
    )
    print(f"results: {res / 'matrix.txt'} .tsv .json")
    if args.require_pass in tally and tally[args.require_pass]["FAIL"]:
        sys.exit(
            f"build {args.require_pass} has {tally[args.require_pass]['FAIL']} FAIL cells"
        )


# ============================================================================
# bench: warm and cold request latency, per build x scenario
# ============================================================================

BENCH_SCENARIOS = (
    # name, file stem, node, request
    ("contiguous", "b_contiguous", "whole", "entity"),
    ("chunks_many", "b_chunks_many", "whole", "entity"),
    ("chunks_one", "b_chunks_one", "whole", "entity"),
    ("compressed", "b_compressed", "whole", "entity"),
    ("row_window", "b_contiguous", "row", "window10"),
)


def resident_pages(path: str) -> tuple[int, int]:
    """(resident, total) pages of the file in the page cache, via mmap + mincore."""
    import ctypes

    import numpy as np

    size = os.path.getsize(path)
    page = os.sysconf("SC_PAGE_SIZE")
    npages = (size + page - 1) // page
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = (
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_long,
    )
    libc.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
    libc.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    fd = os.open(path, os.O_RDONLY)
    try:
        addr = libc.mmap(None, size, 0x1, 0x01, fd, 0)  # PROT_READ, MAP_SHARED
        if addr in (None, ctypes.c_void_p(-1).value):
            raise OSError(ctypes.get_errno(), "mmap failed")
        vec = (ctypes.c_ubyte * npages)()
        try:
            if libc.mincore(ctypes.c_void_p(addr), size, vec) != 0:
                raise OSError(ctypes.get_errno(), "mincore failed")
        finally:
            libc.munmap(ctypes.c_void_p(addr), size)
    finally:
        os.close(fd)
    return int((np.frombuffer(vec, np.uint8) & 1).sum()), npages


def evict(path: str, tries: int = 5) -> dict:
    """Drop the file from the page cache, then count its resident pages (mincore).

    Pages read a moment ago can sit in per-CPU LRU batches that one DONTNEED skips,
    so this retries a few times before it reports what is left.
    """
    for attempt in range(1, tries + 1):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
        resident, _ = resident_pages(path)
        if resident == 0:
            break
        time.sleep(0.1)
    return {"verified": resident == 0, "resident_pages": resident, "attempts": attempt}


def worker_bench(args) -> None:
    import numpy as np

    W = Path(args.workdir).resolve()
    samples = []
    with Server(W, args.build, args.port) as server:
        client = connect(server.url, server.key)
        nodes = register_files(client, W, "bench")
        rng = random.Random(args.seed)  # same seed, same draws, for every build
        for scenario, stem, reg, request in BENCH_SCENARIOS:
            key = f"{stem}-{reg}"
            node, remote = nodes[key], client[key]
            n = node["shape"][0]
            H, Wd = node["shape"][-2:]
            draws = []
            for _ in range(args.requests):
                if request == "entity":
                    draws.append(rng.randrange(n))
                else:
                    j, k = rng.randrange(H - 10), rng.randrange(Wd - 10)
                    draws.append((slice(j, j + 10), slice(k, k + 10)))
            timed_read(server, remote, "slice", draws[0])  # warm-up, not recorded
            for arg in draws:
                # The answer, from the formula the file was written with (no file read).
                if request == "entity":
                    expected = entity_values(arg, arg + 1, H, Wd, node["dtype"])[0]
                else:
                    expected = entity_values(
                        node["row"], node["row"] + 1, H, Wd, node["dtype"]
                    )[0][arg]
                # cold evicts the file first; warm repeats the request right after
                for temp in ("cold", "warm"):
                    eviction = evict(node["path"]) if temp == "cold" else {}
                    got, ms, reads = timed_read(server, remote, "slice", arg)
                    samples.append(
                        {
                            "build": args.build,
                            "scenario": scenario,
                            "temp": temp,
                            "request": f"arr{sel_str(arg)}",
                            "ms": ms,
                            "h5py_bytes": sum(r["nbytes"] for r in reads),
                            "requested_bytes": int(got.nbytes),
                            "equal": bool(np.array_equal(got, expected)),
                            "evicted_verified": eviction.get("verified"),
                            "eviction": eviction,
                        }
                    )
            print(
                f"[{args.build}] {scenario}: {len(draws)} cold + {len(draws)} warm",
                flush=True,
            )
    Path(args.out).write_text(
        json.dumps(
            {"build": args.build, **provenance(W, args.build), "samples": samples}
        )
    )


def cmd_bench(args) -> None:
    W = Path(args.workdir).resolve()
    labels = labels_or_all(W, args.build)
    res = W / "results"
    res.mkdir(exist_ok=True)
    samples, ran = [], {}
    for label in labels:  # sequential: one build, one server at a time
        part = res / f"bench-{label}.json"
        run_worker(
            W,
            label,
            "_bench-worker",
            "--workdir",
            str(W),
            "--build",
            label,
            "--out",
            str(part),
            "--requests",
            str(args.requests),
            "--seed",
            str(args.seed),
            *(["--port", str(args.port)] if args.port else []),
        )
        ran[label] = json.loads(part.read_text())
        samples += ran[label].pop("samples")

    def med(xs):
        return statistics.median(xs) if xs else None

    lines = [
        (
            "| scenario | build | requested B/req | median h5py B/req | median warm ms "
            "| median cold ms | cold evictions verified | values equal |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    summary = []
    for scenario, *_ in BENCH_SCENARIOS:
        for label in labels:
            s = [
                x for x in samples if x["build"] == label and x["scenario"] == scenario
            ]
            warm = [x for x in s if x["temp"] == "warm"]
            cold = [x for x in s if x["temp"] == "cold"]
            row = {
                "scenario": scenario,
                "build": label,
                "requested_bytes": med([x["requested_bytes"] for x in s]),
                "h5py_bytes": med([x["h5py_bytes"] for x in s]),
                "warm_ms": med([x["ms"] for x in warm]),
                "cold_ms": med([x["ms"] for x in cold]),
                "verified": sum(bool(x["evicted_verified"]) for x in cold),
                "n": len(cold),
                "equal": sum(x["equal"] for x in s),
                "samples": len(s),
            }
            summary.append(row)
            lines.append(
                f"| {scenario} | {label} | {fmt_bytes(row['requested_bytes'])} "
                f"| {fmt_bytes(row['h5py_bytes'])} | {row['warm_ms']:.1f} "
                f"| {row['cold_ms']:.1f} | {row['verified']}/{row['n']} "
                f"| {row['equal']}/{row['samples']} |"
            )
    note = (
        f"\n{args.requests} cold + {args.requests} warm requests per cell; rows (and "
        f"windows) drawn with seed {args.seed}, the same draws for every build. Builds ran one after "
        "another, each with its own server; cold = posix_fadvise(DONTNEED) on the file "
        "then mincore check; warm = the same request again right after. One unrecorded "
        f"warm-up request per scenario.\n"
    )
    md = "\n".join(lines) + "\n" + note + "\n" + provenance_lines(ran) + "\n"
    print("\n" + md)
    (res / "bench.md").write_text(md)
    (res / "bench.json").write_text(
        json.dumps({"builds": ran, "summary": summary, "samples": samples}, indent=1)
    )
    print(f"results: {res / 'bench.md'} .json")


# ============================================================================
# serve / register: one server by hand
# ============================================================================


def cmd_serve(args) -> None:
    W = Path(args.workdir).resolve()
    reexec_in_venv(W, args.build)
    server = Server(W, args.build, args.port)
    keyfile = server.run / "api_key"  # for `register` and for use by hand; owner-only
    server.run.mkdir(parents=True, exist_ok=True)
    fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    os.write(fd, server.key.encode())
    os.close(fd)
    with server:
        (server.run / "server.json").write_text(
            json.dumps(
                {
                    "url": server.url,
                    "pid": server.proc.pid,
                    "api_key_file": str(keyfile),
                    "h5py_log": str(server.h5log),
                },
                indent=1,
            )
        )
        print(
            f"serving {args.build} at {server.url}\n"
            f"  register: uv run {SCRIPT.name} register --workdir {W} --build {args.build}\n"
            f"  by hand:  export TILED_API_KEY=$(cat {keyfile})\n"
            f"  h5py reads: tail -f {server.h5log}\nCtrl-C stops it.",
            flush=True,
        )
        try:
            server.proc.wait()
        except KeyboardInterrupt:
            pass


def cmd_register(args) -> None:
    W = Path(args.workdir).resolve()
    reexec_in_venv(W, args.build)
    run = W / "run" / args.build
    info = json.loads((run / "server.json").read_text())
    client = connect(args.url or info["url"], (run / "api_key").read_text().strip())
    kinds = ["matrix", "bench"] if args.kind == "all" else [args.kind]
    for kind in kinds:
        if (W / "data" / kind).exists():
            register_files(client, W, kind)


# ============================================================================
# Command line
# ============================================================================


def main(argv=None) -> None:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name, func, help_, build="many"):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.add_argument("--workdir", required=True, help="everything lives under here")
        if build == "many":
            sp.add_argument(
                "--build",
                action="append",
                metavar="LABEL",
                help="build label, repeatable (default: all set up)",
            )
        elif build == "one":
            sp.add_argument("--build", required=True, metavar="LABEL")
        sp.set_defaults(func=func)
        return sp

    sp = add(
        "setup", cmd_setup, "clone, one worktree + venv per build (needs network)", None
    )
    sp.add_argument(
        "--build",
        action="append",
        required=True,
        metavar="LABEL=REF",
        help="e.g. base=b7e1fea8 (a SHA, branch or tag), repeatable",
    )
    sp.add_argument("--repo", default=REPO_URL)
    sp.add_argument("--python", default="3.12", help="interpreter for the venvs (uv)")
    sp.add_argument(
        "--exclude-newer",
        metavar="TIMESTAMP",
        help="resolve as of this RFC 3339 time (default: now, at first setup)",
    )

    sp = add("data", cmd_data, "write synthetic HDF5 files under W/data", None)
    sp.add_argument("--kind", choices=("matrix", "bench"), required=True)
    sp.add_argument(
        "--scale",
        choices=tuple(BENCH_SCALES),
        default="full",
        help="bench file size (full = 1000 x 1 MiB float64 per file)",
    )
    sp.add_argument("--force", action="store_true", help="rewrite files that exist")

    sp = add("serve", cmd_serve, "run one instrumented server in the foreground", "one")
    sp.add_argument("--port", type=int)

    sp = add(
        "register", cmd_register, "register the data files into a `serve` server", "one"
    )
    sp.add_argument("--kind", choices=("matrix", "bench", "all"), default="all")
    sp.add_argument("--url", help="default: the url `serve` wrote to W/run/LABEL")

    sp = add("matrix", cmd_matrix, "60-cell correctness + bytes matrix per build")
    sp.add_argument("--port", type=int, help="default: a free port")
    sp.add_argument(
        "--require-pass",
        default="head",
        metavar="LABEL",
        help="exit non-zero if this build has any FAIL (default: head)",
    )

    sp = add("bench", cmd_bench, "warm/cold latency per build x scenario")
    sp.add_argument("--requests", type=int, default=20)
    sp.add_argument("--seed", type=int, default=12345)
    sp.add_argument("--port", type=int)

    for name, func in (
        ("_matrix-worker", worker_matrix),
        ("_bench-worker", worker_bench),
    ):
        sp = sub.add_parser(name)  # internal: runs under the build's venv
        sp.add_argument("--workdir", required=True)
        sp.add_argument("--build", required=True)
        sp.add_argument("--out", required=True)
        sp.add_argument("--port", type=int)
        sp.add_argument("--requests", type=int, default=20)
        sp.add_argument("--seed", type=int, default=12345)
        sp.set_defaults(func=func)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
