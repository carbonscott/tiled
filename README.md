# Proof material for the HDF5 composed-slice PR

Not code for review. This orphan branch holds the scripts and media that prove the
follow-up to carbonscott/tiled#2 works (issue carbonscott/tiled#3).

- `proof/issue_repro.py`: counts the bytes h5py returns for three requests (the issue's reproduction).
- `proof/tiled_e2e.py`: end-to-end matrix and benchmark through a live `tiled serve`, for three builds.
- `proof/compare_test_instance.py`: serves real datasets from their source HDF5 files and compares them with a remote Tiled instance.
- `media/`: screenshots and recordings of the proof running.
