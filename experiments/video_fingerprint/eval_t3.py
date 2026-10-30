"""時間をまたぐ 3 点ハッシュ（決まった間隔のフレーム。音声の三つ組の映像版。RANSAC・生記述子なし）

フレームは extract_fixed.py で STEP 秒ごとに取ったもの（cache_fx）。
ハッシュ: フレーム i の点 a（アンカー）・同じフレーム i で a の半径内の点 c・後ろ k 枚目（k<=F）のフレーム j で a の位置から半径内の点 b。
  (a・c・b の視覚語, k, a の大きさ・向きを基準にした c と b の距離・方向, 大きさの比)。半径は a の大きさ ×TR（順位は使わない）。
静止点の除外（STAT>0）: 前後のフレームの STAT px 以内に同じ視覚語の点がある点は、時間で変わらない
  （重ねた文字・ロゴ・止まった画面）とみなし、アンカーにも相手にもしない。PRESTAT=1 なら全点で判定してから NPTS 点を選ぶ。
照合: 完全一致 → (映像, 時刻ずれ, 回転, 拡大率) で投票。1 票は (クエリのアンカー点, DB のアンカー点) それぞれ重複なし。
FAST: 結果を変えずに検索を速くする（1: 静止点の判定と投票、2: ＋DB 引きを先頭 24 bit の表と numba 並列の二分探索、3: ＋ハッシュ作りを numba）。
"""
import json, os, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from scipy.spatial import cKDTree
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + ""); C = os.path.expanduser(os.environ.get("CDIR", f"{H}/cache_fx"))
E = lambda k, d: type(d)(os.environ.get(k, d))
DBV = os.environ.get("DBV", "bbb,ed,sintel,tos,sprite,agent327").split(",")
DBX = [x for x in os.environ.get("DBX", "").split(",") if x]
NPTS, WBITS = E("NPTS", 300), E("WBITS", 6)
SUB = E("SUB", 1)  # フレームを SUB 枚に 1 枚だけ使う（STEP×SUB 秒ごと）
QSUB, QF = E("QSUB", SUB), E("QF", E("F", 1))  # クエリだけ別の間隔・組む枚数にするとき（QSUB は SUB の倍数。DB の「QSUB/SUB 枚先」の組と照らす）
DBK = {int(x) for x in os.environ.get("DBK", "").split(",") if x}  # DB で組む枚数の差（例 2 なら 2 枚先とだけ組む）。空なら 1〜F すべて
SZS = E("SZS", 1.0)  # 点の大きさに掛ける倍率（ORB の大きさを AKAZE に近づける用）
F, DTMAX, DTQ = E("F", 1), E("DTMAX", 4.0), E("DTQ", 0.2)  # 後ろ何枚まで・何秒まで組むか、Δt の刻み
TR, TRL, TRW = E("TR", 3.0), E("TRL", -0.5), E("TRW", 2.0)  # 相手を取る半径（a の大きさの倍数）、大きさの比（log2）の下限と幅
STAT = E("STAT", 4.0)  # 静止点とみなす距離（px）。0 なら除外しない
QC = os.path.expanduser(os.environ.get("QCDIR", C)); QSTAT = E("QSTAT", STAT)  # クエリだけ別の解像度で抽出したキャッシュを使うとき（静止点の距離もその解像度に合わせる）
MAXHIT = E("MAXHIT", 100)
OFF_S, ROT_B, SC_B = 4.0, 16, 0.5
PRESTAT = E("PRESTAT", 0)  # 1 なら全点で静止点を判定してから、残った点のうち反応の強い順に NPTS 点を選ぶ（静止点に枠を取らせない）
STFRAC = []  # PRESTAT のとき、全点に占める静止点の割合（フレームごと）
FAST = E("FAST", 0)  # 1 なら、結果を変えずに検索を速くした処理を使う（静止点の判定・DB 引き・投票）
PT_S = {}  # 検索の区間ごとの合計時間（秒）
def tick(k, t0):
    t = time.perf_counter(); PT_S[k] = PT_S.get(k, 0) + t - t0; return t
