"""B2: アフィン不変の 4 点ハッシュ＋反復模様の抑制（RANSAC・生記述子なし）

ハッシュ: アンカー A の近傍 K 点を A の周りの角度順（向きを保つアフィン変換で順序が変わらない）に並べ、
連続する 3 点 B,C,D を取り、D-A = α(B-A) + β(C-A) の (α,β) と 4 点の視覚語 ID を量子化する。
(α,β) はアフィン変換（縦横比の変化・回転・拡大縮小・平行移動）で変わらない。
照合: 完全一致 → 3 点 A,B,C から求めたアフィン行列（回転・拡大率・縦横比）と時刻ずれで投票。
反復模様の抑制: ①クエリの同一フレームで同じハッシュが多数出たら捨てる ②1 票は (クエリ点, DB 点) の重複なし
③1 クエリフレームからの票に上限 CAP（1 枚の模様だけで点が積み上がらないようにする）。
"""
import json, os, sys, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from scipy.spatial import cKDTree
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp")); C = f"{H}/cache"
DBV = os.environ.get("DBV", "bbb,ed,sintel,tos,sprite,agent327").split(",")
E = lambda k, d: type(d)(os.environ.get(k, d))
NPTS, KNN, WBITS = E("NPTS", 150), E("KNN", 5), E("WBITS", 5)
COMBOS = [tuple(map(int, c.split(":"))) for c in E("COMBOS", "1:2,1:3").split(",")]
QB, QSTEP, QMAX = 5, E("QSTEP", 0.25), 4.0  # α,β の量子化（5bit・幅 0.25・±4 で打ち切り）
MAXHIT, QBURST, CAP = E("MAXHIT", 100), E("QBURST", 4), E("CAP", 8)
OFF_S, ROT_B, SC_B, AN_B = 4.0, 16, 0.25, 0.25
STRETCH = [x for x in E("STRETCH", "").split(",") if x]  # 例 "133,178"（横に ×1.33・×1.78）。"c00" などは切り出した窓（extract_crops.py）
MODE = E("MODE", "aff")  # aff: 4 点のアフィン不変 / sim: B と同じ 3 点の相似不変（距離比・角度）

def frames(z, pre):
    off, ts, d, kp = z[pre + "off"], z[pre + "ts"], z[pre + "desc"], z[pre + "kp"]
    return [(float(ts[i]), d[off[i]:off[i + 1]], kp[off[i]:off[i + 1]]) for i in range(len(off) - 1)]

def words(km, d):
    x = np.unpackbits(d, axis=1).astype(np.float32); c = km.cluster_centers_
    return np.argmin((x ** 2).sum(1, keepdims=True) - 2 * x @ c.T + (c ** 2).sum(1), axis=1)

def quads(km, d, kp):
    """(wA,wB,wC,wD, α連続位置, β連続位置, A idx, B idx, C idx, 点座標)"""
    if len(d) < KNN + 1: return None
    sel = np.argsort(-kp[:, 4])[:NPTS]; d, kp = d[sel], kp[sel]
    w = words(km, d); p = kp[:, :2].astype(np.float64); n = len(p)
    nn = cKDTree(p).query(p, KNN + 1)[1][:, 1:]  # 自分を除く近い順 KNN 点
    if MODE == "sim":
        i1, i2 = np.triu_indices(KNN, 1)
        A = np.repeat(np.arange(n), len(i1)); B = nn[:, i1].ravel(); Cc = nn[:, i2].ravel()  # B は C より近い
        vb, vc = p[B] - p[A], p[Cc] - p[A]; lb, lc = np.linalg.norm(vb, axis=1), np.linalg.norm(vc, axis=1)
        ok = (lb > 2) & (lc > 2)
        pa = np.clip(-np.log2(lb / np.maximum(lc, 1e-9)), 0, 3 - 1e-6) / 3 * (1 << QB)
        pb = (np.arctan2(vc[:, 1], vc[:, 0]) - np.arctan2(vb[:, 1], vb[:, 0])) % (2 * np.pi) / (2 * np.pi) * (1 << QB)
        return dict(w=(w[A][ok], w[B][ok], w[Cc][ok]), pa=pa[ok], pb=pb[ok], A=A[ok], B=B[ok], C=Cc[ok], p=p.astype(np.float32))
    ang = np.arctan2(p[nn][..., 1] - p[:, None, 1], p[nn][..., 0] - p[:, None, 0])
    ordn = np.take_along_axis(nn, np.argsort(ang, axis=1), 1)  # 角度順（巡回順はアフィンで不変）
    A, B, Cc, D = [], [], [], []
    for a, b in COMBOS:
        for i in range(KNN):
            A.append(np.arange(n)); B.append(ordn[:, i]); Cc.append(ordn[:, (i + a) % KNN]); D.append(ordn[:, (i + b) % KNN])
    A, B, Cc, D = map(np.concatenate, (A, B, Cc, D))
    u, v, t = p[B] - p[A], p[Cc] - p[A], p[D] - p[A]
    det = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    ok = np.abs(det) > 0.2 * np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-9  # ほぼ一直線は捨てる
    al = (t[:, 0] * v[:, 1] - t[:, 1] * v[:, 0]) / np.where(ok, det, 1)
    be = (u[:, 0] * t[:, 1] - u[:, 1] * t[:, 0]) / np.where(ok, det, 1)
    ok &= (np.abs(al) < QMAX) & (np.abs(be) < QMAX)
    pa = (al + QMAX) / QSTEP; pb = (be + QMAX) / QSTEP
    return dict(w=(w[A][ok], w[B][ok], w[Cc][ok], w[D][ok]), pa=pa[ok], pb=pb[ok], A=A[ok], B=B[ok], C=Cc[ok], p=p.astype(np.float32))

