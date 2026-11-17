"""
PiP（Picture-in-Picture）矩形検出

フレーム内に重畳された別映像の矩形領域を検出する。

検出アルゴリズム:
  1. 時間分散マップのプロジェクション・2D連結成分解析で矩形候補を作る
  2. 隣り合う画素（_CORR_GAP 画素離れ）の時間方向の相関を求める。PiP の辺では
     内側と外側が別の映像なので相関が弱くなる
  3. 相関の弱い縦線・横線の組み合わせも矩形候補に加える
  4. 各候補の辺ごとに「辺の上の相関の弱さ − 近くの基準線の相関の弱さ」を求め、
     辺の位置を前後 _EDGE_SHIFT 画素で合わせ直す。黒い背景など相関が使えない辺は
     「内側が動き外側が止まっているか」（時間方向の標準偏差の差）で補う
  5. フレームの端に接しない辺の最小値を pip_score とし、閾値以上を返す
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# PiP検出の内部処理用解像度（長辺）
_ANALYSIS_LONG_SIDE = 480

# PiP判定の閾値（辺の時間相関の弱さの差。辺のうち最も弱いもの）
DEFAULT_PIP_SCORE_THRESHOLD = 0.4

# 辺の時間相関の採点
_CORR_GAP = 4          # 相関を取る画素の間隔
_CORR_EPS = 25.0       # 動きの無い画素で相関が暴れないための分母の下駄（輝度の標準偏差）
_EDGE_SHIFT = 4        # 辺の位置を合わせ直す幅（画素）
_LINE_PEAKS = 12       # 縦線・横線の候補として拾う数（各方向）
_STD_EPS = 2.0         # 標準偏差の差で補うときの分母の下駄


@dataclass
class PipRegion:
    """検出されたPiP矩形領域"""
    x: int
    y: int
    w: int
    h: int
    area_ratio: float
    pip_score: float
    method: str = ""


def detect_pip_regions(
    frames: List[np.ndarray],
    pip_score_threshold: float = DEFAULT_PIP_SCORE_THRESHOLD,
    min_area_ratio: float = 0.03,
    max_area_ratio: float = 0.75,
) -> List[PipRegion]:
    """
    フレーム群からPiP矩形領域を検出

    Args:
        frames: BGRフレームのリスト（同一映像の複数フレーム）
        pip_score_threshold: PiP判定の閾値（高いほど厳密）
        min_area_ratio: 最小面積比（フレーム面積に対する割合）
        max_area_ratio: 最大面積比

    Returns:
        検出されたPiP領域のリスト（pip_score降順）
    """
    if len(frames) < 5:
        return []

    h, w = frames[0].shape[:2]
    scale = min(1.0, _ANALYSIS_LONG_SIDE / max(h, w))
    if scale < 1.0:
        resized = [
            cv2.resize(f, None, fx=scale, fy=scale) for f in frames
        ]
    else:
        resized = frames
        scale = 1.0

    gray_stack = np.array([
        cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for f in resized
    ])
    variance_map = np.var(gray_stack, axis=0)
    rh, rw = variance_map.shape[:2]

    # 矩形候補: 分散マップの2手法と、相関の弱い線の組み合わせ
    candidates = _detect_by_projection(
        variance_map, scale, min_area_ratio, max_area_ratio
    )
    candidates += _detect_by_2d_analysis(
        variance_map, scale, min_area_ratio, max_area_ratio
    )
    candidates += _merge_contained_regions(
        _deduplicate(list(candidates)), scale, rw, rh
    )
    weak_h, weak_v = _temporal_corr_weakness(gray_stack)
    candidates += _corr_line_candidates(
        weak_h, weak_v, scale, rh, rw, min_area_ratio, max_area_ratio
    )
    raw_candidate_count = len(candidates)

    rects = np.array([
        (int(r.x * scale), int(r.y * scale),
         int((r.x + r.w) * scale), int((r.y + r.h) * scale))
        for r in candidates
    ], dtype=np.int64).reshape(-1, 4)
    rects = rects[
        ((rects[:, 2] - rects[:, 0]) >= 10)
        & ((rects[:, 3] - rects[:, 1]) >= 10)
    ]
    if len(rects) == 0:
        return []

    lines = _LineMeans(weak_h, weak_v, gray_stack.std(axis=0))
    scores, fitted = _score_rects(lines, rh, rw, rects)

    frame_area = float(h * w)
    result: List[PipRegion] = []
    for i in np.argsort(-scores, kind="stable"):
        if scores[i] < pip_score_threshold:
            break
        x1, y1, x2, y2 = fitted[i]
        rx, ry = int(x1 / scale), int(y1 / scale)
        region = PipRegion(
            x=rx, y=ry,
            w=int((x2 - x1) / scale), h=int((y2 - y1) / scale),
            area_ratio=0.0, pip_score=float(scores[i]), method="edge_corr",
        )
        region.area_ratio = region.w * region.h / frame_area
        if all(_iou(region, k) <= 0.5 for k in result):
            result.append(region)
        if len(result) >= 5:
            break

    if result:
        logger.info(
            f"PiP rectangle detection: {len(result)} found "
            f"(out of {raw_candidate_count} candidates)"
        )

    return result


def _iou(a: PipRegion, b: PipRegion) -> float:
    iw = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    ih = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = iw * ih
    return inter / (a.w * a.h + b.w * b.h - inter + 1e-9)


def _temporal_corr_weakness(
    gray_stack: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """隣り合う画素の時間方向の相関の弱さ（1−相関）

    Returns:
        (weak_h[y, x]: 画素 x と x+_CORR_GAP の間, weak_v[y, x]: 画素 y と y+_CORR_GAP の間)
    """
    k = _CORR_GAP
    g = gray_stack - gray_stack.mean(axis=0, keepdims=True)
    v = (g * g).mean(axis=0)
    ch = (g[:, :, :-k] * g[:, :, k:]).mean(axis=0) / (
        np.sqrt(v[:, :-k] * v[:, k:]) + _CORR_EPS
    )
    cv = (g[:, :-k, :] * g[:, k:, :]).mean(axis=0) / (
        np.sqrt(v[:-k, :] * v[k:, :]) + _CORR_EPS
    )
    return 1 - ch, 1 - cv


def _line_peaks(profile: np.ndarray, n: int, sep: int = 6) -> List[int]:
    """大きい順に n 個（sep 画素以内の重複は除く）の位置を昇順で返す"""
    out: List[int] = []
    for i in np.argsort(-profile):
        if profile[i] <= 0:
            break
        if all(abs(int(i) - j) > sep for j in out):
            out.append(int(i))
        if len(out) >= n:
            break
    return sorted(out)


def _corr_line_candidates(
    weak_h: np.ndarray, weak_v: np.ndarray, scale: float,
    rh: int, rw: int, min_area_ratio: float, max_area_ratio: float,
) -> List[PipRegion]:
    """相関の弱い縦線・横線を投影で拾い、その組み合わせを矩形候補にする"""
    k = _CORR_GAP
    o = k + 3

    def contrast(d: np.ndarray, axis: int) -> np.ndarray:
        pad = ((0, 0), (o, o)) if axis == 0 else ((o, o), (0, 0))
        a = np.pad(d, pad, mode="edge")
        if axis == 0:
            left, right = a[:, :-2 * o], a[:, 2 * o:]
        else:
            left, right = a[:-2 * o, :], a[2 * o:, :]
        return np.clip(d - np.minimum(left, right), 0, None)

    xs = [p + k // 2 for p in _line_peaks(contrast(weak_h, 0).mean(0), _LINE_PEAKS)]
    ys = [p + k // 2 for p in _line_peaks(contrast(weak_v, 1).mean(1), _LINE_PEAKS)]
    rects: List[PipRegion] = []
    for i, x1 in enumerate(xs):
        for x2 in xs[i + 1:]:
            for j, y1 in enumerate(ys):
                for y2 in ys[j + 1:]:
                    a = (x2 - x1) * (y2 - y1) / (rh * rw)
                    if min_area_ratio <= a <= max_area_ratio:
                        rects.append(PipRegion(
                            int(x1 / scale), int(y1 / scale),
                            int((x2 - x1) / scale), int((y2 - y1) / scale),
                            a, 0.0, "corr",
                        ))
    return rects


class _LineMeans:
    """相関の弱さ・標準偏差の、任意の縦線分・横線分の平均を O(1) で返す累積和"""

    def __init__(self, weak_h: np.ndarray, weak_v: np.ndarray, std: np.ndarray):
        self.ch = np.vstack([
            np.zeros((1, weak_h.shape[1])),
            np.cumsum(weak_h, 0, dtype=np.float64),
        ])
        self.cv = np.hstack([
            np.zeros((weak_v.shape[0], 1)),
            np.cumsum(weak_v, 1, dtype=np.float64),
        ])
        self.sc = np.vstack([
            np.zeros((1, std.shape[1])), np.cumsum(std, 0, dtype=np.float64),
        ])
        self.sr = np.hstack([
            np.zeros((std.shape[0], 1)), np.cumsum(std, 1, dtype=np.float64),
        ])
        self.nh, self.nv = weak_h.shape[1], weak_v.shape[0]


def _edge_scores(
    lines: _LineMeans, axis: int, pos: np.ndarray,
    a: np.ndarray, b: np.ndarray, valid: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """辺ごとの採点を全候補まとめて行う（valid でない辺は nan）

    辺の位置を前後 _EDGE_SHIFT で動かして相関の最も弱い位置を探し、そこから
    _CORR_GAP+_EDGE_SHIFT+3 画素離れた左右（上下）の基準線のうち弱い方との差を返す。
    """
    k = _CORR_GAP
    n = lines.nh if axis == 0 else lines.nv
    cs = lines.ch if axis == 0 else lines.cv
    sh = np.arange(-_EDGE_SHIFT, _EDGE_SHIFT + 1)
    ps = pos[:, None] + sh[None, :]
    ok = (ps >= 0) & (ps < n) & valid[:, None] & (b > a)[:, None]
    psc = np.clip(ps, 0, n - 1)
    aa = np.broadcast_to(a[:, None], ps.shape)
    bb = np.broadcast_to(b[:, None], ps.shape)
    den = np.maximum(bb - aa, 1)
    if axis == 0:
        v = (cs[bb, psc] - cs[aa, psc]) / den
    else:
        v = (cs[psc, bb] - cs[psc, aa]) / den
    v = np.where(ok, v, -np.inf)
    i = np.argmax(v, 1)
    rows = np.arange(len(v))
    best = v[rows, i]
    any_ok = ok.any(1)
    bp = np.where(any_ok, psc[rows, i], pos)
    off = k + _EDGE_SHIFT + 3
    rp = bp[:, None] + np.array([-off, off])[None, :]
    rok = (rp >= 0) & (rp < n)
    rpc = np.clip(rp, 0, n - 1)
    a2 = np.broadcast_to(a[:, None], rp.shape)
    b2 = np.broadcast_to(b[:, None], rp.shape)
    d2 = np.maximum(b2 - a2, 1)
    if axis == 0:
        rv = (cs[b2, rpc] - cs[a2, rpc]) / d2
    else:
        rv = (cs[rpc, b2] - cs[rpc, a2]) / d2
    ref = np.where(rok, rv, np.inf).min(1)
    s = np.where(any_ok, best, -9.0) - ref
    s = np.where(valid & rok.any(1), s, np.nan)
    return s, bp


def _score_rects(
    lines: _LineMeans, rh: int, rw: int, rects: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """rects: (N,4) の x1,y1,x2,y2（解析解像度）。点数と、辺を合わせ直した矩形を返す

    フレームの端に接する辺は数えない。数えた辺が3本未満の候補は -9 とする。
    """
    k = _CORR_GAP
    x1, y1, x2, y2 = (rects[:, i].astype(np.int64) for i in range(4))
    my = (y2 - y1) // 8
    mx = (x2 - x1) // 8
    h = k // 2
    sl, pl = _edge_scores(lines, 0, x1 - h, y1 + my, y2 - my, x1 >= k + 2)
    sr, pr = _edge_scores(lines, 0, x2 - h, y1 + my, y2 - my, rw - x2 >= k + 2)
    st, pt = _edge_scores(lines, 1, y1 - h, x1 + mx, x2 - mx, y1 >= k + 2)
    sb, pb = _edge_scores(lines, 1, y2 - h, x1 + mx, x2 - mx, rh - y2 >= k + 2)
    S = np.stack([sl, sr, st, sb], 1)

    # 辺の内側が動き外側が止まっているほど大きい（黒い背景などで相関が使えない辺の補い）
    o = k + 3
    hs, ws = lines.sc.shape[0] - 1, lines.sr.shape[1] - 1

    def vline(x, a, b):
        x = np.clip(x, 0, ws - 1)
        return (lines.sc[b, x] - lines.sc[a, x]) / np.maximum(b - a, 1)

    def hline(y, a, b):
        y = np.clip(y, 0, hs - 1)
        return (lines.sr[y, b] - lines.sr[y, a]) / np.maximum(b - a, 1)

    bl, bt, br, bb = pl + h, pt + h, pr + h, pb + h
    pairs = [
        (vline(bl + o, y1 + my, y2 - my), vline(bl - o - 1, y1 + my, y2 - my)),
        (vline(br - o - 1, y1 + my, y2 - my), vline(br + o, y1 + my, y2 - my)),
        (hline(bt + o, x1 + mx, x2 - mx), hline(bt - o - 1, x1 + mx, x2 - mx)),
        (hline(bb - o - 1, x1 + mx, x2 - mx), hline(bb + o, x1 + mx, x2 - mx)),
    ]
    V = np.stack([(i - e) / (i + e + _STD_EPS) for i, e in pairs], 1)
    S = np.where(np.isnan(S), S, np.fmax(S, V))

    cnt = (~np.isnan(S)).sum(1)
    with np.errstate(all="ignore"):
        scores = np.where(
            cnt >= 3,
            np.nanmin(np.where(cnt[:, None] > 0, S, 0), 1),
            -9.0,
        )
    fitted = np.stack([
        np.where(np.isnan(sl), x1, pl + h), np.where(np.isnan(st), y1, pt + h),
        np.where(np.isnan(sr), x2, pr + h), np.where(np.isnan(sb), y2, pb + h),
    ], 1)
    return scores, fitted


def sample_frames_from_video(
    video_path: str, n_frames: int = 30, skip_start: int = 30
) -> List[np.ndarray]:
    """
    映像ファイルから等間隔にフレームをサンプリング

    Args:
        video_path: 映像ファイルパス
        n_frames: サンプリングするフレーム数
        skip_start: 先頭からスキップするフレーム数

    Returns:
        サンプリングされたBGRフレームのリスト
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= skip_start + n_frames:
        skip_start = 0

    indices = np.linspace(skip_start, total - 1, n_frames, dtype=int)

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def _compute_diff_map(resized_frames: list) -> np.ndarray:
    """連続フレーム間差分の累積マップ"""
    gray_stack = np.array([
        cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for f in resized_frames
    ])
    diff_accum = np.zeros_like(gray_stack[0])
    for i in range(1, len(gray_stack)):
        diff_accum += np.abs(gray_stack[i] - gray_stack[i - 1])
    diff_accum /= max(1, len(gray_stack) - 1)
    return diff_accum