ONLYMEAS = E("ONLYMEAS", 0)  # 1 なら DB を作らず、1 枚あたりのハッシュ数だけ出す

def frames(z, pre, sub=SUB):
    if pre + "off" not in z: return []
    off, ts, d, kp = z[pre + "off"], z[pre + "ts"], z[pre + "desc"], z[pre + "kp"]
    out = []
    for i in range(0, len(off) - 1, sub):
        dd, kk = d[off[i]:off[i + 1]], kp[off[i]:off[i + 1]]
        if SZS != 1: kk = kk.copy(); kk[:, 2] *= SZS
        sel = np.argsort(-kk[:, 4])[:None if PRESTAT else NPTS]; out.append((float(ts[i]), dd[sel], kk[sel]))
    return out

def words(km, d):
    x = np.unpackbits(d, axis=1).astype(np.float32); c = km.cluster_centers_
    return np.argmin((x ** 2).sum(1, keepdims=True) - 2 * x @ c.T + (c ** 2).sum(1), axis=1)

def prep(km, fr, stat=STAT):
    """キーフレームごとに (ts, 座標, 大きさ, 向き(rad), 視覚語, 静止か)"""
    t0 = time.perf_counter()
    P = [(ts, kp[:, :2].astype(np.float64), kp[:, 2].astype(np.float64), np.deg2rad(kp[:, 3].astype(np.float64)), words(km, d)) for ts, d, kp in fr if len(d)]
    t0 = tick("視覚語", t0)
    trees = [cKDTree(p[1]) for p in P]; out = []
    for i, (ts, p, sz, th, w) in enumerate(P):
        st = np.zeros(len(p), bool)
        if stat > 0 and FAST:
            for j in (i - 1, i + 1):
                if 0 <= j < len(P) and len(P[j][1]):
                    dd, nn = trees[j].query(p, k=8, distance_upper_bound=np.nextafter(stat, np.inf))
                    hit = np.isfinite(dd); wj = P[j][4]
                    st |= (hit & (wj[np.minimum(nn, len(wj) - 1)] == w[:, None])).any(1)
                    for a in np.nonzero(hit[:, -1] & ~st)[0]:  # 8 点より多く近くにあるときは全部見る
                        nb = trees[j].query_ball_point(p[a], stat)
                        if (wj[nb] == w[a]).any(): st[a] = True
        elif stat > 0:
            for j in (i - 1, i + 1):
                if 0 <= j < len(P):
                    for a, nb in enumerate(trees[j].query_ball_point(p, stat)):
                        if nb and not st[a] and (P[j][4][nb] == w[a]).any(): st[a] = True
        out.append((ts, p, sz, th, w, st))
    t0 = tick("静止点", t0)
    if PRESTAT:  # 反応の強い順に並んでいるので、静止点でない先頭 NPTS 点を残す
        STFRAC.extend(float(o[5].mean()) for o in out)
        out = [(ts, p[k], sz[k], th[k], w[k], st[k]) for ts, p, sz, th, w, st in out for k in [np.nonzero(~st)[0][:NPTS]]]
        trees = [cKDTree(o[1]) for o in out]
    tick("点を選ぶ", t0)
    return out, trees

import numba as nb

def nbr(tree, p, sz, A, pj, szj, stj):
    """A の各点の位置から半径 TR×大きさ にある（静止点でない・大きさの近い）点の組 (A, X, 距離箱, 方向(連続), 大きさ比箱)"""
    nb = tree.query_ball_point(p[A], TR * sz[A]); AA = np.repeat(A, [len(x) for x in nb])
    if not len(AA): return [np.zeros(0, np.int64)] * 2 + [np.zeros(0)] * 3
    X = np.concatenate([np.array(x, np.int64) for x in nb])
    rho = np.log2(szj[X] / sz[AA]); dv = pj[X] - p[AA]; dist = np.linalg.norm(dv, axis=1) / sz[AA]
    ok = ~stj[X] & (rho >= TRL) & (rho < TRL + TRW) & (dist > 0.5 if pj is p else True)
    AA, X, rho, dv, dist = AA[ok], X[ok], rho[ok], dv[ok], np.maximum(dist[ok], 1e-3)
    return AA, X, np.clip(np.floor((np.log2(dist) + 2) / 0.5), 0, 15), np.arctan2(dv[:, 1], dv[:, 0]), np.clip(np.floor((rho - TRL) / 0.5), 0, 3)

