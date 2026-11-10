requests identical to v2 (step .13): 48/48 cells

| scenario | temp | vs | head med ms | other med ms | diff ms | diff % | 95% CI ms | floor ms | head faster? |
|---|---|---|---:|---:|---:|---:|---|---:|---|
| contiguous | warm | pr2 | 32.0 | 31.6 | +0.35 | +1.1% | [-0.03, +1.27] | 3.19 | no (CI includes 0) |
| contiguous | cold | pr2 | 35.6 | 34.9 | +0.74 | +2.1% | [-0.11, +2.00] | 3.19 | no (CI includes 0) |
| contiguous | warm | base | 32.0 | 196.4 | -164.38 | -83.7% | [-165.88, -162.88] | 15.12 | FASTER |
| contiguous | cold | base | 35.6 | 564.5 | -528.94 | -93.7% | [-532.60, -524.73] | 43.47 | FASTER |
| chunks_many | warm | pr2 | 32.5 | 31.6 | +0.92 | +2.9% | [+0.25, +1.37] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| chunks_many | cold | pr2 | 35.5 | 34.2 | +1.32 | +3.9% | [+0.19, +2.16] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| chunks_many | warm | base | 32.5 | 44.7 | -12.26 | -27.4% | [-13.29, -11.70] | 3.44 | FASTER |
| chunks_many | cold | base | 35.5 | 100.4 | -64.90 | -64.7% | [-66.63, -63.16] | 7.73 | FASTER |
| chunks_one | warm | pr2 | 34.1 | 32.6 | +1.50 | +4.6% | [+1.05, +1.94] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| chunks_one | cold | pr2 | 37.4 | 35.7 | +1.69 | +4.7% | [+1.10, +2.38] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| chunks_one | warm | base | 34.1 | 33.3 | +0.77 | +2.3% | [+0.26, +1.35] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| chunks_one | cold | base | 37.4 | 36.4 | +1.06 | +2.9% | [+0.21, +1.76] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| compressed | warm | pr2 | 35.7 | 34.5 | +1.25 | +3.6% | [+0.71, +1.79] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| compressed | cold | pr2 | 37.9 | 36.1 | +1.80 | +5.0% | [+1.40, +2.50] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| compressed | warm | base | 35.7 | 35.0 | +0.69 | +2.0% | [+0.36, +1.09] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| compressed | cold | base | 37.9 | 37.0 | +0.90 | +2.4% | [-0.62, +1.62] | 3.19 | no (CI includes 0) |
| row_window | warm | pr2 | 25.4 | 24.9 | +0.55 | +2.2% | [+0.15, +1.11] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| row_window | cold | pr2 | 26.6 | 28.1 | -1.50 | -5.3% | [-1.82, -0.72] | 3.19 | no (CI excludes 0 but |diff| < floor) |
| row_window | warm | base | 25.4 | 192.7 | -167.32 | -86.8% | [-168.93, -165.51] | 14.84 | FASTER |
| row_window | cold | base | 26.6 | 559.5 | -532.91 | -95.2% | [-535.01, -530.97] | 43.08 | FASTER |
| reversed_contiguous | warm | pr2 | 32.8 | 195.5 | -162.71 | -83.2% | [-163.44, -161.49] | 15.05 | FASTER |
| reversed_contiguous | cold | pr2 | 36.0 | 552.5 | -516.51 | -93.5% | [-518.91, -513.83] | 42.54 | FASTER |
| reversed_contiguous | warm | base | 32.8 | 197.5 | -164.74 | -83.4% | [-165.34, -164.13] | 15.21 | FASTER |
| reversed_contiguous | cold | base | 36.0 | 565.0 | -528.99 | -93.6% | [-533.72, -524.47] | 43.50 | FASTER |
| reversed_chunks_many | warm | pr2 | 32.8 | 44.5 | -11.75 | -26.4% | [-12.33, -11.16] | 3.43 | FASTER |
| reversed_chunks_many | cold | pr2 | 36.4 | 101.6 | -65.14 | -64.1% | [-67.86, -60.72] | 7.82 | FASTER |
| reversed_chunks_many | warm | base | 32.8 | 43.8 | -10.97 | -25.1% | [-11.35, -10.47] | 3.37 | FASTER |
| reversed_chunks_many | cold | base | 36.4 | 95.3 | -58.88 | -61.8% | [-61.07, -56.89] | 7.34 | FASTER |
| big_row_window | warm | pr2 | 25.3 | 38.6 | -13.27 | -34.4% | [-13.84, -12.86] | 3.19 | FASTER |
| big_row_window | cold | pr2 | 31.2 | 94.8 | -63.62 | -67.1% | [-65.66, -62.20] | 7.30 | FASTER |
| big_row_window | warm | base | 25.3 | 195.6 | -170.27 | -87.1% | [-172.92, -169.39] | 15.06 | FASTER |
| big_row_window | cold | base | 31.2 | 581.9 | -550.72 | -94.6% | [-558.72, -544.87] | 44.81 | FASTER |

