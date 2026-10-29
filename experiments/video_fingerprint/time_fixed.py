"""クエリ 1 本あたりの抽出時間（0.5 秒ごとのフレームの読み出し・AKAZE 全面）を 1 スレッドで測る。time_extract.py と同じ 10 本"""
import json, os, sys, time
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
os.environ.setdefault("LONG", "1280")
from extract_fixed import akaze_frame, LONG
from mimizam.src.video_fingerprinter import _create_akaze
STEP = float(os.environ.get("STEP", 0.5))
cv2.setNumThreads(1); akaze = _create_akaze()
meta = json.load(open(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json")))
seen, pick = set(), []
for m in meta:
    k = (m["tf"], m["positive"])
    if k not in seen: seen.add(k); pick.append(m)
R = []
for m in pick[:10]:
    t0 = time.perf_counter(); cap = cv2.VideoCapture(m["file"]); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; imgs = []; fi = 0; nxt = 0.0
    while cap.grab():
        if fi / fps + 1e-6 >= nxt:
            ok, img = cap.retrieve()
            if ok: imgs.append(img); nxt += STEP
        fi += 1
    cap.release(); t1 = time.perf_counter()
    for img in imgs: akaze_frame(akaze, img)
    t2 = time.perf_counter(); R.append((len(imgs), t1 - t0, t2 - t1)); print(os.path.basename(m["file"]), *("%.2f" % x for x in R[-1]), flush=True)
a = np.array(R); print("長辺 %d 中央値 frames=%d 読み出し %.2fs AKAZE 全面 %.2fs" % tuple([LONG, np.median(a[:, 0])] + list(np.median(a[:, 1:], 0))))