def _detect_by_projection(
    variance_map, scale, min_area, max_area
):
    """水平・垂直プロジェクションから矩形候補を検出"""
    rh, rw = variance_map.shape[:2]
    h_proj = np.mean(variance_map, axis=1)
    v_proj = np.mean(variance_map, axis=0)

    h_edges = _find_projection_edges(h_proj)
    v_edges = _find_projection_edges(v_proj)

    rects = []
    for (y1, y2) in h_edges:
        for (x1, x2) in v_edges:
            area_ratio = ((y2 - y1) * (x2 - x1)) / (rh * rw)
            if min_area <= area_ratio <= max_area:
                rects.append(PipRegion(
                    x=int(x1 / scale), y=int(y1 / scale),
                    w=int((x2 - x1) / scale),
                    h=int((y2 - y1) / scale),
                    area_ratio=area_ratio,
                    pip_score=0.0,
                    method="projection",
                ))
    return rects


def _find_projection_edges(proj, min_ratio=0.12):
    """プロジェクションの急変点を検出"""
    smoothed = np.convolve(proj, np.ones(7) / 7, mode='same')
    grad = np.abs(np.diff(smoothed))

    if np.max(grad) < 1e-6:
        return []

    threshold = np.percentile(grad, 90)
    peaks = []
    i = 0
    while i < len(grad):
        if grad[i] >= threshold:
            start = i
            while i < len(grad) and grad[i] >= threshold * 0.5:
                i += 1
            peak_pos = start + np.argmax(grad[start:i])
            peaks.append(peak_pos)
        i += 1

    min_size = int(len(proj) * min_ratio)
    max_size = int(len(proj) * 0.88)
    pairs = []
    for ip in range(len(peaks)):
        for jp in range(ip + 1, len(peaks)):
            dist = peaks[jp] - peaks[ip]
            if min_size <= dist <= max_size:
                pairs.append((peaks[ip], peaks[jp]))
    return pairs