@nb.njit(cache=True)
def _nbr_nb(p, sz, st, pj, szj, stj, same, TR, TRL, TRW):
    """nbr() と同じ組を、総当たりで出す（1 枚 300 点なので木を使うより速い）。並びはアンカー順"""
    n, m = len(p), len(pj); K = 0
    A = np.empty(n * m, np.int64); X = np.empty(n * m, np.int64); dq = np.empty(n * m, np.int64); dr = np.empty(n * m); rq = np.empty(n * m, np.int64)
    for a in range(n):
        if st[a]: continue
        r = TR * sz[a]
        for x in range(m):
            dx = pj[x, 0] - p[a, 0]; dy = pj[x, 1] - p[a, 1]
            if dx * dx + dy * dy > r * r or stj[x]: continue
            rho = np.log2(szj[x] / sz[a])
            if rho < TRL or rho >= TRL + TRW: continue
            dist = np.sqrt(dx * dx + dy * dy) / sz[a]
            if same and dist <= 0.5: continue
            dist = max(dist, 1e-3)
            A[K] = a; X[K] = x; dq[K] = min(max(np.floor((np.log2(dist) + 2) / 0.5), 0), 15); dr[K] = np.arctan2(dy, dx); rq[K] = min(max(np.floor((rho - TRL) / 0.5), 0), 3); K += 1
    return A[:K], X[:K], dq[:K], dr[:K], rq[:K]

@nb.njit(cache=True)
def _dir16(d, t):
    x = (d - t) % (2 * np.pi) / (2 * np.pi) * 16; f = np.floor(x)
    return int(f) % 16, (int(f) + 1 if x - f >= 0.5 else int(f) - 1) % 16

@nb.njit(cache=True)
def _pairs_nb(p, sz, th, w, st, pj, szj, wj, stj, dji, soft, TR, TRL, TRW, WBITS):
    """pairs() の 1 組（フレーム i と j）を numba で作る。(ハッシュ, アンカー点番号)"""
    Ac, Cc, dqc, drc, rqc = _nbr_nb(p, sz, st, p, sz, st, True, TR, TRL, TRW)
    Ab, Bb, dqb, drb, rqb = _nbr_nb(p, sz, st, pj, szj, stj, False, TR, TRL, TRW)
    n = len(p); sc = np.zeros(n + 1, np.int64); sb = np.zeros(n + 1, np.int64)
    for k in range(len(Ac)): sc[Ac[k] + 1] += 1
    for k in range(len(Ab)): sb[Ab[k] + 1] += 1
    tot = 0
    for a in range(n): tot += sc[a + 1] * sb[a + 1]
    sc = np.cumsum(sc); sb = np.cumsum(sb); V = 4 if soft else 1
    H = np.empty(tot * V, np.int64); AI = np.empty(tot * V, np.int32); K = 0
    for a in range(n):
        for kc in range(sc[a], sc[a + 1]):
            c0, c1 = _dir16(drc[kc], th[a])
            for kb in range(sb[a], sb[a + 1]):
                b0, b1 = _dir16(drb[kb], th[a])
                base = (((w[a] << WBITS | w[Cc[kc]]) << WBITS | wj[Bb[kb]]) << 2 | (dji - 1)) << 4 | dqc[kc]
                base = ((base << 4 | dqb[kb]) << 2 | rqc[kc]) << 2 | rqb[kb]
                H[K] = (base << 4 | c0) << 4 | b0; AI[K] = a; K += 1
                if soft:
                    H[K] = (base << 4 | c0) << 4 | b1; AI[K] = a; K += 1
                    H[K] = (base << 4 | c1) << 4 | b0; AI[K] = a; K += 1
                    H[K] = (base << 4 | c1) << 4 | b1; AI[K] = a; K += 1
    return H, AI

