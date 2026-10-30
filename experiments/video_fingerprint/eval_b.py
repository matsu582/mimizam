"""B 案: AKAZE 特徴点の三つ組ハッシュ（音声の anchor+2target と同じ考え方）

ハッシュ = 3 点の視覚語 ID ＋ 距離比 log(|AB|/|AC|) ＋ 角度 ∠BAC（相似変換で不変）。
DB はハード量子化、クエリは比・角度を近傍 2 ビンへソフト量子化（音声の _freq_ratio_bins と同じ）。
照合は完全一致（ソート済み配列の二分探索）→ (映像, 時刻ずれ, 回転, 拡大率) の投票で整合を確かめる
（音声の時刻ずれヒストグラムに当たる）。
"""
import json, os, sys, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp")); C = f"{H}/cache"
DBV = ["bbb", "ed", "sintel", "tos", "sprite", "agent327"]
NPTS = int(os.environ.get("NPTS", 150)); KNN = int(os.environ.get("KNN", 5)); WBITS = int(os.environ.get("WBITS", 6))
RB, AB = 5, 5  # 距離比・角度のビット数
RMAX = 3.0  # log2 比の上限（B を近い方にしたので比 ∈ (0,1]、-log2 ∈ [0,RMAX)）
OFF_S, ROT_B, SC_B = 4.0, 16, 0.25
MAXHIT = int(os.environ.get("MAXHIT", 100))  # 出現が多すぎるハッシュは捨てる（ストップワード）  # 時刻ずれ 4 秒、回転 22.5°、log2 拡大率 0.25

def frames(z, pre):
    off, ts, d, kp = z[pre + "off"], z[pre + "ts"], z[pre + "desc"], z[pre + "kp"]  # NpzFile は参照のたびに読み直すので 1 回だけ読む
    return [(float(ts[i]), d[off[i]:off[i + 1]], kp[off[i]:off[i + 1]])
            for i in range(len(off) - 1)]

def words(km, d):
    x = np.unpackbits(d, axis=1).astype(np.float32); c = km.cluster_centers_
    return np.argmin((x ** 2).sum(1, keepdims=True) - 2 * x @ c.T + (c ** 2).sum(1), axis=1)

def triplets(km, d, kp):
    """1 フレームの三つ組: (wA,wB,wC, 比の連続位置, 角度の連続位置, A idx, B idx)"""
    if len(d) < KNN + 1: return None
    sel = np.argsort(-kp[:, 4])[:NPTS]; d, kp = d[sel], kp[sel]
    w = words(km, d); p = kp[:, :2].astype(np.float64)
    dist = np.linalg.norm(p[:, None] - p[None], axis=2); np.fill_diagonal(dist, np.inf)
    nn = np.argsort(dist, axis=1)[:, :KNN]
    i1, i2 = np.triu_indices(KNN, 1)
    A = np.repeat(np.arange(len(p)), len(i1)); B = nn[:, i1].ravel(); Cc = nn[:, i2].ravel()  # B は C より近い
    vb, vc = p[B] - p[A], p[Cc] - p[A]
    lb, lc = np.linalg.norm(vb, axis=1), np.linalg.norm(vc, axis=1)
    ok = (lb > 2) & (lc > 2)
    r = np.clip(-np.log2(lb / lc), 0, RMAX - 1e-6) / RMAX * (1 << RB)
    ang = (np.arctan2(vc[:, 1], vc[:, 0]) - np.arctan2(vb[:, 1], vb[:, 0])) % (2 * np.pi) / (2 * np.pi) * (1 << AB)
    return (w[A][ok], w[B][ok], w[Cc][ok], r[ok], ang[ok], p[A][ok], p[B][ok])

def pack(wa, wb, wc, rb, ab):
    return (((wa.astype(np.uint64) << (2 * WBITS)) | (wb.astype(np.uint64) << WBITS) | wc.astype(np.uint64)) << (RB + AB)) \
        | (rb.astype(np.uint64) << AB) | ab.astype(np.uint64)

def hard(t):
    return pack(t[0], t[1], t[2], np.floor(t[3]).astype(int), np.floor(t[4]).astype(int) % (1 << AB))

def soft(t):  # 4 通り（比・角度とも近い方の隣ビンを足す）
    rl = np.floor(t[3]).astype(int); al = np.floor(t[4]).astype(int)
    rn = np.clip(np.where(t[3] - rl >= 0.5, rl + 1, rl - 1), 0, (1 << RB) - 1)
    an = np.where(t[4] - al >= 0.5, al + 1, al - 1) % (1 << AB)
    al %= (1 << AB)
    return [pack(t[0], t[1], t[2], a, b) for a in (rl, rn) for b in (al, an)]

t0 = time.perf_counter()
caches = {n: np.load(f"{C}/{n}.npz") for n in DBV}
rnd = np.random.default_rng(0); samp = []
for n in DBV:
    fr = frames(caches[n], "full_")
    for i in rnd.choice(len(fr), min(100, len(fr)), replace=False):
        d = fr[i][1]; samp.append(d[rnd.choice(len(d), min(200, len(d)), replace=False)])