MASKQ = (1 << QB) - 1
def pack(wv, ia, ib):
    h = np.zeros(len(wv[0]), np.uint64)
    for x in wv: h = (h << np.uint64(WBITS)) | x.astype(np.uint64)
    return ((h << np.uint64(2 * QB))
            | (np.clip(ia, 0, MASKQ).astype(np.uint64) << QB) | np.clip(ib, 0, MASKQ).astype(np.uint64))

def hard(q): return pack(q["w"], np.floor(q["pa"]).astype(int), np.floor(q["pb"]).astype(int))
def soft(q):
    la, lb = np.floor(q["pa"]).astype(int), np.floor(q["pb"]).astype(int)
    na = np.where(q["pa"] - la >= 0.5, la + 1, la - 1); nb = np.where(q["pb"] - lb >= 0.5, lb + 1, lb - 1)
    if MODE == "sim": lb, nb = lb % (1 << QB), nb % (1 << QB)  # 角度は一周する
    return [pack(q["w"], a, b) for a in (la, na) for b in (lb, nb)]

t0 = time.perf_counter()
caches = {n: np.load(f"{C}/{n}.npz") for n in DBV}
rnd = np.random.default_rng(0); samp = []
for n in DBV:
    fr = frames(caches[n], "full_")
    for i in rnd.choice(len(fr), min(100, len(fr)), replace=False):
        d = fr[i][1]; samp.append(d[rnd.choice(len(d), min(200, len(d)), replace=False)])
km = MiniBatchKMeans(1 << WBITS, random_state=0, n_init=3, batch_size=4096).fit(np.unpackbits(np.vstack(samp), axis=1).astype(np.float32))
train_s = time.perf_counter() - t0; print("trained", round(train_s, 1), flush=True)

t0 = time.perf_counter(); cols = {k: [] for k in ("h", "vid", "ts", "gf", "A", "B", "C")}; pts = []; npts = 0
for vi, n in enumerate(DBV):
    for ts, d, kp in frames(caches[n], "full_"):
        q = quads(km, d, kp)
        if q is None: continue
        h = hard(q); m = len(h)
        cols["h"].append(h); cols["vid"].append(np.full(m, vi, np.int8)); cols["ts"].append(np.full(m, ts, np.float32))
        cols["gf"].append(np.full(m, len(pts), np.int32))
        for k in "ABC": cols[k].append(q[k].astype(np.int16))
        pts.append(q["p"]); npts += len(q["p"])
