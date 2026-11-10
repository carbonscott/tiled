# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Final bench (head c6ffc771): head vs pr2 and head vs base, 8 scenarios x warm/cold.

Same rule as the v2 analysis (state/results/bench_v2_noise.py, section 4): bootstrap
(10000 resamples, each build's samples resampled independently) of median(head) -
median(other), 95% percentile CI; FASTER only if CI upper bound < 0 AND the gain
>= max(3.19 ms, 7.7% of the other build's median) (the v1->v2 drift floor).
Also: run-to-run drift of every build vs v2 (step .13), same draws; base and pr2 are
the same code in both runs, head moved 421569c4 -> c6ffc771.
Usage: uv run bench_final_noise.py bench_v2.json bench_final.json out.json
"""
import json, sys
import numpy as np

v2_path, fin_path, out_path = sys.argv[1:4]
v2, fin = json.load(open(v2_path)), json.load(open(fin_path))
B, FL_MS, FL_PCT = 10000, 3.19, 7.7

def groups(d):
    g = {}
    for x in d["samples"]:
        g.setdefault((x["build"], x["scenario"], x["temp"]), []).append(x)
    return g

g2, gf = groups(v2), groups(fin)
scen = list(dict.fromkeys(x["scenario"] for x in fin["samples"]))
ms = lambda g, k: np.array([x["ms"] for x in g[k]])

def boot(a, b, seed):  # verbatim from bench_v2_noise.py
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), (B, len(a)))
    ib = rng.integers(0, len(b), (B, len(b)))
    d = np.median(a[ia], axis=1) - np.median(b[ib], axis=1)
    return float(np.median(a) - np.median(b)), [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]

res = {"method": __doc__, "floor": {"ms": FL_MS, "pct": FL_PCT}, "compare": {}, "drift_vs_v2": {}}
same = {k: [x["request"] for x in gf[k]] == [x["request"] for x in g2[k]] for k in gf if k in g2}
res["same_requests_as_v2"] = f"{sum(same.values())}/{len(same)} cells"
L = [f"requests identical to v2 (step .13): {res['same_requests_as_v2']}", "",
     "| scenario | temp | vs | head med ms | other med ms | diff ms | diff % | 95% CI ms | floor ms | head faster? |",
     "|---|---|---|---:|---:|---:|---:|---|---:|---|"]
seed = 0
for sc in scen:
    for other in ("pr2", "base"):
        for t in ("warm", "cold"):
            seed += 1
            h, o = ms(gf, ("head", sc, t)), ms(gf, (other, sc, t))
            diff, ci = boot(h, o, seed)
            om = float(np.median(o)); floor = max(FL_MS, FL_PCT / 100 * om); pct = 100 * diff / om
            lo, hi = ci
            if hi < 0 and -diff >= floor: v = "FASTER"
            elif lo > 0 and diff >= floor: v = "SLOWER"
            elif hi < 0 or lo > 0: v = "no (CI excludes 0 but |diff| < floor)"
            else: v = "no (CI includes 0)"
            res["compare"][f"{other}|{t}|{sc}"] = {"head_ms": float(np.median(h)), "other_ms": om,
                "diff_ms": round(diff, 2), "pct": round(pct, 1), "ci95": [round(c, 2) for c in ci],
                "floor_ms": round(floor, 2), "verdict": v, "n": [len(h), len(o)]}
            L.append(f"| {sc} | {t} | {other} | {np.median(h):.1f} | {om:.1f} | {diff:+.2f} | {pct:+.1f}% "
                     f"| [{lo:+.2f}, {hi:+.2f}] | {floor:.2f} | {v} |")
L += ["", "## Drift vs v2 (step .13), same draws: final - v2", "",
      "| scenario | build | temp | v2 med ms | final med ms | final-v2 ms | % | 95% CI ms |", "|---|---|---|---:|---:|---:|---:|---|"]
for sc in scen:
    for b in ("base", "pr2", "head"):
        for t in ("warm", "cold"):
            seed += 1
            a2, af = ms(g2, (b, sc, t)), ms(gf, (b, sc, t))
            diff, ci = boot(af, a2, seed); pct = 100 * diff / float(np.median(a2))
            res["drift_vs_v2"][f"{b}|{t}|{sc}"] = {"v2_ms": float(np.median(a2)), "final_ms": float(np.median(af)),
                "diff_ms": round(diff, 2), "pct": round(pct, 1), "ci95": [round(c, 2) for c in ci]}
            L.append(f"| {sc} | {b} | {t} | {np.median(a2):.1f} | {np.median(af):.1f} | {diff:+.2f} | {pct:+.1f}% | [{ci[0]:+.2f}, {ci[1]:+.2f}] |")
for b in ("base", "pr2", "head"):
    d = [v for k, v in res["drift_vs_v2"].items() if k.startswith(b + "|")]
    s = {"cells": len(d), "max_abs_ms_small_cells(<100ms)": max(abs(v["diff_ms"]) for v in d if v["v2_ms"] < 100),
         "max_abs_pct": max(abs(v["pct"]) for v in d), "median_abs_ms": float(np.median([abs(v["diff_ms"]) for v in d]))}
    res["drift_vs_v2"][f"summary|{b}"] = s
    L.append(f"\ndrift summary {b}: {s}")
print("\n".join(L))
json.dump(res, open(out_path, "w"), indent=1)
