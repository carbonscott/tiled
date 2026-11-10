import json, sys, collections
c = collections.Counter(); ex = {}
for fn in sys.argv[1:]:
    for l in open(fn):
        m = json.loads(l)
        k = m["kind"]
        if k in ("read_type_differs", "block_type_differs"):
            cat = (k, m["head"].split(":")[1], m["pr2"].split(":")[1])
        elif k in ("read_head_vs_pr2", "block_head_vs_pr2", "structure_differs"):
            hn = m.get("head") == m.get("numpy") or (m.get("head","").split(":")[:2] == m.get("numpy","").split(":")[:2] and m.get("head","").split(":")[-1] == m.get("numpy","").split(":")[-1])
            cat = (k, "head==numpy" if hn else "head!=numpy", m.get("head","")[:30], m.get("pr2","")[:30])
        elif k in ("read_head_vs_numpy", "block_head_vs_numpy"):
            cat = (k, m["head"][:60], m["pr2"][:40], m["numpy"][:40], m["mode"])
        else:
            cat = (k,)
        c[cat] += 1; ex.setdefault(cat, m)
for k, v in c.most_common():
    m = ex[k]
    print(v, k)
    print("     e.g.", m["spec"]["shapes"], m["spec"]["storage"], m["spec"]["chunks"], "reg=", m["reg"], "sq=", m["squeeze"], m["mode"], m.get("structure"), m.get("block", ""), "req=", m.get("req"))
