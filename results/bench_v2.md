| scenario | request | build | requested B/req | median h5py B/req | median warm ms | median cold ms | cold evictions verified | values equal |
|---|---|---|---:|---:|---:|---:|---:|---:|
| contiguous | b_contiguous-whole[i] | base | 1.00 MiB | 1000.00 MiB | 196.7 | 558.0 | 20/20 | 40/40 |
| contiguous | b_contiguous-whole[i] | pr2 | 1.00 MiB | 1.00 MiB | 31.8 | 34.7 | 20/20 | 40/40 |
| contiguous | b_contiguous-whole[i] | head | 1.00 MiB | 1.00 MiB | 31.8 | 34.6 | 20/20 | 40/40 |
| chunks_many | b_chunks_many-whole[i] | base | 1.00 MiB | 64.00 MiB | 44.9 | 94.5 | 20/20 | 40/40 |
| chunks_many | b_chunks_many-whole[i] | pr2 | 1.00 MiB | 1.00 MiB | 31.7 | 34.2 | 20/20 | 40/40 |
| chunks_many | b_chunks_many-whole[i] | head | 1.00 MiB | 1.00 MiB | 32.0 | 34.2 | 20/20 | 40/40 |
| chunks_one | b_chunks_one-whole[i] | base | 1.00 MiB | 1.00 MiB | 33.6 | 36.5 | 20/20 | 40/40 |
| chunks_one | b_chunks_one-whole[i] | pr2 | 1.00 MiB | 1.00 MiB | 32.6 | 35.2 | 20/20 | 40/40 |
| chunks_one | b_chunks_one-whole[i] | head | 1.00 MiB | 1.00 MiB | 33.7 | 36.3 | 20/20 | 40/40 |
| compressed | b_compressed-whole[i] | base | 1.00 MiB | 1.00 MiB | 35.1 | 36.9 | 20/20 | 40/40 |
| compressed | b_compressed-whole[i] | pr2 | 1.00 MiB | 1.00 MiB | 34.7 | 36.2 | 20/20 | 40/40 |
| compressed | b_compressed-whole[i] | head | 1.00 MiB | 1.00 MiB | 35.1 | 36.8 | 20/20 | 40/40 |
| row_window | b_contiguous-row[j:j+10,k:k+10] | base | 800.0 B | 1000.00 MiB | 189.2 | 534.0 | 20/20 | 40/40 |
| row_window | b_contiguous-row[j:j+10,k:k+10] | pr2 | 800.0 B | 1.00 MiB | 24.7 | 27.7 | 20/20 | 40/40 |
| row_window | b_contiguous-row[j:j+10,k:k+10] | head | 800.0 B | 800.0 B | 25.1 | 26.4 | 20/20 | 40/40 |
| reversed_contiguous | b_contiguous-whole[i,::-1] | base | 1.00 MiB | 1000.00 MiB | 195.9 | 540.7 | 20/20 | 40/40 |
| reversed_contiguous | b_contiguous-whole[i,::-1] | pr2 | 1.00 MiB | 1000.00 MiB | 196.9 | 542.7 | 20/20 | 40/40 |
| reversed_contiguous | b_contiguous-whole[i,::-1] | head | 1.00 MiB | 1.00 MiB | 32.7 | 35.7 | 20/20 | 40/40 |
| reversed_chunks_many | b_chunks_many-whole[i,::-1] | base | 1.00 MiB | 64.00 MiB | 43.5 | 91.9 | 20/20 | 40/40 |
| reversed_chunks_many | b_chunks_many-whole[i,::-1] | pr2 | 1.00 MiB | 64.00 MiB | 42.3 | 92.6 | 20/20 | 40/40 |
| reversed_chunks_many | b_chunks_many-whole[i,::-1] | head | 1.00 MiB | 1.00 MiB | 32.6 | 35.7 | 20/20 | 40/40 |
| big_row_window | b_big_contiguous-row[j:j+10,k:k+10] | base | 800.0 B | 1.00 GiB | 191.6 | 550.1 | 20/20 | 40/40 |
| big_row_window | b_big_contiguous-row[j:j+10,k:k+10] | pr2 | 800.0 B | 64.00 MiB | 35.8 | 87.2 | 20/20 | 40/40 |
| big_row_window | b_big_contiguous-row[j:j+10,k:k+10] | head | 800.0 B | 800.0 B | 25.3 | 30.7 | 20/20 | 40/40 |

20 cold + 20 warm requests per cell; entities i (and windows j, k) drawn with seed 12345, the same draws for every build. Builds ran one after another, each with its own server; cold = posix_fadvise(DONTNEED) on the file then mincore check; warm = the same request again right after. One unrecorded warm-up request per scenario. A request is node[selection]; '-whole' nodes are the whole stack, '-row' nodes one entity registered with the `slice` parameter.

- contiguous: b_contiguous.h5 (contiguous, 1000x256x512 float64, Dask chunks of 1000x256x512); node = the whole stack; request arr[i]
- chunks_many: b_chunks_many.h5 (chunks_many, 1000x256x512 float64, Dask chunks of 64x256x512); node = the whole stack; request arr[i]
- chunks_one: b_chunks_one.h5 (chunks_one, 1000x256x512 float64, Dask chunks of 1x256x512); node = the whole stack; request arr[i]
- compressed: b_compressed.h5 (compressed, 1000x256x512 float64, Dask chunks of 1x256x512); node = the whole stack; request arr[i]
- row_window: b_contiguous.h5 (contiguous, 1000x256x512 float64, Dask chunks of 1000x256x512); node = row 503; request arr[j:j+10,k:k+10]
- reversed_contiguous: b_contiguous.h5 (contiguous, 1000x256x512 float64, Dask chunks of 1000x256x512); node = the whole stack; request arr[i,::-1]
- reversed_chunks_many: b_chunks_many.h5 (chunks_many, 1000x256x512 float64, Dask chunks of 64x256x512); node = the whole stack; request arr[i,::-1]
- big_row_window: b_big_contiguous.h5 (contiguous, 16x4096x2048 float64, Dask chunks of 16x4096x2048); node = row 11; request arr[j:j+10,k:k+10]

base: sha=b7e1fea8570391852a52e06dada39397e24e2335 tiled=0.0.1.dev3631+gb7e1fea85 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
pr2: sha=514dc33a66430b053d1338801da19eb3154b993b tiled=0.0.1.dev3632+g514dc33a6 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
head: sha=421569c45edcb7cfdc8f7b47352a4a2a8cb3700c tiled=0.0.1.dev3634+g421569c45 dask=2026.8.0 h5py=3.16.0 hdf5=2.0.0 numpy=2.5.4 python=3.12.12 host=sdfmilan125
