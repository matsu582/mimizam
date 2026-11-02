"""加工ごとに、ORB と AKAZE の点の再現率と記述子の一致率を比べる（元の映像の同じ時刻の画像と組にする）。
正解の対応は、SIFT＋RANSAC で求めた射影変換（元の画像 → クエリの画像）を使う。DB 側は長辺 640、クエリ側は長辺 960。
再現率: クエリの点のうち、元の画像の点を写した位置が EPS px 以内にあるものの割合。
一致率: クエリの点のうち、記述子の最近傍（Hamming）が、写した位置で EPS px 以内の元の点であるものの割合。"""
import json, os, sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from mimizam.src.video_fingerprinter import _create_akaze, normalize_frame
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + ""); EPS = 3.0; TS = (5.0, 15.0, 25.0)
EXT = {"tos": "mov", "llamigos": "webm"}

def grab(path, t):
    cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, img = cap.read(); cap.release()
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if ok else None

def det(name, g, n):
    if name == "AKAZE":
        k, d = _create_akaze().detectAndCompute(g, None)
        if d is None: return None
        o = np.argsort([-x.response for x in k])[:n]; k = [k[i] for i in o]; d = d[o]
    else:
        k, d = cv2.ORB.create(nfeatures=n).detectAndCompute(g, None)
        if d is None: return None
    return np.array([x.pt for x in k], np.float32), d

def job(m):
    out = []
    src = f"{H}/src/{m['src']}.{EXT.get(m['src'], 'mp4')}"
    for t in TS:
        gq, gs = grab(m["file"], t), grab(src, m["start"] + t)
        if gq is None or gs is None: continue
        gq = normalize_frame(gq, 960, allow_upscale=True); gs = normalize_frame(gs, 640, allow_upscale=True)
        sift = cv2.SIFT.create(4000); ks, ds = sift.detectAndCompute(gs, None); kq, dq = sift.detectAndCompute(gq, None)
        if ds is None or dq is None: continue
        mm = [a for a, b in cv2.BFMatcher().knnMatch(ds, dq, k=2) if a.distance < 0.75 * b.distance]
        if len(mm) < 20: continue
        Hm, inl = cv2.findHomography(np.float32([ks[a.queryIdx].pt for a in mm]), np.float32([kq[a.trainIdx].pt for a in mm]), cv2.RANSAC, 3.0)
        if Hm is None or inl.sum() < 20: continue
        r = dict(name=os.path.basename(m["file"])[:-4], tf=m["tf"], t=t, gt_inl=int(inl.sum()))
        for name in ("AKAZE", "ORB"):
            for n in (300, 2000):
                a, b = det(name, gq, n), det(name, gs, n)
                if a is None or b is None: r[f"{name}{n}"] = (0.0, 0.0, 0); continue
                (pq, dq_), (ps, ds_) = a, b
                pw = cv2.perspectiveTransform(ps[None], Hm)[0]  # 元の点をクエリの座標へ
                dist = np.linalg.norm(pq[:, None] - pw[None], axis=2)
                rep = dist.min(1) <= EPS
                nn = cv2.BFMatcher(cv2.NORM_HAMMING).match(dq_, ds_)
                ok = np.zeros(len(pq), bool)
                for x in nn: ok[x.queryIdx] = dist[x.queryIdx, x.trainIdx] <= EPS
                # 映像の中身の点だけ: 元の画像の枠を写した範囲の内側で、4:3 の文字の帯（下 120px、長辺 960 で y>=600）を除く
                hh, ww = gs.shape; box = cv2.perspectiveTransform(np.float32([[[0, 0], [ww, 0], [ww, hh], [0, hh]]]), Hm)[0]
                inside = np.array([cv2.pointPolygonTest(box, (float(x), float(y)), False) >= 0 for x, y in pq])
                if m["tf"] == "aspect43_text": inside &= pq[:, 1] < 600 * gq.shape[0] / 720
                c = inside.sum()
                r[f"{name}{n}"] = (float(rep.mean()), float(ok.mean()), len(pq), float(rep[inside].mean()) if c else 0.0, float(ok[inside].mean()) if c else 0.0, int(c))
        out.append(r)
    return out

if __name__ == "__main__":
    cv2.setNumThreads(1)
    meta = [m for m in json.load(open(f"{H}/q/meta.json")) if m["positive"]]
    with ProcessPoolExecutor(8) as ex: R = [r for o in ex.map(job, meta) for r in o]
    json.dump(R, open(f"{H}/res_cmp_orb.json", "w"))
    tfs = ["reenc480", "low240", "crop70", "color", "rot10", "aspect43_text", "pip_half", "pip_third"]
    print(f"組の数 {len(R)}（正解の変換が取れた組）")
    for n in (300, 2000):
        print(f"== 1 枚 {n} 点まで（再現率 / 一致率）")
        for tf in tfs:
            S = [r for r in R if r["tf"] == tf]
            a = np.array([r[f"AKAZE{n}"] for r in S]).mean(0); o = np.array([r[f"ORB{n}"] for r in S]).mean(0)
            print(f"{tf:14s} n={len(S):3d}  全点 AKAZE {a[0]:.2f} / {a[1]:.2f}  ORB {o[0]:.2f} / {o[1]:.2f}   中身の点だけ AKAZE {a[3]:.2f} / {a[4]:.2f}（{a[5]:.0f} 点）  ORB {o[3]:.2f} / {o[4]:.2f}（{o[5]:.0f} 点）")
