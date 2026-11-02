import json, os, sys, glob
import numpy as np
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp"))
def auc(p, n):
    p, n = np.array(p), np.array(n)
    return float(((p[:, None] > n[None]).sum() + 0.5 * (p[:, None] == n[None]).sum()) / (len(p) * len(n)))
rows = []
for f in sorted(glob.glob(f"{H}/res_*.json")):
    r = json.load(open(f)); R = r["results"]
    pos = [x for x in R if x["positive"]]; neg = [x for x in R if not x["positive"]]
    ok = lambda x: x["top"] == x["src"] and x["pos_ok"]
    nmax = max(x["score"] for x in neg)
    # 正例の「正しい映像・位置で、かつ負例の最高点を超えた」割合（誤検出 0 の閾値での再現率）
    tpr0 = np.mean([ok(x) and x["score"] > nmax for x in pos])
    sp = [x["score"] if ok(x) else 0.0 for x in pos]; sn = [x["score"] for x in neg]
    fp_sys = np.mean([x["top"] is not None for x in neg])
    tfs = sorted({x["tf"] for x in pos})
    per = {t: np.mean([ok(x) for x in pos if x["tf"] == t]) for t in tfs}
    per0 = {t: np.mean([ok(x) and x["score"] > nmax for x in pos if x["tf"] == t]) for t in tfs}
    line = dict(v=r["variant"], top1=np.mean([ok(x) for x in pos]), tpr_fp0=tpr0, auc=auc(sp, sn), neg_hit=fp_sys,
                q_ms=1000 * np.median([x["sec"] for x in R]), db_mb=r["db_bytes"] / 1e6, per=per, per0=per0)
    if "ann_top" in R[0]:
        line["ann_top1"] = np.mean([x["ann_top"] == x["src"] for x in pos])
        line["ann_auc"] = auc([x["ann_score"] if x["ann_top"] == x["src"] else 0 for x in pos], [x["ann_score"] for x in neg])
    rows.append(line)
for l in rows:
    print(f'{l["v"]:5s} top1={l["top1"]:.2f} TPR@FP0={l["tpr_fp0"]:.2f} AUC={l["auc"]:.3f} 負例で何か返す={l["neg_hit"]:.2f} '
          f'q={l["q_ms"]:.0f}ms DB={l["db_mb"]:.1f}MB' + (f' | ANNのみ top1={l["ann_top1"]:.2f} AUC={l["ann_auc"]:.3f}' if "ann_top1" in l else ""))
print("変換別 top1 / TPR@FP0")
tfs = list(rows[0]["per"])
print("      " + " ".join(f"{t[:9]:>11s}" for t in tfs))
for l in rows:
    print(f'{l["v"]:5s} ' + " ".join(f'{l["per"][t]:.2f}/{l["per0"][t]:.2f}'.rjust(11) for t in tfs))
