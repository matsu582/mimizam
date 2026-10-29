"""時間をまたぐハッシュ（音声の三つ組の映像版。RANSAC・生記述子なし）

ハッシュ: キーフレーム i の点 a（アンカー）と、後ろ F 枚以内・DTMAX 秒以内のキーフレーム j の点 b の組。
  (a の視覚語, b の視覚語, Δt=t_j−t_i の量子化, a の大きさ・向きを基準にした b の距離・方向, 大きさの比)
  b は a の位置から a の大きさ ×TR の半径にある点だけを取る（順位は使わない）。
静止点の除外（STAT>0）: 前後のキーフレームの STAT px 以内に同じ視覚語の点がある点は、時間で変わらない
  （重ねた文字・ロゴ・止まった画面）とみなし、アンカーにも相手にもしない。
照合: 完全一致 → (映像, 時刻ずれ, 回転, 拡大率) で投票。1 票は (クエリのアンカー点, DB のアンカー点) それぞれ重複なし。
"""
import json, os, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from scipy.spatial import cKDTree
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + ""); C = f"{H}/cache"
E = lambda k, d: type(d)(os.environ.get(k, d))
DBV = os.environ.get("DBV", "bbb,ed,sintel,tos,sprite,agent327").split(",")
DBX = [x for x in os.environ.get("DBX", "").split(",") if x]
NPTS, WBITS = E("NPTS", 1000), E("WBITS", 6)
F, DTMAX, DTQ = E("F", 2), E("DTMAX", 4.0), E("DTQ", 0.2)  # 後ろ何枚まで・何秒まで組むか、Δt の刻み
TR, TRL, TRW = E("TR", 3.0), E("TRL", -0.5), E("TRW", 2.0)  # 相手を取る半径（a の大きさの倍数）、大きさの比（log2）の下限と幅
STAT = E("STAT", 4.0)  # 静止点とみなす距離（px）。0 なら除外しない
MAXHIT = E("MAXHIT", 100)
OFF_S, ROT_B, SC_B = 4.0, 16, 0.5
ONLYMEAS = E("ONLYMEAS", 0)  # 1 なら DB を作らず、1 枚あたりのハッシュ数だけ出す

def frames(z, pre):
    off, ts, d, kp = z[pre + "off"], z[pre + "ts"], z[pre + "desc"], z[pre + "kp"]
    out = []
    for i in range(len(off) - 1):
        dd, kk = d[off[i]:off[i + 1]], kp[off[i]:off[i + 1]]
        sel = np.argsort(-kk[:, 4])[:NPTS]; out.append((float(ts[i]), dd[sel], kk[sel]))
    return out

def words(km, d):
    x = np.unpackbits(d, axis=1).astype(np.float32); c = km.cluster_centers_
    return np.argmin((x ** 2).sum(1, keepdims=True) - 2 * x @ c.T + (c ** 2).sum(1), axis=1)

def prep(km, fr):
    """キーフレームごとに (ts, 座標, 大きさ, 向き(rad), 視覚語, 静止か)"""
    P = [(ts, kp[:, :2].astype(np.float64), kp[:, 2].astype(np.float64), np.deg2rad(kp[:, 3].astype(np.float64)), words(km, d)) for ts, d, kp in fr if len(d)]
    trees = [cKDTree(p[1]) for p in P]; out = []
    for i, (ts, p, sz, th, w) in enumerate(P):
        st = np.zeros(len(p), bool)
        if STAT > 0:
            for j in (i - 1, i + 1):
                if 0 <= j < len(P):
                    for a, nb in enumerate(trees[j].query_ball_point(p, STAT)):
                        if nb and not st[a] and (P[j][4][nb] == w[a]).any(): st[a] = True
        out.append((ts, p, sz, th, w, st))
    return out, trees