db = {k: np.concatenate(v) for k, v in cols.items()}
o = np.argsort(db["h"], kind="stable"); db = {k: v[o] for k, v in db.items()}
index_s = time.perf_counter() - t0
P = np.zeros((len(pts), NPTS, 2), np.float32)
for i, x in enumerate(pts): P[i, :len(x)] = x
n_entries = len(db["h"]); print("indexed", round(index_s, 1), n_entries, flush=True)
# 1 件 = ハッシュ 4B ＋ フレーム番号 4B ＋ 点番号 3 つ（150 点なら 1B、それより多ければ 2B ずつ）、点座標表は 1 点 4B（int16×2）
IDXB = 1 if NPTS <= 256 else 2  # 点番号 1 つの byte 数
DS = int(len(pts) * NPTS).bit_length()  # DB 点番号の bit 数
db_bytes = n_entries * (8 + 3 * IDXB) + npts * 4

FAST = E("FAST", 0); BACKEND = E("BACKEND", ""); LOOKUP_S = [0.0]; SS_S = [0.0]; T = dict(hash=0.0, hits=0.0, agg=0.0, ss=0.0, fill=0.0)
if BACKEND == "sqlite":
    import sqlite3
    dbfile = f"{H}/b3_{os.environ.get('TAG', 'x')}.sqlite"
    if os.path.exists(dbfile): os.remove(dbfile)
    con = sqlite3.connect(dbfile); t_ = time.perf_counter()
    con.execute("CREATE TABLE video_frames (frame_id INTEGER PRIMARY KEY, video_idx INTEGER, ts REAL, points BLOB)")
    con.execute("CREATE TABLE video_hashes (hash_value INTEGER NOT NULL, frame_id INTEGER NOT NULL, a INTEGER, b INTEGER, c INTEGER)")
    fv = np.zeros(len(pts), np.int64); ft = np.zeros(len(pts))
    fv[db["gf"]] = db["vid"]; ft[db["gf"]] = db["ts"]
    con.executemany("INSERT INTO video_frames VALUES (?,?,?,?)", ((i, int(fv[i]), float(ft[i]), np.asarray(x, np.float32).tobytes()) for i, x in enumerate(pts)))
    con.executemany("INSERT INTO video_hashes VALUES (?,?,?,?,?)", zip(db["h"].astype(np.int64).tolist(), db["gf"].tolist(), db["A"].tolist(), db["B"].tolist(), db["C"].tolist()))
    con.execute("CREATE INDEX idx_video_hashes_hash ON video_hashes (hash_value)"); con.commit(); con.execute("VACUUM")
    print("sqlite built", round(time.perf_counter() - t_, 1), "s", os.path.getsize(dbfile), "bytes", flush=True)
    sqlite_bytes = os.path.getsize(dbfile)

