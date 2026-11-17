"""縦横比変換で AKAZE の点・視覚語がどれだけ残るか（同じ時刻のフレームで、既知の変換を当てて比べる）"""
import json, os, sys, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))  # mimizam の親
from mimizam.src.video_fingerprinter import normalize_frame, _create_akaze
from sklearn.cluster import MiniBatchKMeans
S = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/src"); Q = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q")
meta = {os.path.basename(m["file"])[:-4]: m for m in json.load(open(f"{Q}/meta.json"))}
ak = _create_akaze()
def grab(path, t):
    cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); cap.release(); return f
def feats(img, npts=150):
    g = normalize_frame(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 1280, allow_upscale=True)
    k, d = ak.detectAndCompute(g, None)
    o = np.argsort([-x.response for x in k])[:npts]
    return np.array([k[i].pt for i in o]), d[o], g.shape
z = np.load(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/cache/sintel.npz"))
km = MiniBatchKMeans(32, random_state=0, n_init=3).fit(np.unpackbits(z["full_desc"][::50], axis=1).astype(np.float32))
w = lambda d: km.predict(np.unpackbits(d, axis=1).astype(np.float32))
for src, ext in [("sintel", "mp4"), ("bbb", "mp4"), ("tos", "mov")]:
    for tf in ["aspect43_text", "rot10", "crop70", "reenc480"]:
        m = meta[f"{src}_0_{tf}"]; res = []
        for t in (5.0, 12.0, 20.0):
            a = grab(f"{S}/{src}.{ext}", m["start"] + t); b = grab(m["file"], t)
            pa, da, sa = feats(a); pb, db, sb = feats(b)
            # 既知の変換を当てる代わりに、全点で BF+RANSAC の homography を推定してから点の再現率を数える
            bf = cv2.BFMatcher(cv2.NORM_HAMMING); a_all = feats(a, 2000); b_all = feats(b, 2000)
            mm = [x for x, y in bf.knnMatch(a_all[1], b_all[1], k=2) if x.distance < 0.8 * y.distance]
            if len(mm) < 8: res.append((0, 0, 0)); continue
            Hm, inl = cv2.findHomography(a_all[0][[x.queryIdx for x in mm]], b_all[0][[x.trainIdx for x in mm]], cv2.RANSAC, 5.0)
            if Hm is None: res.append((0, 0, 0)); continue
            pt = cv2.perspectiveTransform(pa.reshape(-1, 1, 2), Hm).reshape(-1, 2)
            dd = np.linalg.norm(pt[:, None] - pb[None], axis=2); j = dd.argmin(1); near = dd.min(1) < 4
            same = (w(da)[near] == w(db)[j[near]]).mean() if near.any() else 0
            res.append((near.mean(), same, int(inl.sum())))
        r = np.array(res); print(f"{src:7s} {tf:14s} 上位150点の再現率={r[:,0].mean():.2f} 残った点の視覚語一致={r[:,1].mean():.2f} RANSACインライア={r[:,2].mean():.0f}")