def pairs(F_, trees, soft):
    """(ハッシュ, アンカーのフレーム番号, アンカー点番号) を返す。soft なら方向と Δt の隣の箱も作る（クエリ側）"""
    H_, FI, AI = [], [], []
    for i, (ts, p, sz, th, w, st) in enumerate(F_):
        ia = np.nonzero(~st)[0]
        if not len(ia): continue
        for j in range(i + 1, min(i + 1 + F, len(F_))):
            tj, pj, szj, thj, wj, stj = F_[j]; dt = tj - ts
            if dt > DTMAX: break
            nb = trees[j].query_ball_point(p[ia], TR * sz[ia])
            A = np.repeat(ia, [len(x) for x in nb])
            if not len(A): continue
            B = np.concatenate([np.array(x, np.int64) for x in nb])
            rho = np.log2(szj[B] / sz[A]); ok = ~stj[B] & (rho >= TRL) & (rho < TRL + TRW); A, B, rho = A[ok], B[ok], rho[ok]
            dv = pj[B] - p[A]; dist = np.maximum(np.linalg.norm(dv, axis=1) / sz[A], 1e-3)
            dq = np.clip(np.floor((np.log2(dist) + 2) / 0.5), 0, 15).astype(np.int64)
            dr = (np.arctan2(dv[:, 1], dv[:, 0]) - th[A]) % (2 * np.pi) / (2 * np.pi) * 16
            rq = np.clip(np.floor((rho - TRL) / 0.5), 0, 3).astype(np.int64)
            tq = dt / DTQ; t0 = int(np.floor(tq))
            fb = np.floor(dr).astype(np.int64); nbd = np.where(dr - fb >= 0.5, fb + 1, fb - 1) % 16
            tl = [t0] + ([t0 + 1 if tq - t0 >= 0.5 else t0 - 1] if soft else [])
            for tb in tl:
                for db_ in ([fb % 16, nbd] if soft else [fb % 16]):
                    h = (((((w[A].astype(np.int64) << WBITS | wj[B]) << 6 | min(max(tb, 0), 63)) << 4 | dq) << 4 | db_) << 2 | rq)
                    H_.append(h); FI.append(np.full(len(A), i, np.int32)); AI.append(A.astype(np.int32))
    if not H_: return np.zeros(0, np.int64), np.zeros(0, np.int32), np.zeros(0, np.int32)
    return np.concatenate(H_), np.concatenate(FI), np.concatenate(AI)

t0 = time.perf_counter(); caches = {n: np.load(f"{C}/{n}.npz") for n in DBV}
rnd = np.random.default_rng(0); samp = []
for n in DBV:  # eval_b2.py と同じ視覚語の学習
    z = caches[n]; off, d = z["full_off"], z["full_desc"]
    for i in rnd.choice(len(off) - 1, min(100, len(off) - 1), replace=False):
        dd = d[off[i]:off[i + 1]]; samp.append(dd[rnd.choice(len(dd), min(200, len(dd)), replace=False)])
km = MiniBatchKMeans(1 << WBITS, random_state=0, n_init=3, batch_size=4096).fit(np.unpackbits(np.vstack(samp), axis=1).astype(np.float32))
train_s = time.perf_counter() - t0; print("trained", round(train_s, 1), flush=True)

t0 = time.perf_counter(); cols = {k: [] for k in ("h", "vid", "ts", "gf", "a")}; PT = []; nfr = 0; nst = []
for vi, n in enumerate(DBV):
    for zz in [caches[n]] + [np.load(f"{C}/{n}__{x}.npz") for x in DBX]:
        F_, trees = prep(km, frames(zz, "full_")); h, fi, ai = pairs(F_, trees, False)
        nst += [x[5].mean() for x in F_]
        cols["h"].append(h); cols["vid"].append(np.full(len(h), vi, np.int8)); cols["ts"].append(np.array([F_[i][0] for i in range(len(F_))], np.float32)[fi] if len(h) else np.zeros(0, np.float32))
        cols["gf"].append((fi + len(PT)).astype(np.int32)); cols["a"].append(ai)
        for x in F_: PT.append((x[2], x[3]))
        nfr += len(F_)
        if ONLYMEAS: print(n, "ハッシュ / 枚", round(len(h) / max(len(F_), 1)), "静止点の割合", round(float(np.mean([x[5].mean() for x in F_])), 3), flush=True); break
    if ONLYMEAS and vi >= 1: raise SystemExit
db = {k: np.concatenate(v) for k, v in cols.items()}; o = np.argsort(db["h"], kind="stable"); db = {k: v[o] for k, v in db.items()}
SZ = np.zeros((len(PT), NPTS), np.float32); TH = np.zeros((len(PT), NPTS), np.float32)
for i, (s, t) in enumerate(PT): SZ[i, :len(s)] = s; TH[i, :len(t)] = t
index_s = time.perf_counter() - t0; n_entries = len(db["h"])
npts = int(sum(len(s) for s, t in PT)); db_bytes = n_entries * (4 + 4 + 2) + npts * 6  # ハッシュ 4B＋フレーム 4B＋点番号 2B、点ごとに座標・大きさ・向き 6B
print("indexed", round(index_s, 1), n_entries, "frames", nfr, "静止点の割合", round(float(np.mean(nst)), 3), flush=True)
DS = int(len(PT) * NPTS).bit_length()

