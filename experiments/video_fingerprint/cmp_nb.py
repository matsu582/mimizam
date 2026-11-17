"""numpy 版と numba 版の全件結果が同じか、速度と内訳を比べる"""
import json, sys, numpy as np
a, b = (json.load(open(f"res_{t}.json")) for t in sys.argv[1:3])
A = {x["name"]: x for x in a["results"]}
same = sum(all(A[x["name"]][k] == x[k] for k in ("top", "score", "second", "pos_ok", "off") if k in A[x["name"]]) for x in b["results"])
print(f"一致 {same}/{len(b['results'])}")
for t, d in ((sys.argv[1], a), (sys.argv[2], b)):
    s = np.array([x["sec"] for x in d["results"]]) * 1000
    print(f"{t}: p50/p95 {np.median(s):.0f}/{np.percentile(s, 95):.0f}ms 合計 {s.sum() / 1000:.0f}s 内訳 " + " ".join(f"{k}={v:.0f}s" for k, v in d["T"].items() if v))
