"""B3 系の結果を、その組での誤検出 0 の閾値と、1 組目で決めた閾値（票数 >19・1位−2位 >5）の両方で集計する"""
import json, sys, numpy as np
TF = ["reenc480", "low240", "crop70", "color", "rot10", "aspect43_text", "pip_half", "pip_third"]
for tag in sys.argv[1:]:
    R = json.load(open(f"res_{tag}.json"))["results"]; s = [x["sec"] for x in R]
    pos = [x for x in R if x["positive"]]; neg = [x for x in R if not x["positive"]]
    print(f"{tag}: 正例 {len(pos)} 負例 {len(neg)} 正解率 {np.mean([x['top'] == x['src'] and x['pos_ok'] for x in pos]):.2f}  q p50/p95 {np.median(s)*1000:.0f}/{np.percentile(s, 95)*1000:.0f}ms")
    for nm, f, fixed in [("票数", lambda x: x["score"], 19), ("1位−2位", lambda x: x["score"] - x["second"], 5)]:
        th = max(f(x) for x in neg)
        for lab, t in [("この組で FP0", th), ("1 組目の閾値", fixed)]:
            ok = lambda x: x["top"] == x["src"] and x["pos_ok"] and f(x) > t
            fp = sum(f(x) > t for x in neg)
            print(f"  {nm} {lab}（>{t:.0f}）: 再現率 {np.mean([ok(x) for x in pos]):.2f}  誤検出 {fp}/{len(neg)}  " + " ".join(f"{tf[:6]}={np.mean([ok(x) for x in pos if x['tf'] == tf]):.2f}" for tf in TF))
