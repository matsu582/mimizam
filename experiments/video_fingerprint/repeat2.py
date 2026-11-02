"""点の数を変えたときの AKAZE 点の再現率（元フレームの上位 N 点のうち、クエリの上位 N 点に同じ場所の点がある割合）"""
import json, os, sys, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))  # mimizam の親
from mimizam.src.video_fingerprinter import normalize_frame, _create_akaze
S = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/src"); Q = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q")
meta = {os.path.basename(m["file"])[:-4]: m for m in json.load(open(f"{Q}/meta.json"))}
ak = _create_akaze(); NS = [150, 500, 2000, 10**9]
def grab(path, t):
    cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); cap.release(); return f
def feats(img):
    g = normalize_frame(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 1280, allow_upscale=True)
    k, d = ak.detectAndCompute(g, None); o = np.argsort([-x.response for x in k])
    return np.array([k[i].pt for i in o]), d[o]
for src, ext in [("sintel", "mp4"), ("bbb", "mp4"), ("tos", "mov")]:
    for tf in ["aspect43_text", "reenc480"]:
        m = meta[f"{src}_0_{tf}"]; rows = []
        for t in (5.0, 12.0, 20.0):
            pa, da = feats(grab(f"{S}/{src}.{ext}", m["start"] + t)); pb, db = feats(grab(m["file"], t))
            mm = [x for x, y in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2) if x.distance < 0.8 * y.distance]
            Hm, inl = cv2.findHomography(pa[[x.queryIdx for x in mm]], pb[[x.trainIdx for x in mm]], cv2.RANSAC, 5.0)
            pt = cv2.perspectiveTransform(pa.reshape(-1, 1, 2), Hm).reshape(-1, 2)
            r = []
            for n in NS:
                a, b = pt[:n], pb[:n]
                near = np.array([np.min(np.linalg.norm(b - x, axis=1)) < 4 for x in a])
                r.append((near.mean(), near.sum()))
            rows.append((len(pa), len(pb), r))
        na = np.mean([x[0] for x in rows]); nb = np.mean([x[1] for x in rows])
        cells = "  ".join(f"N={'全部' if n > 1e8 else n}: {np.mean([x[2][i][0] for x in rows]):.2f}（{np.mean([x[2][i][1] for x in rows]):.0f} 点）" for i, n in enumerate(NS))
        print(f"{src:7s} {tf:14s} 検出数 元 {na:.0f} / クエリ {nb:.0f}  {cells}", flush=True)