if BACKEND == "pg":
    import io, psycopg2
    con = psycopg2.connect(host="localhost", dbname="vfexp", user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD", "")); cur = con.cursor(); t_ = time.perf_counter()
    cur.execute("DROP TABLE IF EXISTS video_hashes; DROP TABLE IF EXISTS video_frames")
    cur.execute("CREATE TABLE video_frames (frame_id INTEGER PRIMARY KEY, video_idx SMALLINT, ts REAL, points BYTEA)")
    cur.execute("CREATE TABLE video_hashes (hash_value BIGINT NOT NULL, frame_id INTEGER NOT NULL, a SMALLINT, b SMALLINT, c SMALLINT)")
    fv = np.zeros(len(pts), np.int64); ft = np.zeros(len(pts))
    fv[db["gf"]] = db["vid"]; ft[db["gf"]] = db["ts"]
    cur.executemany("INSERT INTO video_frames VALUES (%s,%s,%s,%s)", [(i, int(fv[i]), float(ft[i]), psycopg2.Binary(np.asarray(x, np.float32).tobytes())) for i, x in enumerate(pts)])
    buf = io.StringIO("".join(f"{h}\t{g}\t{a}\t{b}\t{c}\n" for h, g, a, b, c in zip(db["h"].astype(np.int64).tolist(), db["gf"].tolist(), db["A"].tolist(), db["B"].tolist(), db["C"].tolist())))
    cur.copy_from(buf, "video_hashes"); cur.execute("CREATE INDEX idx_video_hashes_hash ON video_hashes (hash_value)"); con.commit()
    con.autocommit = True; cur.execute("VACUUM ANALYZE video_hashes"); cur.execute("VACUUM ANALYZE video_frames")
    cur.execute("SELECT pg_total_relation_size('video_hashes') + pg_total_relation_size('video_frames')"); sqlite_bytes = cur.fetchone()[0]
    print("pg built", round(time.perf_counter() - t_, 1), "s", sqlite_bytes, "bytes", flush=True)

def q_rows(hl):
    if BACKEND == "pg":
        cur.execute("SELECT h.hash_value, h.frame_id, h.a, h.b, h.c, f.video_idx, f.ts FROM video_hashes h JOIN video_frames f ON f.frame_id = h.frame_id WHERE h.hash_value = ANY(%s)", (hl,))
        return cur.fetchall()
    out = []
    for i in range(0, len(hl), 30000):  # SQLite 3.32 以降の変数上限は 32766
        b = hl[i:i + 30000]
        out += con.execute(f"SELECT h.hash_value, h.frame_id, h.a, h.b, h.c, f.video_idx, f.ts FROM video_hashes h JOIN video_frames f ON f.frame_id = h.frame_id WHERE h.hash_value IN ({','.join('?' * len(b))})", b).fetchall()
    return out

def q_points(ids):
    sql = f"SELECT frame_id, points FROM video_frames WHERE frame_id IN ({','.join(map(str, ids))})"
    if BACKEND == "pg": cur.execute(sql); return [(i, bytes(b)) for i, b in cur.fetchall()]
    return con.execute(sql).fetchall()

def fetch(hashes):
    hl = hashes.astype(np.int64).tolist(); out = q_rows(hl)
    if not out: return {k: np.zeros(0, t) for k, t in [("h", np.uint64), ("gf", np.int64), ("ggf", np.int64), ("A", np.int64), ("B", np.int64), ("C", np.int64), ("vid", np.int64), ("ts", np.float32)]}, np.zeros((0, NPTS, 2), np.float32)
    r = np.array(out, dtype=np.float64); o = np.argsort(r[:, 0].astype(np.uint64), kind="stable"); r = r[o]
    ggf = r[:, 1].astype(np.int64); uf, lgf = np.unique(ggf, return_inverse=True)
    rows_ = q_points(uf.tolist())
    pm = {i: np.frombuffer(bl, np.float32).reshape(-1, 2) for i, bl in rows_}
    PP = np.zeros((len(uf), NPTS, 2), np.float32)
    for j, f in enumerate(uf.tolist()): PP[j, :len(pm[f])] = pm[f]
    return dict(h=r[:, 0].astype(np.uint64), gf=lgf, ggf=ggf, A=r[:, 2].astype(np.int64), B=r[:, 3].astype(np.int64), C=r[:, 4].astype(np.int64), vid=r[:, 5].astype(np.int64), ts=r[:, 6].astype(np.float32)), PP

NB = E("NB", 0); NBSS = E("NBSS", 0)  # NB=1 numba 1 スレッド / NB=2 numba 並列、NBSS=1 は範囲探しだけ numpy
if NB:
    import numba

    def _nb_search(H, hs, keep):
        nh, n = hs.shape
        LO = np.empty((nh, n), np.int64); HI = np.empty((nh, n), np.int64)
        for k in range(nh):
            LO[k] = np.searchsorted(H, hs[k], side="left"); HI[k] = np.searchsorted(H, hs[k], side="right")
        return LO, HI

    def _nb_fill(LO, HI, keep, qp, qA, qB, qC, gfa, Aa, Ba, Ca, vida, tsa, ggfa, PP, tsq, qi):
        """当たりから (key, クエリ点, DB 点) を作る。numpy 版と同じ式・同じ型で計算する"""
        nh, n = LO.shape; st = np.zeros(nh * n + 1, np.int64)
        for k in range(nh):
            for i in range(n):
                c = HI[k, i] - LO[k, i]
                st[k * n + i + 1] = c if (c > 0 and c <= MAXHIT and keep[i]) else 0
        st = np.cumsum(st); tot = st[-1]
        key = np.empty(tot, np.int64); qa = np.empty(tot, np.int64); da = np.empty(tot, np.int64)
        two_pi = 2 * np.pi; t32 = np.float32(tsq); o32 = np.float32(OFF_S)
        for ki in numba.prange(nh * n):  # NB=2 なら並列（各 (ハッシュ, 三つ組) の書き込み先は st で決まっている）
            k = ki // n; i = ki % n; r = st[ki]
            if st[ki + 1] == r: continue
            a_, b_, c_ = qA[i], qB[i], qC[i]
            v00 = qp[b_, 0] - qp[a_, 0]; v10 = qp[b_, 1] - qp[a_, 1]  # 列 0 = AB
            v01 = qp[c_, 0] - qp[a_, 0]; v11 = qp[c_, 1] - qp[a_, 1]  # 列 1 = AC
            dq = v00 * v11 - v01 * v10
            i00 = v11 / dq; i01 = -v01 / dq; i10 = -v10 / dq; i11 = v00 / dq
            for e in range(LO[k, i], HI[k, i]):
                g = gfa[e]; pa0 = PP[g, Aa[e], 0]; pa1 = PP[g, Aa[e], 1]
                d00 = np.float64(PP[g, Ba[e], 0] - pa0); d10 = np.float64(PP[g, Ba[e], 1] - pa1)
                d01 = np.float64(PP[g, Ca[e], 0] - pa0); d11 = np.float64(PP[g, Ca[e], 1] - pa1)
                m00 = d00 * i00 + d01 * i10; m01 = d00 * i01 + d01 * i11
                m10 = d10 * i00 + d11 * i10; m11 = d10 * i01 + d11 * i11
                det = abs(m00 * m11 - m01 * m10); fr2 = m00 ** 2 + m01 ** 2 + m10 ** 2 + m11 ** 2
                rr = np.sqrt(max(fr2 * fr2 - 4 * det * det, 0.0))
                s0 = np.sqrt((fr2 + rr) / 2); s1 = np.sqrt(max(fr2 - rr, 0.0) / 2)
                sc = np.log2(np.sqrt(max(s0 * s1, 1e-9))); an = np.log2(s0 / max(s1, 1e-9))
                rot = np.arctan2(m10 - m01, m00 + m11) % two_pi
                off_b = min(max(np.int64(np.rint((tsa[e] - t32) / o32)) + 512, 0), 1023)
                rot_b = np.int64(np.floor(rot / two_pi * ROT_B)) % ROT_B
                sc_b = min(max(np.int64(np.rint(sc / SC_B)) + 16, 0), 31)
                an_b = min(max(np.int64(np.rint(an / AN_B)), 0), 7)
                key[r] = (((np.int64(vida[e]) << 10 | off_b) << 4 | rot_b) << 5 | sc_b) << 3 | an_b
                qa[r] = qi * NPTS + a_; da[r] = np.int64(ggfa[e]) * NPTS + Aa[e]; r += 1
        return key, qa, da
    nb_search = numba.njit(cache=True)(_nb_search)
    nb_fill = numba.njit(cache=(NB == 1), parallel=(NB == 2))(_nb_fill)

    def nb_rows(H, hs, keep, *rest):
        t_ = time.perf_counter()
        if NBSS: LO, HI = np.searchsorted(H, hs, "left"), np.searchsorted(H, hs, "right")
        else: LO, HI = nb_search(H, hs, keep)
        T["ss"] += time.perf_counter() - t_; t_ = time.perf_counter()
        r = nb_fill(LO, HI, keep, *rest); T["fill"] += time.perf_counter() - t_
        return r

def score(fr):
    rows = []; t_h = time.perf_counter()
    qs_ = [(qi, ts, q, soft(q)) for qi, (ts, d, kp) in enumerate(fr) for q in [quads(km, d, kp)] if q is not None]
    T["hash"] += time.perf_counter() - t_h; t_h = time.perf_counter()
    if not qs_: return {}, {}, {}
    if BACKEND:  # クエリの全ハッシュをまとめて DB の完全一致索引で引き、手元の配列にする
        t_ = time.perf_counter(); src, PP = fetch(np.unique(np.concatenate([h for x in qs_ for h in x[3]]))); LOOKUP_S[0] += time.perf_counter() - t_
    else:
        src, PP = dict(db, ggf=db["gf"]), P
    for qi, ts, q, hs in qs_:
        hq = hs[0]
        u, inv = np.unique(hq, return_inverse=True); keep = np.bincount(inv)[inv] <= QBURST  # 同一フレームの反復を捨てる
        qp = q["p"].astype(np.float64)
        if NB:
            rows.append(nb_rows(src["h"], np.stack(hs), keep, qp, q["A"].astype(np.int64), q["B"].astype(np.int64), q["C"].astype(np.int64),
                                src["gf"], src["A"], src["B"], src["C"], src["vid"], src["ts"], src["ggf"], PP, ts, qi))
            continue
        Vq = np.stack([qp[q["B"]] - qp[q["A"]], qp[q["C"]] - qp[q["A"]]], 2)  # 列 = AB, AC
        for h in hs:
            t_ = time.perf_counter(); lo = np.searchsorted(src["h"], h, "left"); hi = np.searchsorted(src["h"], h, "right"); SS_S[0] += time.perf_counter() - t_
            cnt = hi - lo; sel = (cnt > 0) & (cnt <= MAXHIT) & keep
            if not sel.any(): continue
            cs = cnt[sel]; qq = np.repeat(np.nonzero(sel)[0], cs); e = np.repeat(lo[sel] - np.cumsum(cs) + cs, cs) + np.arange(cs.sum())
            gf = src["gf"][e]; pa, pb, pc = PP[gf, src["A"][e]], PP[gf, src["B"][e]], PP[gf, src["C"][e]]
            Vd = np.stack([pb - pa, pc - pa], 2).astype(np.float64)
            vq = Vq[qq]; dq = vq[:, 0, 0] * vq[:, 1, 1] - vq[:, 0, 1] * vq[:, 1, 0]
            iq = np.stack([np.stack([vq[:, 1, 1], -vq[:, 0, 1]], 1), np.stack([-vq[:, 1, 0], vq[:, 0, 0]], 1)], 1) / dq[:, None, None]
            M = Vd @ iq  # クエリ→DB のアフィン行列
            if FAST:  # 2x2 の特異値を閉じた式で出す（s0*s1=|det|、s0^2+s1^2=Frobenius^2）
                det = np.abs(M[:, 0, 0] * M[:, 1, 1] - M[:, 0, 1] * M[:, 1, 0]); fr2 = (M ** 2).sum((1, 2))
                r_ = np.sqrt(np.maximum(fr2 * fr2 - 4 * det * det, 0)); s = np.stack([np.sqrt((fr2 + r_) / 2), np.sqrt(np.maximum(fr2 - r_, 0) / 2)], 1)
            else:
                s = np.linalg.svd(M, compute_uv=False)
            sc = np.log2(np.sqrt(np.maximum(s[:, 0] * s[:, 1], 1e-9))); an = np.log2(s[:, 0] / np.maximum(s[:, 1], 1e-9))
            rot = np.arctan2(M[:, 1, 0] - M[:, 0, 1], M[:, 0, 0] + M[:, 1, 1]) % (2 * np.pi)
            off_b = np.clip(np.round((src["ts"][e] - ts) / OFF_S).astype(np.int64) + 512, 0, 1023)
            rot_b = np.floor(rot / (2 * np.pi) * ROT_B).astype(np.int64) % ROT_B
            sc_b = np.clip(np.round(sc / SC_B).astype(np.int64) + 16, 0, 31)
            an_b = np.clip(np.round(an / AN_B).astype(np.int64), 0, 7)
            key = (((src["vid"][e].astype(np.int64) << 10 | off_b) << 4 | rot_b) << 5 | sc_b) << 3 | an_b  # 25bit
            qa = (qi * NPTS + q["A"][qq]).astype(np.int64)  # クエリ点
            da = (src["ggf"][e].astype(np.int64) * NPTS + src["A"][e])  # DB 点
            rows.append((key, qa, da))
    T["hits"] += time.perf_counter() - t_h; t_h = time.perf_counter()
    if not rows: return {}, {}, {}
    key, qa, da = (np.concatenate(x) for x in zip(*rows))
    if os.environ.get("DUMP") and not os.path.exists(os.environ["DUMP"]): np.savez(os.environ["DUMP"], key=key, qa=qa, da=da)
    # (key, クエリ点) と (key, DB 点) の重複なし票。フレームごとに CAP で頭打ち（1 本の int64 に詰めて unique）
    QS = int(qa.max()).bit_length()
    if FAST:  # 値だけの np.unique は hash 経路で遅いので、sort して隣と比べる
        def uq(a): a = np.sort(a); return a[np.r_[True, a[1:] != a[:-1]]]
    else:
        uq = np.unique
    kq = uq(key << QS | qa); kd = uq(key << DS | da)
    kf, nf = np.unique((kq >> QS) << 7 | ((kq & ((1 << QS) - 1)) // NPTS), return_counts=True)
    keys, capped = np.unique(kf >> 7, return_inverse=True); sq = np.bincount(capped, weights=np.minimum(nf, CAP))
    kk, nd = np.unique(kd >> DS, return_counts=True)
    if FAST:  # 映像ごとの最大票を配列のまま出す（keys は昇順、vid は上位ビット）
        j = np.searchsorted(kk, keys); j = np.minimum(j, len(kk) - 1); v = np.minimum(sq, np.where(kk[j] == keys, nd[j], 0))
        vid = keys >> 22; fcnt = np.bincount(capped); o = np.lexsort((-v, vid)); first = o[np.r_[True, vid[o][1:] != vid[o][:-1]]]
        first = first[v[first] > 0]
        T["agg"] += time.perf_counter() - t_h
        return ({int(vid[i]): float(v[i]) for i in first}, {int(vid[i]): (((int(keys[i]) >> 12) & 1023) - 512) * OFF_S for i in first}, {int(vid[i]): int(fcnt[i]) for i in first})
    ndm = dict(zip(kk.tolist(), nd.tolist()))
    best, off, nfr = {}, {}, {}
    for k, s_, fcount in zip(keys.tolist(), sq.tolist(), np.bincount(capped).tolist()):
        v = min(s_, ndm.get(k, 0)); vid = k >> 22
        if v > best.get(vid, 0): best[vid] = v; off[vid] = (((k >> 12) & 1023) - 512) * OFF_S; nfr[vid] = fcount
    return best, off, nfr

out = []
LIMIT = E("LIMIT", 0)
_ql = json.load(open(os.path.expanduser(os.environ.get("META", f"{H}/q/meta.json"))))
score(frames(np.load(f"{C}/{os.path.basename(_ql[0]['file'])[:-4]}.npz"), "full_"))  # numba のコンパイルをここで済ませる
for k_ in T: T[k_] = 0.0
for q in json.load(open(os.path.expanduser(os.environ.get("META", f"{H}/q/meta.json"))))[::(192 // LIMIT if LIMIT else 1)]:
    name = os.path.basename(q["file"])[:-4]; z = np.load(f"{C}/{name}.npz")
    t0 = time.perf_counter()
    best, off, nfr = score(frames(z, "full_"))
    if len(z["pip_off"]) > 1:
        pb_, po, pn = score(frames(z, "pip_"))
        for v, c in pb_.items():
            if c > best.get(v, 0): best[v] = c; off[v] = po[v]; nfr[v] = pn[v]
    for sx in STRETCH:  # 横に伸ばしたクエリでも引き、映像ごとに一番票の多い結果を採る
        zs = np.load(f"{C}/{name}__{sx if sx[0].isalpha() else 'x' + sx}.npz")
        sb, so, sn = score(frames(zs, "full_"))
        for v, c in sb.items():
            if c > best.get(v, 0): best[v] = c; off[v] = so[v]; nfr[v] = sn[v]
    qs = time.perf_counter() - t0
    top = max(best, key=best.get) if best else None
    second = sorted(best.values())[-2] if len(best) > 1 else 0.0
    out.append(dict(q, name=name, sec=qs, top=DBV[top] if top is not None else None, score=float(best[top]) if best else 0.0,
                    second=float(second), frames=int(nfr[top]) if best else 0, off=float(off[top]) if best else None,
                    pos_ok=bool(top is not None and abs(off[top] - q["start"]) <= OFF_S * 2 + 2)))
tag = os.environ.get("TAG", "B2")
json.dump(dict(variant=tag, backend=BACKEND, lookup_s=LOOKUP_S[0], searchsorted_s=SS_S[0], T=T, sqlite_bytes=globals().get("sqlite_bytes"), params=dict(STRETCH=STRETCH, MODE=MODE, NPTS=NPTS, KNN=KNN, WBITS=WBITS, COMBOS=COMBOS, QSTEP=QSTEP, MAXHIT=MAXHIT, QBURST=QBURST, CAP=CAP),
               train_s=train_s, index_s=index_s, db_bytes=db_bytes, n_entries=n_entries, results=out), open(f"{H}/res_{tag}.json", "w"))
print(tag, "done", n_entries, flush=True)
