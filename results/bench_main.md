| scenario | build | requested B/req | median h5py B/req | median warm ms | median cold ms | cold evictions verified | values equal |
|---|---|---:|---:|---:|---:|---:|---:|
| contiguous | base | 1.00 MiB | 1000.00 MiB | 196.6 | 558.8 | 20/20 | 40/40 |
| contiguous | pr2 | 1.00 MiB | 1.00 MiB | 32.0 | 34.0 | 20/20 | 40/40 |
| contiguous | head | 1.00 MiB | 1.00 MiB | 32.0 | 34.6 | 20/20 | 40/40 |
| chunks_many | base | 1.00 MiB | 64.00 MiB | 41.7 | 95.1 | 20/20 | 40/40 |
| chunks_many | pr2 | 1.00 MiB | 1.00 MiB | 32.0 | 35.7 | 20/20 | 40/40 |
| chunks_many | head | 1.00 MiB | 1.00 MiB | 32.0 | 35.5 | 20/20 | 40/40 |
| chunks_one | base | 1.00 MiB | 1.00 MiB | 32.4 | 35.8 | 20/20 | 40/40 |
| chunks_one | pr2 | 1.00 MiB | 1.00 MiB | 34.2 | 37.4 | 20/20 | 40/40 |
| chunks_one | head | 1.00 MiB | 1.00 MiB | 34.4 | 37.2 | 20/20 | 40/40 |
| compressed | base | 1.00 MiB | 1.00 MiB | 34.0 | 35.5 | 20/20 | 40/40 |
| compressed | pr2 | 1.00 MiB | 1.00 MiB | 35.4 | 37.2 | 20/20 | 40/40 |
| compressed | head | 1.00 MiB | 1.00 MiB | 35.3 | 37.1 | 20/20 | 40/40 |
| row_window | base | 800.0 B | 1000.00 MiB | 190.7 | 554.7 | 20/20 | 40/40 |
| row_window | pr2 | 800.0 B | 1.00 MiB | 25.5 | 27.4 | 20/20 | 40/40 |
| row_window | head | 800.0 B | 800.0 B | 24.9 | 26.4 | 20/20 | 40/40 |

20 cold + 20 warm requests per cell; rows (and windows) drawn with seed 12345, the same draws for every build. Builds ran one after another, each with its own server; cold = posix_fadvise(DONTNEED) on the file then mincore check; warm = the same request again right after. One unrecorded warm-up request per scenario.

base: sha=b7e1fea8570391852a52e06dada39397e24e2335 tiled=0.0.1.dev3631+gb7e1fea85 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
pr2: sha=514dc33a66430b053d1338801da19eb3154b993b tiled=0.0.1.dev3632+g514dc33a6 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
head: sha=421569c45edcb7cfdc8f7b47352a4a2a8cb3700c tiled=0.0.1.dev3634+g421569c45 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
