"""検出器ごとの 1 枚あたりの時間と点の数（0.5 秒ごとのフレーム、1 スレッド）。time_fixed.py と同じクエリから 4 本"""
import json, os, sys, time
import numpy as np, cv2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from mimizam.src.video_fingerprinter import _create_akaze, normalize_frame
cv2.setNumThreads(1)
meta = json.load(open(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json"))); seen, pick = set(), []
for m in meta:
    k = (m["tf"], m["positive"])
    if k not in seen: seen.add(k); pick.append(m)
imgs = []
for m in pick[:4]:
    cap = cv2.VideoCapture(m["file"]); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fi = 0; nxt = 0.0
    while cap.grab():
        if fi / fps + 1e-6 >= nxt:
            ok, img = cap.retrieve()
            if ok: imgs.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)); nxt += 0.5
        fi += 1
    cap.release()
DET = {
    "AKAZE": _create_akaze,
    "ORB 1000": lambda: cv2.ORB.create(nfeatures=1000),
    "ORB 1000 (1 段)": lambda: cv2.ORB.create(nfeatures=1000, nlevels=1),
    "SIFT 1000": lambda: cv2.SIFT.create(nfeatures=1000),
}
for L in (960, 640):
    G = [normalize_frame(g, L, allow_upscale=True) for g in imgs]
    t0 = time.perf_counter(); [normalize_frame(g, L, allow_upscale=True) for g in imgs]; tn = (time.perf_counter() - t0) / len(imgs) * 1000
    print(f"== 長辺 {L}、{len(G)} 枚、縮小 {tn:.1f}ms/枚", flush=True)
    for name, mk in DET.items():
        d = mk(); d.detectAndCompute(G[0], None); n = []
        t0 = time.perf_counter()
        for g in G: k, _ = d.detectAndCompute(g, None); n.append(len(k))
        ms = (time.perf_counter() - t0) / len(G) * 1000
        print(f"{name:16s} {ms:6.1f}ms/枚  60 枚で {ms * 60 / 1000:.2f}s  点の数 中央値 {int(np.median(n))}", flush=True)
