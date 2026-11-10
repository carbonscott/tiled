"""Property test of NDSlice composition (tiled.ndslice.compose_slices) against numpy.

Run with either tree's python: python -I compose_prop.py --examples N --seed S --mode {expanded,raw,zarr}
  expanded: left = expand_for_shape(random, shape[, squeeze]); right = expand_for_shape(random, left result shape)
  raw:      left as above; right = raw random index (ints, any slices, Ellipsis) -- as ZarrArrayAdapter passes
  zarr:     left = (slice(0, n), ...) exactly as ZarrArrayAdapter._stencil; right = raw random index
Reports counts of: equal, composition raised, wrong result.
"""

import argparse
import collections
import sys

import numpy as np
from hypothesis import HealthCheck, given, seed, settings
from hypothesis import strategies as st

from tiled.ndslice import NDSlice

ap = argparse.ArgumentParser()
ap.add_argument("--examples", type=int, default=2000)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--mode", default="expanded")
ap.add_argument("--squeeze", action="store_true")
args = ap.parse_args()

C = collections.Counter()
EX = {}


def idx(draw, shape, allow_oob=False):
    out = []
    for n in shape:
        k = draw(st.sampled_from(["full", "int", "slice", "slice", "slice"]))
        lim = n + 2
        if k == "full":
            out.append(slice(None))
        elif k == "int":
            if n == 0:
                out.append(slice(None))
            else:
                out.append(draw(st.integers(-n, n - 1)))
        else:
            b = st.one_of(st.none(), st.integers(-lim, lim))
            out.append(slice(draw(b), draw(b), draw(st.sampled_from([None, 1, 2, 3, -1, -2, -3, -5]))))
    if draw(st.integers(0, 3)) == 0:
        pos = draw(st.integers(0, len(out)))
        drop = draw(st.integers(0, len(out) - pos))
        out = out[:pos] + [Ellipsis] + out[pos + drop :]
    elif out and draw(st.booleans()):
        out = out[: draw(st.integers(0, len(out)))]
    return tuple(out)


@seed(args.seed)
@settings(max_examples=args.examples, deadline=None, database=None, suppress_health_check=list(HealthCheck))
@given(st.data())
def prop(data):
    ndim = data.draw(st.integers(1, 4))
    shape = tuple(data.draw(st.sampled_from([0, 1, 1, 2, 3, 5, 7])) for _ in range(ndim))
    arr = np.arange(int(np.prod(shape))).reshape(shape)
    if args.mode == "zarr":
        left = NDSlice(*(slice(0, n) for n in shape))
        mid = arr[tuple(left)]
    else:
        raw_left = idx(data.draw, shape)
        try:
            if args.squeeze:
                left = NDSlice(*raw_left).expand_for_shape(shape, squeeze=True)
            else:
                left = NDSlice(*raw_left).expand_for_shape(shape)
        except TypeError:
            # PR #2 has no squeeze option
            C["no_squeeze_option"] += 1
            return
        mid = arr[tuple(raw_left)]
        if args.squeeze:
            mid = np.squeeze(mid)
        assert np.array_equal(arr[tuple(left)], mid), (shape, raw_left, left)
    raw_right = idx(data.draw, mid.shape)
    if args.mode == "expanded":
        right = NDSlice(*raw_right).expand_for_shape(mid.shape)
    else:
        right = NDSlice(*raw_right)
    expected = mid[tuple(raw_right)]
    try:
        comp = left[right]
    except Exception as e:
        key = ("raised", type(e).__name__, str(e)[:60])
        C[key] += 1
        EX.setdefault(key, (shape, left, right))
        return
    try:
        got = arr[tuple(comp)]
    except Exception as e:
        key = ("composed index invalid", type(e).__name__)
        C[key] += 1
        EX.setdefault(key, (shape, left, right, comp))
        return
    if got.shape == expected.shape and np.array_equal(got, expected):
        C["equal"] += 1
    else:
        key = ("WRONG",)
        C[key] += 1
        EX.setdefault(key, (shape, left, right, comp, got.shape, expected.shape))


prop()
for k, v in C.most_common():
    print(v, k, EX.get(k, ""))
