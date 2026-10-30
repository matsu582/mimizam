"""
時間をまたぐ 3 点ハッシュによる映像指紋（音声の三つ組の映像版）

決まった間隔で取ったフレームの AKAZE 特徴点から、
フレーム i の点 a（アンカー）・同じフレームで a の近くの点 c・後ろのフレーム j で a の位置の近くの点 b
の 3 点で 1 つのハッシュを作る。ハッシュは 3 点の視覚語と、a の大きさ・向きを基準にした c・b の距離・方向、
大きさの比を量子化したもの。照合は完全一致で引き、(映像, 時刻ずれ, 回転, 拡大率) の投票で判定する。
RANSAC・生記述子は使わない。

前後のフレームの同じ位置に同じ視覚語がある点（静止点: 重ねた文字・ロゴ・止まった画面）は、
ハッシュに使わない。静止点を全点で除いてから、反応の強い順に max_points 点を使う。
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .video_fingerprinter import _create_akaze, normalize_frame

logger = logging.getLogger(__name__)

TWO_PI = 2 * np.pi


@dataclass
class VideoHashConfig:
    """時間 3 点ハッシュの設定"""

    # DB 側: step 秒ごとのフレームを、pair_gap 枚先（= step×pair_gap 秒後）のフレームと組む
    db_step: float = 0.5
    db_long_side: int = 640
    db_static_px: float = 2.0
    # 横に縮めた版も登録する倍率（4:3 などの縦横比の変化に備える）
    db_stretch: Tuple[float, ...] = (1 / 1.33, 1 / 1.78)
    # クエリ側: query_step 秒ごとのフレームを次のフレームと組む（query_step = db_step×pair_gap）
    query_step: float = 1.0
    query_long_side: int = 960
    query_static_px: float = 3.0
    pair_gap: int = 2
    max_points: int = 300
    word_bits: int = 6
    # 相手の点を取る半径（a の大きさの倍数）、大きさの比（log2）の下限と幅
    radius: float = 3.0
    ratio_low: float = -0.5
    ratio_width: float = 2.0
    # 照合: 1 つのハッシュで DB に max_hits 件より多く当たるものは捨てる
    max_hits: int = 100
    offset_bin: float = 4.0
    rot_bins: int = 16
    scale_bin: float = 0.5
    # 判定: 1 位の票 − 2 位の票がこれを超えたら一致
    margin_threshold: float = 11.0
    codebook_samples: int = 200000


@dataclass
class HashFrame:
    """1 フレームの点（静止点を除いたあとの上位点）"""
    timestamp: float
    points: np.ndarray  # (n, 2) float64
    sizes: np.ndarray  # (n,)
    angles: np.ndarray  # (n,) rad
    descriptors: np.ndarray  # (n, 61) uint8


def read_frames(path: str, step: float, long_side: int,
                stretch: Tuple[float, ...] = ()) -> List[List[Tuple[float, np.ndarray]]]:
    """step 秒ごとのフレームを読み、版（元＋横縮小）ごとのグレー画像の列を返す"""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    versions: List[List[Tuple[float, np.ndarray]]] = [[] for _ in range(1 + len(stretch))]
    fi, nxt = 0, 0.0
    try:
        while cap.grab():
            t = fi / fps
            if t + 1e-6 >= nxt:
                ok, img = cap.retrieve()
                if ok:
                    nxt += step
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    for v, sx in enumerate((1.0,) + tuple(stretch)):
                        g = gray if v == 0 else cv2.resize(
                            gray, (max(1, int(round(gray.shape[1] * sx))), gray.shape[0]),
                            interpolation=cv2.INTER_AREA)
                        versions[v].append((t, normalize_frame(g, long_side, allow_upscale=True)))
            fi += 1
    finally:
        cap.release()
    return versions


def detect(images: List[Tuple[float, np.ndarray]]):
    """AKAZE の全点を (ts, 座標, 大きさ, 向き(rad), 反応, 記述子) で返す"""
    akaze = _create_akaze()
    out = []
    for ts, g in images:
        kps, desc = akaze.detectAndCompute(g, None)
        if desc is None or not kps:
            out.append((ts, np.zeros((0, 2)), np.zeros(0), np.zeros(0), np.zeros(0), np.zeros((0, 61), np.uint8)))
            continue
        k = np.array([(p.pt[0], p.pt[1], p.size, p.angle, p.response) for p in kps], np.float64)
        out.append((ts, k[:, :2], k[:, 2], np.deg2rad(k[:, 3]), k[:, 4], desc))
    return out


class VideoHasher:
    """時間 3 点ハッシュの作成（視覚語のモデルを持つ）"""

    def __init__(self, config: Optional[VideoHashConfig] = None):
        self.config = config or VideoHashConfig()
        self.centers: Optional[np.ndarray] = None

    @property
    def is_trained(self) -> bool:
        return self.centers is not None

    def train(self, descriptor_sets: List[np.ndarray]) -> None:
        """視覚語（2^word_bits 語）を k-means で学習する"""
        from sklearn.cluster import MiniBatchKMeans
        d = np.vstack([x for x in descriptor_sets if len(x)])
        n = 1 << self.config.word_bits
        if len(d) < n:
            raise ValueError("Not enough descriptors to train visual words")
        rng = np.random.default_rng(0)
        if len(d) > self.config.codebook_samples:
            d = d[rng.choice(len(d), self.config.codebook_samples, replace=False)]
        km = MiniBatchKMeans(n, random_state=0, n_init=3, batch_size=4096).fit(
            np.unpackbits(d, axis=1).astype(np.float32))
        self.centers = km.cluster_centers_.astype(np.float32)

    def words(self, desc: np.ndarray) -> np.ndarray:
        x = np.unpackbits(desc, axis=1).astype(np.float32)
        c = self.centers
        return np.argmin((x ** 2).sum(1, keepdims=True) - 2 * x @ c.T + (c ** 2).sum(1), axis=1)

    def select(self, raw, static_px: float):
        """静止点を全点で除き、残りから反応の強い順に max_points 点を選ぶ。(ts, 座標, 大きさ, 向き, 視覚語) の列"""
        W = [self.words(r[5]) if len(r[5]) else np.zeros(0, np.int64) for r in raw]
        trees = [cKDTree(r[1]) if len(r[1]) else None for r in raw]
        out = []
        for i, (ts, p, sz, th, resp, _) in enumerate(raw):
            st = np.zeros(len(p), bool)
            if static_px > 0 and len(p):
                for j in (i - 1, i + 1):
                    if 0 <= j < len(raw) and trees[j] is not None:
                        k = min(8, len(raw[j][1]))
                        d, nb = trees[j].query(p, k=k, distance_upper_bound=static_px)
                        d, nb = d.reshape(len(p), k), nb.reshape(len(p), k)
                        ok = np.isfinite(d)
                        wj = np.append(W[j], -1)[np.where(ok, nb, len(W[j]))]
                        st |= (ok & (wj == W[i][:, None])).any(1)
            keep = np.nonzero(~st)[0]
            keep = keep[np.argsort(-resp[keep], kind="stable")][:self.config.max_points]
            out.append((ts, p[keep], sz[keep], th[keep], W[i][keep].astype(np.int64)))
        return out

    def _nbr(self, p, sz, pj, szj, same):
        c = self.config
        if not len(p) or not len(pj):
            return (np.zeros(0, np.int64),) * 2 + (np.zeros(0),) * 3
        nb = cKDTree(pj).query_ball_point(p, c.radius * sz)
        A = np.repeat(np.arange(len(p)), [len(x) for x in nb])
        if not len(A):
            return (np.zeros(0, np.int64),) * 2 + (np.zeros(0),) * 3
        X = np.concatenate([np.array(x, np.int64) for x in nb])
        rho = np.log2(szj[X] / sz[A])
        dv = pj[X] - p[A]
        dist = np.linalg.norm(dv, axis=1) / sz[A]
        ok = (rho >= c.ratio_low) & (rho < c.ratio_low + c.ratio_width) & ((dist > 0.5) if same else True)
        A, X, rho, dv, dist = A[ok], X[ok], rho[ok], dv[ok], np.maximum(dist[ok], 1e-3)
        dq = np.clip(np.floor((np.log2(dist) + 2) / 0.5), 0, 15)
        rq = np.clip(np.floor((rho - c.ratio_low) / 0.5), 0, 3)
        return A, X, dq, np.arctan2(dv[:, 1], dv[:, 0]), rq

    def hashes(self, frames, gap: int, k_code: int, soft: bool):
        """フレーム i と i+gap の組からハッシュを作る。(ハッシュ, フレーム番号, 点番号)。
        k_code はハッシュに入れる「何枚先か」（DB の枚数で数える）。soft なら方向の隣の箱も作る（クエリ側）"""
        wb = self.config.word_bits
        H_, FI, AI = [], [], []
        for i in range(len(frames) - gap):
            _, p, sz, th, w = frames[i]
            _, pj, szj, _, wj = frames[i + gap]
            Ac, Cc, dqc, dirc, rqc = self._nbr(p, sz, p, sz, True)
            Ab, Bb, dqb, dirb, rqb = self._nbr(p, sz, pj, szj, False)
            if not len(Ac) or not len(Ab):
                continue
            o = np.argsort(Ac, kind="stable")
            Ac, Cc, dqc, dirc, rqc = Ac[o], Cc[o], dqc[o], dirc[o], rqc[o]
            lo = np.searchsorted(Ac, Ab, "left")
            cnt = np.searchsorted(Ac, Ab, "right") - lo
            ib = np.repeat(np.arange(len(Ab)), cnt)
            ic = np.repeat(lo - np.cumsum(cnt) + cnt, cnt) + np.arange(cnt.sum())
            if not len(ib):
                continue
            A = Ab[ib]
            drc = (dirc[ic] - th[A]) % TWO_PI / TWO_PI * 16
            drb = (dirb[ib] - th[A]) % TWO_PI / TWO_PI * 16
            fc, fb = np.floor(drc).astype(np.int64), np.floor(drb).astype(np.int64)
            nc = np.where(drc - fc >= 0.5, fc + 1, fc - 1) % 16
            nbb = np.where(drb - fb >= 0.5, fb + 1, fb - 1) % 16
            base = (((w[A] << wb | w[Cc[ic]]) << wb | wj[Bb[ib]]) << 2 | (k_code - 1)) << 4 | dqc[ic].astype(np.int64)
            base = ((base << 4 | dqb[ib].astype(np.int64)) << 2 | rqc[ic].astype(np.int64)) << 2 | rqb[ib].astype(np.int64)
            for c_ in ([fc % 16, nc] if soft else [fc % 16]):
                for b_ in ([fb % 16, nbb] if soft else [fb % 16]):
                    H_.append((base << 4 | c_) << 4 | b_)
                    FI.append(np.full(len(A), i, np.int64))
                    AI.append(A.astype(np.int64))
        if not H_:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64)
        return np.concatenate(H_), np.concatenate(FI), np.concatenate(AI)

    def db_rows(self, frames) -> List[Tuple[int, float, int, float, float]]:
        """DB に入れる行 (ハッシュ, 時刻, アンカー番号, アンカーの大きさ, 向き)。アンカー番号は版の中の通し番号"""
        c = self.config
        h, fi, ai = self.hashes(frames, c.pair_gap, c.pair_gap, False)
        if not len(h):
            return []
        h, idx = np.unique(np.stack([h, fi * c.max_points + ai], 1), axis=0).T
        fi, ai = idx // c.max_points, idx % c.max_points
        ts = np.array([f[0] for f in frames])[fi]
        sz, th = point_table(frames, c.max_points)
        sz, th = sz[fi, ai], th[fi, ai]
        return list(zip(h.tolist(), ts.tolist(), idx.tolist(), sz.tolist(), th.tolist()))

    def query_hashes(self, frames):
        """クエリのハッシュ（1 枚先＝DB の pair_gap 枚先として作る）"""
        return self.hashes(frames, 1, self.config.pair_gap, True)

    def save(self, path: str) -> None:
        np.savez(path, centers=self.centers, word_bits=self.config.word_bits)

    def load(self, path: str) -> None:
        z = np.load(path)
        if int(z["word_bits"]) != self.config.word_bits:
            raise ValueError("word_bits of the model does not match the config")
        self.centers = z["centers"].astype(np.float32)


def point_table(frames, max_points: int):
    """フレームごとの点の大きさ・向きを (フレーム数, max_points) の表にする"""
    sz = np.ones((len(frames), max_points))
    th = np.zeros((len(frames), max_points))
    for i, f in enumerate(frames):
        sz[i, :len(f[2])] = f[2]
        th[i, :len(f[3])] = f[3]
    return sz, th


def vote(config: VideoHashConfig, frames, qh, qf, qa, rows) -> Dict[str, Dict[str, float]]:
    """DB から引いた行で投票する。rows は (ハッシュ, 映像ID, 版, 時刻, アンカー番号, 大きさ, 向き) の列。
    戻り値: {映像ID: {"votes": 最高票, "offset": DB 時刻 − クエリ時刻（秒）}}"""
    c = config
    if not rows or not len(qh):
        return {}
    rh = np.array([r[0] for r in rows], np.int64)
    o = np.argsort(rh, kind="stable")
    rh = rh[o]
    rows = [rows[i] for i in o]
    vids = sorted({r[1] for r in rows})
    vix = {v: i for i, v in enumerate(vids)}
    rv = np.array([vix[r[1]] for r in rows], np.int64)
    rver = np.array([r[2] for r in rows], np.int64)
    rts = np.array([r[3] for r in rows], np.float64)
    ranc = np.array([r[4] for r in rows], np.int64)
    rsz = np.array([r[5] for r in rows], np.float64)
    rth = np.array([r[6] for r in rows], np.float64)
    lo = np.searchsorted(rh, qh, "left")
    cnt = np.searchsorted(rh, qh, "right") - lo
    sel = (cnt > 0) & (cnt <= c.max_hits)
    if not sel.any():
        return {}
    cs = cnt[sel]
    qq = np.repeat(np.nonzero(sel)[0], cs)
    e = np.repeat(lo[sel] - np.cumsum(cs) + cs, cs) + np.arange(cs.sum())
    qf_, qa_ = qf[qq], qa[qq]
    qts = np.array([f[0] for f in frames])[qf_]
    qsz, qth = point_table(frames, c.max_points)
    qsz, qth = qsz[qf_, qa_], qth[qf_, qa_]
    sc = np.log2(rsz[e] / qsz)
    rot = (rth[e] - qth) % TWO_PI
    off_b = np.clip(np.round((rts[e] - qts) / c.offset_bin).astype(np.int64) + (1 << 20), 0, (1 << 21) - 1)
    rb = np.floor(rot / TWO_PI * c.rot_bins).astype(np.int64) % c.rot_bins
    sb = np.clip(np.round(sc / c.scale_bin).astype(np.int64) + 16, 0, 31)
    key = ((rv[e] << 21 | off_b) << 5 | rb) << 5 | sb
    # 1 票は (クエリのアンカー点, DB のアンカー点) それぞれ重複なし
    qid = qf_ * c.max_points + qa_
    did = (rv[e] << 8 | rver[e]) << 32 | ranc[e]
    k1, n1 = np.unique(np.unique(np.stack([key, qid], 1), axis=0)[:, 0], return_counts=True)
    k2, n2 = np.unique(np.unique(np.stack([key, did], 1), axis=0)[:, 0], return_counts=True)
    j = np.minimum(np.searchsorted(k2, k1), len(k2) - 1)
    v = np.minimum(n1, np.where(k2[j] == k1, n2[j], 0))
    best: Dict[str, Dict[str, float]] = {}
    for i in np.argsort(-v, kind="stable"):
        if v[i] <= 0:
            break
        vid = vids[int(k1[i] >> 31)]
        if vid not in best:
            best[vid] = {"votes": float(v[i]),
                         "offset": float(((int(k1[i]) >> 10) & ((1 << 21) - 1)) - (1 << 20)) * c.offset_bin}
    return best