km = MiniBatchKMeans(1 << WBITS, random_state=0, n_init=3, batch_size=4096).fit(np.unpackbits(np.vstack(samp), axis=1).astype(np.float32))
train_s = time.perf_counter() - t0; print("trained", round(train_s, 1), flush=True)

t0 = time.perf_counter(); cols = {k: [] for k in ("h", "vid", "ts", "ax", "ay", "bx", "by")}
for vi, n in enumerate(DBV):
    for ts, d, kp in frames(caches[n], "full_"):
        t = triplets(km, d, kp)
        if t is None: continue
        h = hard(t); m = len(h)
        cols["h"].append(h); cols["vid"].append(np.full(m, vi, np.int8)); cols["ts"].append(np.full(m, ts, np.float32))
        cols["ax"].append(t[5][:, 0]); cols["ay"].append(t[5][:, 1]); cols["bx"].append(t[6][:, 0]); cols["by"].append(t[6][:, 1])
db = {k: np.concatenate(v) for k, v in cols.items()}
o = np.argsort(db["h"], kind="stable"); db = {k: v[o] for k, v in db.items()}
index_s = time.perf_counter() - t0
n_entries = len(db["h"]); print("indexed", round(index_s, 1), n_entries, flush=True)
# 1 件 = ハッシュ 4B + 映像/時刻 4B（＋幾何検証用の A,B 座標 4×2B）
db_bytes = n_entries * (4 + 4 + 8)

def score(fr):
    """映像ごとに、(時刻ずれ, 回転, 拡大率) の最多ビンの票数（三つ組の重複は数えない）"""
    rows = []
    for qi, (ts, d, kp) in enumerate(fr):
        t = triplets(km, d, kp)
        if t is None: continue
        tid = np.arange(len(t[0]))
        for h in soft(t):
            lo = np.searchsorted(db["h"], h, "left"); hi = np.searchsorted(db["h"], h, "right")
            cnt = hi - lo; sel = (cnt > 0) & (cnt <= MAXHIT)
            if not sel.any(): continue
            q = np.repeat(tid[sel], cnt[sel]); e = np.concatenate([np.arange(a, b) for a, b in zip(lo[sel], hi[sel])])
            qa, qb = t[5][q], t[6][q]
            vq = qb - qa; vd = np.stack([db["bx"][e] - db["ax"][e], db["by"][e] - db["ay"][e]], 1)
            rot = (np.arctan2(vq[:, 1], vq[:, 0]) - np.arctan2(vd[:, 1], vd[:, 0])) % (2 * np.pi)
            sc = np.log2(np.linalg.norm(vq, axis=1) / np.maximum(np.linalg.norm(vd, axis=1), 1e-6))
            off_b = np.clip(np.round((db["ts"][e] - ts) / OFF_S).astype(np.int64) + 512, 0, 1023)
            rot_b = np.floor(rot / (2 * np.pi) * ROT_B).astype(np.int64) % ROT_B
            sc_b = np.clip(np.round(sc / SC_B).astype(np.int64) + 16, 0, 31)
            key = (db["vid"][e].astype(np.int64) << 19) | (off_b << 9) | (rot_b << 5) | sc_b
            rows.append(((qi * 20000 + q).astype(np.int64) << 22) | key)
    if not rows: return {}, {}
    r = np.unique(np.concatenate(rows))  # 同じクエリ三つ組→同じビンは 1 票
    keys, cnt = np.unique(r & ((1 << 22) - 1), return_counts=True)
    best, off = {}, {}
    for k, c in zip(keys, cnt):
        v = int(k >> 19)
        if c > best.get(v, 0): best[v] = int(c); off[v] = (int((k >> 9) & 1023) - 512) * OFF_S
    return best, off

out = []
for q in json.load(open(f"{H}/q/meta.json")):
    name = os.path.basename(q["file"])[:-4]; z = np.load(f"{C}/{name}.npz")
    t0 = time.perf_counter()
    best, off = score(frames(z, "full_"))
    if len(z["pip_off"]) > 1:
        pb, po = score(frames(z, "pip_"))
        for v, c in pb.items():
            if c > best.get(v, 0): best[v] = c; off[v] = po[v]
    qs = time.perf_counter() - t0
    top = max(best, key=best.get) if best else None
    out.append(dict(q, name=name, sec=qs, top=DBV[top] if top is not None else None, score=float(best[top]) if best else 0.0,
                    pos_ok=bool(top is not None and abs(off[top] - q["start"]) <= OFF_S * 2 + 2)))
tag = os.environ.get("TAG", "B")
json.dump(dict(variant=tag, params=dict(NPTS=NPTS, KNN=KNN, WBITS=WBITS), train_s=train_s, index_s=index_s, db_bytes=db_bytes,
               n_entries=n_entries, results=out), open(f"{H}/res_{tag}.json", "w"))
print(tag, "done", n_entries)