def _detect_by_2d_analysis(
    variance_map, scale, min_area, max_area
):
    """2D分散マップの連結成分解析で矩形候補を検出"""
    rh, rw = variance_map.shape[:2]

    v_min = np.percentile(variance_map, 5)
    v_max = np.percentile(variance_map, 95)
    if v_max - v_min < 1e-6:
        return []

    normalized = np.clip(
        (variance_map - v_min) / (v_max - v_min), 0, 1
    )

    rects = []
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    for thresh_val in [0.2, 0.35, 0.5, 0.65, 0.8]:
        for use_low in [True, False]:
            if use_low:
                binary = (normalized < thresh_val).astype(np.uint8)
            else:
                binary = (normalized >= thresh_val).astype(np.uint8)
            binary *= 255

            cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(
                cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                area = cv2.contourArea(cnt)
                area_ratio = area / (rh * rw)
                if area_ratio < min_area or area_ratio > max_area:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                rect_area = w * h
                rectangularity = area / rect_area if rect_area > 0 else 0
                if rectangularity < 0.7:
                    continue

                rects.append(PipRegion(
                    x=int(x / scale), y=int(y / scale),
                    w=int(w / scale), h=int(h / scale),
                    area_ratio=area_ratio,
                    pip_score=0.0,
                    method="2d_analysis",
                ))

    return rects


def _filter_false_positives(
    rects: List[PipRegion],
    variance_map: np.ndarray,
    diff_map: np.ndarray,
    scale: float,
) -> List[PipRegion]:
    """
    偽陽性フィルタ

    矩形内外の分散パターン差・境界の不連続性・
    フレーム間差分の差異を総合してpip_scoreを算出。
    """
    if not rects:
        return []

    rh, rw = variance_map.shape[:2]
    total_var_mean = np.mean(variance_map)
    total_diff_mean = np.mean(diff_map)

    if total_var_mean < 1e-6:
        return []

    filtered = []

    for rect in rects:
        rx = max(0, min(int(rect.x * scale), rw - 1))
        ry = max(0, min(int(rect.y * scale), rh - 1))
        rx2 = min(int((rect.x + rect.w) * scale), rw)
        ry2 = min(int((rect.y + rect.h) * scale), rh)

        if rx2 - rx < 10 or ry2 - ry < 10:
            continue

        inner_mask = np.zeros((rh, rw), dtype=bool)
        inner_mask[ry:ry2, rx:rx2] = True
        outer_mask = ~inner_mask

        if np.sum(outer_mask) < 100:
            continue

        # 分散パターンの差
        inner_var = np.mean(variance_map[inner_mask])
        outer_var = np.mean(variance_map[outer_mask])
        var_diff_ratio = abs(inner_var - outer_var) / total_var_mean

        # 境界の不連続性
        rw_px = rx2 - rx
        rh_px = ry2 - ry
        border_w = max(3, min(rw_px, rh_px) // 10)
        boundary_scores = []

        _add_boundary_score(
            diff_map, boundary_scores,
            ry - border_w, ry, ry, ry + border_w,
            rx, rx2, rh, rw,
        )
        _add_boundary_score(
            diff_map, boundary_scores,
            ry2 - border_w, ry2, ry2, ry2 + border_w,
            rx, rx2, rh, rw,
        )
        _add_boundary_score_v(
            diff_map, boundary_scores,
            rx - border_w, rx, rx, rx + border_w,
            ry, ry2, rh, rw,
        )
        _add_boundary_score_v(
            diff_map, boundary_scores,
            rx2 - border_w, rx2, rx2, rx2 + border_w,
            ry, ry2, rh, rw,
        )

        avg_boundary = (
            np.mean(boundary_scores) if boundary_scores else 0
        )

        # フレーム間差分パターンの差
        inner_diff = np.mean(diff_map[inner_mask])
        outer_diff = np.mean(diff_map[outer_mask])
        diff_ratio = abs(inner_diff - outer_diff) / (
            total_diff_mean + 1e-6
        )

        pip_score = (
            var_diff_ratio * 0.4
            + min(avg_boundary / (total_diff_mean + 1e-6), 2.0) * 0.3
            + diff_ratio * 0.3
        )

        rect.pip_score = pip_score
        filtered.append(rect)

    filtered.sort(key=lambda r: r.pip_score, reverse=True)
    return filtered[:5]


def _add_boundary_score(
    diff_map, scores,
    outer_y1, outer_y2, inner_y1, inner_y2,
    x1, x2, max_h, max_w,
):
    """水平境界のスコアを追加"""
    if outer_y1 < 0 or inner_y2 >= max_h:
        return
    outer_strip = diff_map[outer_y1:outer_y2, x1:x2]
    inner_strip = diff_map[inner_y1:inner_y2, x1:x2]
    if outer_strip.size > 0 and inner_strip.size > 0:
        scores.append(abs(
            np.mean(outer_strip) - np.mean(inner_strip)
        ))


def _add_boundary_score_v(
    diff_map, scores,
    outer_x1, outer_x2, inner_x1, inner_x2,
    y1, y2, max_h, max_w,
):
    """垂直境界のスコアを追加"""
    if outer_x1 < 0 or inner_x2 >= max_w:
        return
    outer_strip = diff_map[y1:y2, outer_x1:outer_x2]
    inner_strip = diff_map[y1:y2, inner_x1:inner_x2]
    if outer_strip.size > 0 and inner_strip.size > 0:
        scores.append(abs(
            np.mean(outer_strip) - np.mean(inner_strip)
        ))


def _deduplicate(rects: List[PipRegion]) -> List[PipRegion]:
    """IoU > 0.5 の重複矩形を除去"""
    if len(rects) <= 1:
        return rects

    kept = []
    for rect in rects:
        is_dup = False
        for k in kept:
            iou = _compute_iou(rect, k)
            if iou > 0.5:
                is_dup = True
                break
        if not is_dup:
            kept.append(rect)
    return kept


def _merge_contained_regions(
    rects: List[PipRegion],
    scale: float,
    map_w: int,
    map_h: int,
) -> List[PipRegion]:
    """包含・高IoUの候補群を外接矩形へ統合する"""
    if len(rects) <= 1:
        return rects

    frame_area = (map_w * map_h) / (scale * scale) if scale > 0 else 0.0
    groups: List[List[PipRegion]] = []
    for rect in sorted(rects, key=lambda r: r.w * r.h, reverse=True):
        placed = False
        for group in groups:
            merged = _union_region(group, frame_area)
            if (
                _containment_ratio(merged, rect) >= 0.6
                or _compute_iou(merged, rect) >= 0.5
            ):
                group.append(rect)
                placed = True
                break
        if not placed:
            groups.append([rect])

    return [_union_region(group, frame_area) for group in groups]


def _union_region(
    rects: List[PipRegion], frame_area: float,
) -> PipRegion:
    """候補群の外接矩形を作る"""
    if len(rects) == 1:
        return rects[0]

    x1 = min(r.x for r in rects)
    y1 = min(r.y for r in rects)
    x2 = max(r.x + r.w for r in rects)
    y2 = max(r.y + r.h for r in rects)
    w = x2 - x1
    h = y2 - y1
    area_ratio = (w * h) / frame_area if frame_area > 0 else 0.0
    return PipRegion(
        x=x1, y=y1, w=w, h=h,
        area_ratio=area_ratio, pip_score=0.0, method="merged",
    )


def _containment_ratio(a: PipRegion, b: PipRegion) -> float:
    """小さい方の矩形が交差領域にどれだけ含まれるかを返す"""
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    smaller = min(a.w * a.h, b.w * b.h)
    return inter / smaller if smaller > 0 else 0.0


def _compute_iou(a: PipRegion, b: PipRegion) -> float:
    """2矩形のIoUを計算"""
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    area_a = a.w * a.h
    area_b = b.w * b.h
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
