"""結果 JSON を、指定した「1 位−2 位」の閾値で数える（2 組目に 1 組目の閾値をそのまま使う用）。引数: TAG:閾値 ..."""
import json, os, sys, numpy as np
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp"))
for a in sys.argv[1:]:
    t, th = a.split(":"); th = float(th); d = json.load(open(f"{H}/res_{t}.json")); R = d["results"]
    pos = [r for r in R if r["positive"]]; neg = [r for r in R if not r["positive"]]
    hit = lambda r: r["top"] == r["src"] and r["pos_ok"] and r["score"] - r["second"] > th
    tfs = sorted({r["tf"] for r in pos}, key=lambda x: [r["tf"] for r in pos].index(x))
    print(f"{t} >{th:g}: 再現率 {np.mean([hit(r) for r in pos]):.2f} 誤検出 {sum(r['score'] - r['second'] > th for r in neg)}/{len(neg)} 負例の最高差 {max(r['score'] - r['second'] for r in neg):g}",
          " ".join(f"{k[:6]}={np.mean([hit(r) for r in pos if r['tf'] == k]):.2f}" for k in tfs),
          f" 検索中央値 {np.median([r['sec'] for r in R]) * 1000:.0f}ms DB {d['db_bytes'] / 1e6:.0f}MB")
