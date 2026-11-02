"""クエリ 1 本の AKAZE を、フレームごとに N スレッドへ分けたときの時間（time_fixed.py と同じ 10 本）"""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
os.environ.setdefault("LONG", "960")
from extract_fixed import akaze_frame, LONG
from mimizam.src.video_fingerprinter import _create_akaze
N = int(os.environ.get("N", 8)); cv2.setNumThreads(1); loc = threading.local()
def one(img):
    if not hasattr(loc, "a"): loc.a = _create_akaze()
    return akaze_frame(loc.a, img)
meta = json.load(open(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json"))); seen, pick = set(), []
for m in meta:
    k = (m["tf"], m["positive"])
    if k not in seen: seen.add(k); pick.append(m)
R = []; ex = ThreadPoolExecutor(N)
for m in pick[:10]:
    cap = cv2.VideoCapture(m["file"]); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; imgs = []; fi = 0; nxt = 0.0
    while cap.grab():
        if fi / fps + 1e-6 >= nxt:
            ok, img = cap.retrieve()
            if ok: imgs.append(img); nxt += 0.5
        fi += 1
    cap.release(); t0 = time.perf_counter(); r = list(ex.map(one, imgs)); R.append(time.perf_counter() - t0)
print("長辺", LONG, "スレッド", N, "AKAZE 全面の中央値 %.2fs" % np.median(R))