def pairs_nb(F_, soft, f=F, km_=1):
    H_, FI, AI = [], [], []
    for i, (ts, p, sz, th, w, st) in enumerate(F_):
        for j in range(i + 1, min(i + 1 + f, len(F_))):
            tj, pj, szj, thj, wj, stj = F_[j]
            if tj - ts > DTMAX: break
            h, a = _pairs_nb(p, sz, th, w.astype(np.int64), st, pj, szj, wj.astype(np.int64), stj, (j - i) * km_, soft, float(TR), float(TRL), float(TRW), WBITS)
            H_.append(h); AI.append(a); FI.append(np.full(len(h), i, np.int32))
    if not H_: return np.zeros(0, np.int64), np.zeros(0, np.int32), np.zeros(0, np.int32)
    return np.concatenate(H_), np.concatenate(FI), np.concatenate(AI)

def pairs(F_, trees, soft, f=F, km_=1, ks=()):
    """(ハッシュ, アンカーのフレーム番号, アンカー点番号) を返す。soft なら c・b の方向の隣の箱も作る（クエリ側）"""
    H_, FI, AI = [], [], []
    for i, (ts, p, sz, th, w, st) in enumerate(F_):
        ia = np.nonzero(~st)[0]
        if not len(ia): continue
        Ac, Cc, dqc, dirc, rqc = nbr(trees[i], p, sz, ia, p, sz, st)
        if not len(Ac): continue
        o = np.argsort(Ac, kind="stable"); Ac, Cc, dqc, dirc, rqc = Ac[o], Cc[o], dqc[o], dirc[o], rqc[o]
        for j in range(i + 1, min(i + 1 + f, len(F_))):
            tj, pj, szj, thj, wj, stj = F_[j]
            if tj - ts > DTMAX: break
            if ks and (j - i) not in ks: continue
            Ab, Bb, dqb, dirb, rqb = nbr(trees[j], p, sz, ia, pj, szj, stj)
            if not len(Ab): continue
            # 同じアンカーの c と b を総当たりで組む
            lo = np.searchsorted(Ac, Ab, "left"); hi = np.searchsorted(Ac, Ab, "right"); cnt = hi - lo
            ib = np.repeat(np.arange(len(Ab)), cnt); ic = np.repeat(lo - np.cumsum(cnt) + cnt, cnt) + np.arange(cnt.sum())
            if not len(ib): continue
            A = Ab[ib]; thA = th[A]
            drc = (dirc[ic] - thA) % (2 * np.pi) / (2 * np.pi) * 16; drb = (dirb[ib] - thA) % (2 * np.pi) / (2 * np.pi) * 16
            fc, fb = np.floor(drc).astype(np.int64), np.floor(drb).astype(np.int64)
            nc_ = np.where(drc - fc >= 0.5, fc + 1, fc - 1) % 16; nb_ = np.where(drb - fb >= 0.5, fb + 1, fb - 1) % 16
            base = (((w[A].astype(np.int64) << WBITS | w[Cc[ic]]) << WBITS | wj[Bb[ib]]) << 2 | ((j - i) * km_ - 1)) << 4 | dqc[ic].astype(np.int64)
            base = ((base << 4 | dqb[ib].astype(np.int64)) << 2 | rqc[ic].astype(np.int64)) << 2 | rqb[ib].astype(np.int64)
            for c_ in ([fc % 16, nc_] if soft else [fc % 16]):
                for b_ in ([fb % 16, nb_] if soft else [fb % 16]):
                    H_.append((base << 4 | c_) << 4 | b_); FI.append(np.full(len(A), i, np.int32)); AI.append(A.astype(np.int32))
    if not H_: return np.zeros(0, np.int64), np.zeros(0, np.int32), np.zeros(0, np.int32)
    return np.concatenate(H_), np.concatenate(FI), np.concatenate(AI)

DBCACHE = os.environ.get("DBCACHE", "")  # 指定すると、DB（視覚語・ハッシュ表・点の大きさと向き）をこのファイルに保存し、次からは読み込む
if DBCACHE and os.path.exists(DBCACHE):
    import pickle; _d = pickle.load(open(DBCACHE, "rb")); globals().update(_d); print("loaded", DBCACHE, flush=True)
