# Unit-test runs (orchestrator's own re-runs, local VM, Python 3.13, dask 2026.8.0, h5py 3.16.0, numpy 2.5.4)

New tests on PR #2's code, with tests/test_hdf5.py and tests/test_slicer.py taken from c6ffc771
(blobs 8ae4adcd / da4e29a0), `-k "registered_slice_composes or reads_only_requested_elements or
single_element or compose_reversed_slice_with_relative_stop or compose_expanded_slices"`:

    514dc33a  42 failed, 6 passed, 1 warning in 16.19s   (the 6: test_single_element_keeps_dtype[_over_http][squeezed-*])
    c6ffc771  48 passed, 1 warning in 15.03s

At c6ffc771:

    tests/test_hdf5.py                       95 passed, 1 warning in 47.93s
    tests/test_slicer.py tests/test_array.py 243 passed, 1 warning in 52.38s
    ruff 0.17.3: All checks passed! / 392 files already formatted

Rebased onto bluesky/tiled main 49fe22da (cc808fd6) vs unmodified main: see verify_rebase_c6ffc771.txt.
head_tests.json is the implementation worker's record (including test_zarr/test_writing runs).
