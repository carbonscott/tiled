Closes #3.

Follow-up to #2, and stacked on it. #2 passes one requested slice down to h5py, but two kinds of request still read far more than they ask for: a slice of a dataset registered with a `slice` parameter reads the whole registered row, and a request with a negative step reads whole Dask chunks (all of a contiguous dataset). This makes h5py read exactly the requested elements in both cases.

### What changed

- **`HDF5ArrayAdapter`** keeps the registered selection (the `slice` and `squeeze` parameters, as one expanded `NDSlice` called `_stencil`, the name `ZarrArrayAdapter` uses) apart from the lazy Dask array of the whole dataset. `read` and `read_block` compose it with the requested slice and slice the Dask array once, which Dask fuses into each chunk's `getter`, so h5py receives the requested selection.
- **Negative steps.** Dask never fuses a negative step into `getter` (`dask.array.optimization.normalize_slice` raises `NotImplementedError` for `step < 0`), so on #2 even a plain `arr[5, ::-1]` reads whole chunks. The composed selection is now read forwards and reversed in memory with #2's `_forward_selection`; h5py never sees a negative step.
- **`compose_slices`** now composes reversed slices that run to the start of an axis (`arr[0:10][::-1]` composed to the empty `slice(9, -1, -1)`), and `NDSlice.expand_for_shape` takes `squeeze=` to express a squeeze as integer indices. The hypothesis strategy in `test_slicer.py` had an emptiness filter that never drew these slices; with it fixed, the property test finds a failing example on #2 and passes here.
- **Unchanged:** the Dask chunking and the number of file opens. When the catalog's structure no longer matches the file (a dataset that grew, or a reshape), the registered view is sliced in memory as before.
- **One small behaviour change:** `adapter.read()` on a squeezed scalar dataset returns a NumPy scalar instead of a 0-d array, because the squeeze is now an integer index. The server applies `numpy.asarray`, so HTTP responses are identical.

### Results

*Pending: the end-to-end matrix, benchmarks, real-dataset comparison and media are running on a Slurm node and will be filled in here.*

### Tests

- New: `test_registered_slice_composes_with_requested_slice` (4 layouts × 4 registrations, every request shape and every `read_block`, asserting h5py bytes `==` result bytes) and `test_registered_slice_composes_over_http`. #2's `<=` assertion in `test_reads_only_requested_elements` is now `==`. With only `tests/test_hdf5.py` taken from this branch, 22 tests fail on #2 (514dc33a), all on byte counts.
- `tests/test_hdf5.py`: 71 passed (421569c4).
- The other test files that touch HDF5 (`test_catalog`, `test_container_files`, `test_deep_search`, `test_directory_walker`, `test_container_fields`, `test_export`, `test_register`, `test_simple_server`, `test_sync`, `test_tokenize`): 193 passed, 50 skipped, 3 xfailed.
- Rebased with #2 onto bluesky/tiled `main` (49fe22da): `tests/test_hdf5.py` 71 passed; the other HDF5 files 196 passed, 53 skipped, 3 xfailed, the same as unmodified `main` (48 and 196/53/3 passed/skipped/xfailed). No failures on either.
- `ruff check` and `ruff format --check` are clean.

### Reproduce

The proof scripts live on the orphan branch [`proof-lazy-hdf5`](https://github.com/carbonscott/tiled/tree/proof-lazy-hdf5), not in this PR. On Linux with `git` and `uv`; only `setup` needs the network. On a Slurm cluster, run `setup` on a login node and each later step as `srun --ntasks=1 --cpus-per-task=8 --mem=32G <step>` (add `--jobid=<id> --overlap` to run inside a held allocation).

```sh
git clone --branch hdf5-compose-registered-slice https://github.com/carbonscott/tiled tiled-pr && cd tiled-pr
git show origin/proof-lazy-hdf5:proof/tiled_e2e.py > ../tiled_e2e.py && cd ..
W=$PWD/tiled-e2e
uv run --script tiled_e2e.py setup --workdir "$W" \
    --build base=b7e1fea8570391852a52e06dada39397e24e2335 \
    --build pr2=514dc33a66430b053d1338801da19eb3154b993b \
    --build head=$(git -C tiled-pr rev-parse HEAD)
export UV_OFFLINE=1   # nothing after setup touches the network
uv run --script tiled_e2e.py data   --workdir "$W" --kind matrix
uv run --script tiled_e2e.py matrix --workdir "$W"        # 3 x 60 cells; exits 1 if head has any FAIL
uv run --script tiled_e2e.py data   --workdir "$W" --kind bench
uv run --script tiled_e2e.py bench  --workdir "$W" --requests 20
# results: $W/results/matrix.{txt,tsv,json} and $W/results/bench.{md,json}
```

### Checklist
- [x] Add a Changelog entry
- [x] Add the ticket number which this PR closes to the comment section

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01LXjGSbZpKujVHMN9pAKtp2