else:
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
            F_, trees = prep(km, frames(zz, "full_")); h, fi, ai = pairs(F_, trees, False, F, 1, DBK)
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
    print("indexed", round(index_s, 1), n_entries, "frames", nfr, "静止点の割合", round(float(np.mean(STFRAC if PRESTAT else nst)), 3), flush=True)
    DS = int(len(PT) * NPTS).bit_length()
    if DBCACHE:
        import pickle; pickle.dump(dict(km=km, train_s=train_s, db=db, SZ=SZ, TH=TH, index_s=index_s, n_entries=n_entries, db_bytes=db_bytes, DS=DS), open(DBCACHE, "wb"), protocol=4); print("saved", DBCACHE, flush=True)


@nb.njit(parallel=True, cache=True)
def bs_tab(H, T, sh, q):
    """np.searchsorted(H, q, "left"), (…, "right") と同じ。先頭 bit の表で箱を決め、箱の中だけを二分探索する（クエリのハッシュごとに並列）"""
    lo = np.empty(len(q), np.int64); hi = np.empty(len(q), np.int64)
    for i in nb.prange(len(q)):
        x = q[i]; a, b = T[x >> sh], T[(x >> sh) + 1]; e = b
        while a < b:
            m = (a + b) >> 1
            if H[m] < x: a = m + 1
            else: b = m
        lo[i] = a; b = e
        while a < b:
            m = (a + b) >> 1
            if H[m] <= x: a = m + 1
            else: b = m
        hi[i] = a
    return lo, hi

if FAST >= 2:  # 先頭 24 bit ごとの開始位置の表（128MB）
    t0 = time.perf_counter(); TSH = max(int(db["h"].max()).bit_length() - 24, 0)
    TAB = np.searchsorted(db["h"] >> TSH, np.arange((1 << 24) + 1)).astype(np.int64); print("表", round(time.perf_counter() - t0, 1), "s", flush=True)

def uniq_count(x, sh):
    """np.unique(np.unique(x) >> sh, return_counts=True) と同じ結果を、並べ替え 1 回で出す"""
    x = np.sort(x)
    if not len(x): return x, np.zeros(0, np.int64)
    x = x[np.concatenate(([True], x[1:] != x[:-1]))] >> sh
    b = np.flatnonzero(np.concatenate(([True], x[1:] != x[:-1], [True])))
    return x[b[:-1]], np.diff(b)

