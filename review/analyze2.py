import json, sys, collections
def st(r):  # status:type
    if not r: return r
    p = r.split(":")
    return p[0] + ":" + p[1]
def shape(r):
    return r.rsplit(":", 1)[-1] if r.startswith("ok") else ""
c = collections.Counter(); ex = {}
for fn in sys.argv[1:]:
    for l in open(fn):
        m = json.loads(l)
        k = m["kind"]
        h, p, n = m.get("head", ""), m.get("pr2", ""), m.get("numpy", "")
        if k.endswith("type_differs"):
            cat = ("TYPE", k, h.split(":")[1] == "ndarray", p.split(":")[1] == "ndarray")
        elif k == "structure_differs":
            cat = ("STRUCT",)
        elif k.endswith("head_vs_pr2"):
            head_ok = (st(h) == st(n) and shape(h) == shape(n)) if h.startswith("ok") else n.startswith("err")
            cat = ("H!=P", k.split("_")[0], "head matches numpy" if head_ok else "HEAD WRONG", st(h), st(p), m["mode"] if not head_ok else "")
        elif k.endswith("head_vs_numpy"):
            same_as_pr2 = h[:80] == p[:80] or (h.split(":")[:2] == p.split(":")[:2])
            cat = ("H!=N", k.split("_")[0], "same as pr2" if same_as_pr2 else "DIFFERENT FROM PR2", st(h), st(n), m["mode"])
        else:
            cat = (k,)
        c[cat] += 1; ex.setdefault(cat, m)
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    m = ex[k]
    print(v, k)
    print("     e.g.", m["spec"]["shapes"], m["spec"]["storage"], m["spec"]["chunks"], "reg=", m["reg"], "sq=", m["squeeze"], m["mode"], m.get("structure"), m.get("block", ""), "req=", m.get("req"), "| H", m.get("head", "")[:90], "| P", m.get("pr2", "")[:90], "| N", m.get("numpy", "")[:60])
