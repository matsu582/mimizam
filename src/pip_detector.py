"""
PiP（Picture-in-Picture）矩形検出

映像フレームの時間分散マップと2D連結成分解析を用いて、
フレーム内に重畳された別映像の矩形領域を検出する。

検出アルゴリズム:
  1. 複数フレームの画素値の時間分散を計算
  2. 分散マップのプロジェクション（水平・垂直）から急変点を検出
  3. 分散マップの二値化 + 連結成分解析で矩形候補を検出
  4. 矩形内外の分散パターン差と境界の不連続性でPiPを判定
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# PiP検出の内部処理用解像度（長辺）
_ANALYSIS_LONG_SIDE = 480

# PiP判定の閾値
DEFAULT_PIP_SCORE_THRESHOLD = 0.5


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

    # 時間分散マップを計算
    gray_stack = np.array([
        cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for f in resized
    ])
    variance_map = np.var(gray_stack, axis=0)

    # フレーム間差分の累積マップ（偽陽性フィルタ用）
    diff_map = _compute_diff_map(resized)

    # 矩形候補を検出（2手法の統合）
    rh, rw = variance_map.shape[:2]
    candidates = []

    # 手法1: プロジェクション方式
    proj_rects = _detect_by_projection(
        variance_map, scale, min_area_ratio, max_area_ratio
    )
    candidates.extend(proj_rects)

    # 手法2: 2D連結成分解析
    area_rects = _detect_by_2d_analysis(
        variance_map, scale, min_area_ratio, max_area_ratio
    )
    candidates.extend(area_rects)

    # 重複除去
    candidates = _deduplicate(candidates)

    # 偽陽性フィルタ
    filtered = _filter_false_positives(
        candidates, variance_map, diff_map, scale
    )

    # pip_score閾値でフィルタ
    result = [
        r for r in filtered if r.pip_score >= pip_score_threshold
    ]
    result.sort(key=lambda r: r.pip_score, reverse=True)

    if result:
        logger.info(
            f"PiP rectangle detection: {len(result)} found "
            f"(out of {len(candidates)} candidates)"
        )

    return result[:5]


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