def score(fr):
    F_, trees = prep(km, fr, QSTAT); t0 = time.perf_counter(); h, fi, ai = pairs_nb(F_, True, QF, QSUB // SUB) if FAST >= 3 else pairs(F_, trees, True, QF, QSUB // SUB); t0 = tick("ハッシュ作り", t0)
    if not len(h): return {}, {}, 0, 0
    if os.environ.get("DUMPH"): DUMPED.append(h.copy())
    if FAST >= 2: lo, hi = bs_tab(db["h"], TAB, TSH, h)
    else: lo = np.searchsorted(db["h"], h, "left"); hi = np.searchsorted(db["h"], h, "right")
    cnt = hi - lo
    sel = (cnt > 0) & (cnt <= MAXHIT)
    if not sel.any(): return {}, {}, len(h), 0
    cs = cnt[sel]; qq = np.repeat(np.nonzero(sel)[0], cs); e = np.repeat(lo[sel] - np.cumsum(cs) + cs, cs) + np.arange(cs.sum())
    t0 = tick("DB 引き", t0)
    qf, qa = fi[qq], ai[qq]; qts = np.array([x[0] for x in F_])[qf]
    QSZ = np.zeros((len(F_), NPTS)); QTH = np.zeros((len(F_), NPTS))
    for i, x in enumerate(F_): QSZ[i, :len(x[2])] = x[2]; QTH[i, :len(x[3])] = x[3]
    g, a = db["gf"][e], db["a"][e]
    sc = np.log2(SZ[g, a] / QSZ[qf, qa]); rot = (TH[g, a] - QTH[qf, qa]) % (2 * np.pi)
    off_b = np.clip(np.round((db["ts"][e] - qts) / OFF_S).astype(np.int64) + 512, 0, 1023)
    key = ((db["vid"][e].astype(np.int64) << 10 | off_b) << 4 | (np.floor(rot / (2 * np.pi) * ROT_B).astype(np.int64) % ROT_B)) << 5 | np.clip(np.round(sc / SC_B).astype(np.int64) + 16, 0, 31)
    QS = int(len(F_) * NPTS).bit_length()
    if FAST:
        k1, n1 = uniq_count(key << QS | (qf.astype(np.int64) * NPTS + qa), QS); k2, n2 = uniq_count(key << DS | (g.astype(np.int64) * NPTS + a), DS)
    else:
        kq = np.unique(key << QS | (qf.astype(np.int64) * NPTS + qa)); kd = np.unique(key << DS | (g.astype(np.int64) * NPTS + a))
        k1, n1 = np.unique(kq >> QS, return_counts=True); k2, n2 = np.unique(kd >> DS, return_counts=True)
    j = np.minimum(np.searchsorted(k2, k1), len(k2) - 1); v = np.minimum(n1, np.where(k2[j] == k1, n2[j], 0))
    t0 = tick("投票", t0)
    vid = k1 >> 19; best, off = {}, {}
    for i in np.argsort(-v):
        if v[i] <= 0: break
        if int(vid[i]) not in best: best[int(vid[i])] = float(v[i]); off[int(vid[i])] = ((int(k1[i]) >> 9 & 1023) - 512) * OFF_S
    tick("映像ごとの最高", t0)
    return best, off, len(h), int(sel.sum())

PT_S.clear(); DUMPED = []
out = []; LIMIT = E("LIMIT", 0)
ql = json.load(open(os.path.expanduser(os.environ.get("META", f"{H}/q/meta.json"))))
for q in ql[::(len(ql) // LIMIT if LIMIT else 1)]:
    name = os.path.basename(q["file"])[:-4]; z = np.load(f"{QC}/{name}.npz")
    t0 = time.perf_counter(); best, off, nh, nhit = score(frames(z, "full_", QSUB))
    if "pip_off" in z and len(z["pip_off"]) > 1:
        pb_, po, _, _ = score(frames(z, "pip_", QSUB))
        for v, c in pb_.items():
            if c > best.get(v, 0): best[v] = c; off[v] = po[v]
    qs = time.perf_counter() - t0
    top = max(best, key=best.get) if best else None; second = sorted(best.values())[-2] if len(best) > 1 else 0.0
    out.append(dict(q, name=name, sec=qs, top=DBV[top] if top is not None else None, score=float(best[top]) if best else 0.0, second=float(second),
                    off=float(off[top]) if best else None, pos_ok=bool(top is not None and abs(off[top] - q["start"]) <= OFF_S * 2 + 2), nhash=int(nh), nhit=nhit,
                    true_score=float(best.get(DBV.index(q["src"]), 0)) if q["positive"] and q["src"] in DBV else None))
print("検索の区間ごとの時間（クエリ 1 本あたり ms）", {k: round(v / len(out) * 1000, 1) for k, v in PT_S.items()}, "合計", round(sum(PT_S.values()) / len(out) * 1000, 1), "実測の中央値", round(float(np.median([r['sec'] for r in out])) * 1000, 1), flush=True)
if os.environ.get("DUMPH"): np.savez(os.environ["DUMPH"], *DUMPED)
tag = os.environ.get("TAG", "TF3")
json.dump(dict(variant=tag, params=dict(SUB=SUB, QSUB=QSUB, QF=QF, DBK=sorted(DBK), SZS=SZS, F=F, DTMAX=DTMAX, DTQ=DTQ, TR=TR, TRL=TRL, TRW=TRW, STAT=STAT, QCDIR=QC, QSTAT=QSTAT, PRESTAT=PRESTAT, FAST=FAST, NPTS=NPTS, WBITS=WBITS, DBX=DBX),
               train_s=train_s, index_s=index_s, db_bytes=db_bytes, n_entries=n_entries, results=out), open(f"{H}/res_{tag}.json", "w"))
print(tag, "done", n_entries, flush=True)
