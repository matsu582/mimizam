"""幅 1/2 の PiP: DB フレームの上位 1000 点のうち、クエリ側で同じ場所に点が出る割合（クエリの点の取り方別）"""
import json, os, sys, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))  # mimizam の親
from mimizam.src.video_fingerprinter import normalize_frame, _create_akaze
S = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/src"); Q = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q")
meta = {os.path.basename(m["file"])[:-4]: m for m in json.load(open(f"{Q}/meta.json"))}
ak = _create_akaze()
def grab(path, t):
    cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); cap.release(); return f
def feats(img):
    g = normalize_frame(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 1280, allow_upscale=True)
    k, d = ak.detectAndCompute(g, None); o = np.argsort([-x.response for x in k])
    return np.array([k[i].pt for i in o]), d[o], g.shape
for src, ext in [("sintel", "mp4"), ("bbb", "mp4"), ("tos", "mov")]:
    m = meta[f"{src}_0_pip_half"]; rows = []
    for t in (5.0, 12.0, 20.0):
        fd = grab(f"{S}/{src}.{ext}", m["start"] + t); fq = grab(m["file"], t)
        pa, da, sh = feats(fd); pa, da = pa[:1000], da[:1000]
        hq = int(round(640 * fd.shape[0] / fd.shape[1] / 2) * 2); x0, y0 = 1280 - 640 - 20, 720 - hq - 20
        pb, db, _ = feats(fq)
        crop = cv2.resize(fq[y0:y0 + hq, x0:x0 + 640], (1280, hq * 2))
        pc, dc, _ = feats(crop); pc = pc / 2 + [x0, y0]
        pt = pa * (640 / sh[1]) + [x0, y0]  # 既知の配置で DB 点をクエリ座標へ
        inside = ((pb[:, 0] >= x0) & (pb[:, 1] >= y0)).astype(float)
        def rep(b, tol=3): return np.mean([np.min(np.linalg.norm(b - x, axis=1)) < tol for x in pt]) if len(b) else 0
        rows.append(dict(n_q=len(pb), in1000=inside[:1000].mean(), r1000=rep(pb[:1000]), r4000=rep(pb[:4000]), rall=rep(pb), rcrop=rep(pc[:1000]), n_in=int(inside.sum())))
    print(src, {k: round(float(np.mean([r[k] for r in rows])), 2) for k in rows[0]}, flush=True)