## Drift vs v2 (step .13), same draws: final - v2

| scenario | build | temp | v2 med ms | final med ms | final-v2 ms | % | 95% CI ms |
|---|---|---|---:|---:|---:|---:|---|
| contiguous | base | warm | 196.7 | 196.4 | -0.30 | -0.2% | [-2.06, +1.48] |
| contiguous | base | cold | 558.0 | 564.5 | +6.57 | +1.2% | [-17.86, +16.90] |
| contiguous | pr2 | warm | 31.8 | 31.6 | -0.18 | -0.6% | [-0.80, +0.36] |
| contiguous | pr2 | cold | 34.7 | 34.9 | +0.19 | +0.5% | [-1.46, +1.11] |
| contiguous | head | warm | 31.8 | 32.0 | +0.18 | +0.6% | [-0.17, +1.03] |
| contiguous | head | cold | 34.6 | 35.6 | +0.95 | +2.7% | [+0.23, +1.82] |
| chunks_many | base | warm | 44.9 | 44.7 | -0.13 | -0.3% | [-0.82, +0.62] |
| chunks_many | base | cold | 94.5 | 100.4 | +5.84 | +6.2% | [+3.95, +7.47] |
| chunks_many | pr2 | warm | 31.7 | 31.6 | -0.11 | -0.3% | [-0.61, +0.31] |
| chunks_many | pr2 | cold | 34.2 | 34.2 | -0.01 | -0.0% | [-0.56, +1.00] |
| chunks_many | head | warm | 32.0 | 32.5 | +0.44 | +1.4% | [-0.45, +1.12] |
| chunks_many | head | cold | 34.2 | 35.5 | +1.24 | +3.6% | [+0.26, +2.24] |
| chunks_one | base | warm | 33.6 | 33.3 | -0.28 | -0.8% | [-0.76, +0.23] |
| chunks_one | base | cold | 36.5 | 36.4 | -0.10 | -0.3% | [-0.76, +0.71] |
| chunks_one | pr2 | warm | 32.6 | 32.6 | +0.01 | +0.0% | [-0.60, +0.55] |
| chunks_one | pr2 | cold | 35.2 | 35.7 | +0.49 | +1.4% | [-0.12, +1.26] |
| chunks_one | head | warm | 33.7 | 34.1 | +0.40 | +1.2% | [-0.28, +0.88] |
| chunks_one | head | cold | 36.3 | 37.4 | +1.16 | +3.2% | [+0.56, +1.91] |
| compressed | base | warm | 35.1 | 35.0 | -0.12 | -0.3% | [-0.44, +0.22] |
| compressed | base | cold | 36.9 | 37.0 | +0.13 | +0.4% | [-0.29, +1.69] |
| compressed | pr2 | warm | 34.7 | 34.5 | -0.21 | -0.6% | [-0.75, +0.51] |
| compressed | pr2 | cold | 36.2 | 36.1 | -0.05 | -0.1% | [-0.48, +0.23] |
| compressed | head | warm | 35.1 | 35.7 | +0.60 | +1.7% | [+0.06, +0.94] |
| compressed | head | cold | 36.8 | 37.9 | +1.14 | +3.1% | [+0.57, +1.76] |
| row_window | base | warm | 189.2 | 192.7 | +3.48 | +1.8% | [+0.75, +5.61] |
| row_window | base | cold | 534.0 | 559.5 | +25.47 | +4.8% | [+22.72, +28.04] |
| row_window | pr2 | warm | 24.7 | 24.9 | +0.19 | +0.8% | [-0.49, +0.62] |
| row_window | pr2 | cold | 27.7 | 28.1 | +0.40 | +1.4% | [-0.53, +0.94] |
| row_window | head | warm | 25.1 | 25.4 | +0.29 | +1.1% | [-0.26, +0.92] |
| row_window | head | cold | 26.4 | 26.6 | +0.17 | +0.6% | [-0.36, +0.52] |
| reversed_contiguous | base | warm | 195.9 | 197.5 | +1.61 | +0.8% | [-0.77, +2.73] |
| reversed_contiguous | base | cold | 540.7 | 565.0 | +24.24 | +4.5% | [+19.23, +29.00] |
| reversed_contiguous | pr2 | warm | 196.9 | 195.5 | -1.41 | -0.7% | [-3.02, +0.26] |
| reversed_contiguous | pr2 | cold | 542.7 | 552.5 | +9.79 | +1.8% | [+5.76, +14.21] |
| reversed_contiguous | head | warm | 32.7 | 32.8 | +0.10 | +0.3% | [-0.35, +0.65] |
| reversed_contiguous | head | cold | 35.7 | 36.0 | +0.27 | +0.8% | [-0.53, +1.35] |
| reversed_chunks_many | base | warm | 43.5 | 43.8 | +0.25 | +0.6% | [-1.06, +1.57] |
| reversed_chunks_many | base | cold | 91.9 | 95.3 | +3.44 | +3.7% | [+1.05, +5.96] |
| reversed_chunks_many | pr2 | warm | 42.3 | 44.5 | +2.23 | +5.3% | [+1.21, +2.92] |
| reversed_chunks_many | pr2 | cold | 92.6 | 101.6 | +8.97 | +9.7% | [+3.60, +12.37] |
| reversed_chunks_many | head | warm | 32.6 | 32.8 | +0.20 | +0.6% | [-0.43, +0.95] |
| reversed_chunks_many | head | cold | 35.7 | 36.4 | +0.70 | +2.0% | [+0.08, +2.15] |
| big_row_window | base | warm | 191.6 | 195.6 | +4.03 | +2.1% | [+1.58, +6.87] |
| big_row_window | base | cold | 550.1 | 581.9 | +31.81 | +5.8% | [+25.11, +40.03] |
| big_row_window | pr2 | warm | 35.8 | 38.6 | +2.75 | +7.7% | [+2.07, +3.29] |
| big_row_window | pr2 | cold | 87.2 | 94.8 | +7.68 | +8.8% | [+5.90, +9.89] |
| big_row_window | head | warm | 25.3 | 25.3 | +0.06 | +0.2% | [-0.31, +0.59] |
| big_row_window | head | cold | 30.7 | 31.2 | +0.52 | +1.7% | [-0.31, +0.78] |

drift summary base: {'cells': 16, 'max_abs_ms_small_cells(<100ms)': 5.84, 'max_abs_pct': 6.2, 'median_abs_ms': 2.525}

drift summary pr2: {'cells': 16, 'max_abs_ms_small_cells(<100ms)': 8.97, 'max_abs_pct': 9.7, 'median_abs_ms': 0.305}

drift summary head: {'cells': 16, 'max_abs_ms_small_cells(<100ms)': 1.24, 'max_abs_pct': 3.6, 'median_abs_ms': 0.42000000000000004}