def score(fr):
    F_, trees = prep(km, fr); h, fi, ai = pairs(F_, trees, True)
    if not len(h): return {}, {}, 0, 0
    lo = np.searchsorted(db["h"], h, "left"); hi = np.searchsorted(db["h"], h, "right"); cnt = hi - lo
    sel = (cnt > 0) & (cnt <= MAXHIT)
    if not sel.any(): return {}, {}, len(h), 0
    cs = cnt[sel]; qq = np.repeat(np.nonzero(sel)[0], cs); e = np.repeat(lo[sel] - np.cumsum(cs) + cs, cs) + np.arange(cs.sum())
    qf, qa = fi[qq], ai[qq]; qts = np.array([x[0] for x in F_])[qf]
    QSZ = np.zeros((len(F_), NPTS)); QTH = np.zeros((len(F_), NPTS))
    for i, x in enumerate(F_): QSZ[i, :len(x[2])] = x[2]; QTH[i, :len(x[3])] = x[3]
    g, a = db["gf"][e], db["a"][e]
    sc = np.log2(SZ[g, a] / QSZ[qf, qa]); rot = (TH[g, a] - QTH[qf, qa]) % (2 * np.pi)
    off_b = np.clip(np.round((db["ts"][e] - qts) / OFF_S).astype(np.int64) + 512, 0, 1023)
    key = ((db["vid"][e].astype(np.int64) << 10 | off_b) << 4 | (np.floor(rot / (2 * np.pi) * ROT_B).astype(np.int64) % ROT_B)) << 5 | np.clip(np.round(sc / SC_B).astype(np.int64) + 16, 0, 31)
    QS = int(len(F_) * NPTS).bit_length()
    kq = np.unique(key << QS | (qf.astype(np.int64) * NPTS + qa)); kd = np.unique(key << DS | (g.astype(np.int64) * NPTS + a))
    k1, n1 = np.unique(kq >> QS, return_counts=True); k2, n2 = np.unique(kd >> DS, return_counts=True)
    j = np.minimum(np.searchsorted(k2, k1), len(k2) - 1); v = np.minimum(n1, np.where(k2[j] == k1, n2[j], 0))
    vid = k1 >> 19; best, off = {}, {}
    for i in np.argsort(-v):
        if v[i] <= 0: break
        if int(vid[i]) not in best: best[int(vid[i])] = float(v[i]); off[int(vid[i])] = ((int(k1[i]) >> 9 & 1023) - 512) * OFF_S
    return best, off, len(h), int(sel.sum())

out = []; LIMIT = E("LIMIT", 0)
ql = json.load(open(os.path.expanduser(os.environ.get("META", f"{H}/q/meta.json"))))
for q in ql[::(len(ql) // LIMIT if LIMIT else 1)]:
    name = os.path.basename(q["file"])[:-4]; z = np.load(f"{C}/{name}.npz")
    t0 = time.perf_counter(); best, off, nh, nhit = score(frames(z, "full_"))
    if len(z["pip_off"]) > 1:
        pb_, po, _, _ = score(frames(z, "pip_"))
        for v, c in pb_.items():
            if c > best.get(v, 0): best[v] = c; off[v] = po[v]
    qs = time.perf_counter() - t0
    top = max(best, key=best.get) if best else None; second = sorted(best.values())[-2] if len(best) > 1 else 0.0
    out.append(dict(q, name=name, sec=qs, top=DBV[top] if top is not None else None, score=float(best[top]) if best else 0.0, second=float(second),
                    off=float(off[top]) if best else None, pos_ok=bool(top is not None and abs(off[top] - q["start"]) <= OFF_S * 2 + 2), nhash=int(nh), nhit=nhit,
                    true_score=float(best.get(DBV.index(q["src"]), 0)) if q["positive"] and q["src"] in DBV else None))
tag = os.environ.get("TAG", "TT")
json.dump(dict(variant=tag, params=dict(F=F, DTMAX=DTMAX, DTQ=DTQ, TR=TR, TRL=TRL, TRW=TRW, STAT=STAT, NPTS=NPTS, WBITS=WBITS, DBX=DBX),
               train_s=train_s, index_s=index_s, db_bytes=db_bytes, n_entries=n_entries, results=out), open(f"{H}/res_{tag}.json", "w"))
print(tag, "done", n_entries, flush=True)
