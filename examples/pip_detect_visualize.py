#!/usr/bin/env python3
"""
PiP矩形検出の可視化・戦略比較ツール

PiP（ピクチャインピクチャ）を含む動画に対して、mimizam が検出した矩形を
確認するための診断ツール。検索とは独立に、`detect_pip_regions` が返す矩形
（座標・サイズ・pip_score）を動画フレーム上に重ねて画像として保存し、
一覧をテキストでも出力する。

さらに、検出された矩形が真のPiP全体ではなく一部しか覆えないケースの改善候補
として、候補矩形の後処理戦略 A/B/C を **examples 内でのみ** 試作し、各戦略が
選ぶ代表矩形（USED）を並べて目視比較できるようにしている（`src/` は未変更）。

戦略:
    baseline  現行の detect_pip_regions と同じ（後処理なし）
    A         候補クラスタリング＋union外接枠（近接/重複候補を1枠に統合）
    B         包含統合（一方が他方をほぼ包含/高IoUなら大きい union に併合）
    C         被覆重み付けスコア（pip_score を面積比で持ち上げ、全体枠を優遇）

各戦略の代表矩形(USED)を緑、その他候補を黄で描いた注釈画像を戦略ごとに保存し、
代表矩形の座標・スコアを比較表として出力する。「どれが真のPiPに近いか」は
生成画像を目視で見比べて判断する（正解座標の入力は不要）。

使い方:
    uv run ./examples/pip_detect_visualize.py <動画パス>
    uv run ./examples/pip_detect_visualize.py <動画パス> --strategy all
    uv run ./examples/pip_detect_visualize.py <動画パス> --strategy A B --cluster-margin 0.03

出力:
    - 戦略ごとの注釈画像 *_pip_<strategy>.png
    - 各戦略の代表矩形(USED)の比較表（標準出力）
"""

import argparse
import logging
import os
import sys
from typing import Dict, List, Tuple

import cv2
import numpy as np

from mimizam import PipRegion, sample_frames_from_video

# 検出パイプラインの内部関数を再利用する（src は変更しない。ここでは候補生成と
# スコアリングを本体と完全に同じロジックで行うため内部関数を読み取り利用する）。
from mimizam.src import pip_detector as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STRATEGIES = ["baseline", "A", "B", "C"]

COLOR_USED = (0, 200, 0)      # 緑: その戦略が選ぶ代表矩形(USED)
COLOR_OTHER = (0, 200, 255)   # 黄: 検出されたその他の矩形


# ---------------------------------------------------------------------------
# 検出パイプラインの前段（本体 detect_pip_regions と同じ前処理を再現）
# ---------------------------------------------------------------------------
def _build_maps(
    frames: List[np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, float]:
    """時間分散マップ・フレーム間差分マップと解析スケールを作る"""
    h, w = frames[0].shape[:2]
    scale = min(1.0, pd._ANALYSIS_LONG_SIDE / max(h, w))
    if scale < 1.0:
        resized = [cv2.resize(f, None, fx=scale, fy=scale) for f in frames]
    else:
        resized = frames
        scale = 1.0

    gray_stack = np.array([
        cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for f in resized
    ])
    variance_map = np.var(gray_stack, axis=0)
    diff_map = pd._compute_diff_map(resized)
    return variance_map, diff_map, scale


def _raw_candidates(
    variance_map: np.ndarray, scale: float,
    min_area: float, max_area: float,
) -> List[PipRegion]:
    """スコア付与前の候補矩形（重複除去済み・元解像度座標）"""
    cands: List[PipRegion] = []
    cands.extend(
        pd._detect_by_projection(variance_map, scale, min_area, max_area)
    )
    cands.extend(
        pd._detect_by_2d_analysis(variance_map, scale, min_area, max_area)
    )
    return pd._deduplicate(cands)


def _score(
    rects: List[PipRegion],
    variance_map: np.ndarray, diff_map: np.ndarray, scale: float,
    threshold: float,
) -> List[PipRegion]:
    """本体と同じ偽陽性フィルタでスコア付けし、閾値通過分を降順で返す"""
    scored = pd._filter_false_positives(rects, variance_map, diff_map, scale)
    result = [r for r in scored if r.pip_score >= threshold]
    result.sort(key=lambda r: r.pip_score, reverse=True)
    return result


# ---------------------------------------------------------------------------
# 幾何ユーティリティ
# ---------------------------------------------------------------------------
def _union_box(rects: List[PipRegion], frame_area: int) -> PipRegion:
    x1 = min(r.x for r in rects)
    y1 = min(r.y for r in rects)
    x2 = max(r.x + r.w for r in rects)
    y2 = max(r.y + r.h for r in rects)
    w, h = x2 - x1, y2 - y1
    return PipRegion(
        x=x1, y=y1, w=w, h=h,
        area_ratio=(w * h) / frame_area if frame_area else 0.0,
        pip_score=0.0, method="union",
    )


def _connected(a: PipRegion, b: PipRegion, margin: int) -> bool:
    """2矩形が重複、または margin 以内に近接していれば連結とみなす"""
    ax1, ay1, ax2, ay2 = a.x - margin, a.y - margin, a.x + a.w + margin, a.y + a.h + margin
    bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def _contain_ratio(a: PipRegion, b: PipRegion) -> float:
    """小さい方の面積のうち交差が占める割合（包含度）"""
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    smaller = min(a.w * a.h, b.w * b.h)
    return inter / smaller if smaller > 0 else 0.0


# ---------------------------------------------------------------------------
# 戦略ごとの代表矩形（USED=先頭）を返す
# ---------------------------------------------------------------------------
def _strategy_baseline(ctx: dict) -> List[PipRegion]:
    return _score(
        ctx["candidates"], ctx["variance_map"], ctx["diff_map"],
        ctx["scale"], ctx["threshold"],
    )[:5]


def _strategy_a_cluster(ctx: dict) -> List[PipRegion]:
    """近接/重複候補をクラスタ化し、各クラスタのunion枠を代表候補にする"""
    cands = ctx["candidates"]
    if not cands:
        return []
    margin = int(ctx["cluster_margin"] * min(ctx["fh"], ctx["fw"]))

    # union-find で連結成分をまとめる
    parent = list(range(len(cands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if _connected(cands[i], cands[j], margin):
                union(i, j)

    clusters: Dict[int, List[PipRegion]] = {}
    for idx, r in enumerate(cands):
        clusters.setdefault(find(idx), []).append(r)

    union_boxes = [
        _union_box(group, ctx["frame_area"]) for group in clusters.values()
    ]
    return _score(
        union_boxes, ctx["variance_map"], ctx["diff_map"],
        ctx["scale"], ctx["threshold"],
    )[:5]


def _strategy_b_contain(ctx: dict) -> List[PipRegion]:
    """一方が他方をほぼ包含/高IoUなら大きいunionに併合してからスコア"""
    cands = sorted(
        ctx["candidates"], key=lambda r: r.w * r.h, reverse=True
    )
    merged: List[List[PipRegion]] = []
    for r in cands:
        placed = False
        for group in merged:
            rep = _union_box(group, ctx["frame_area"])
            if _contain_ratio(rep, r) >= 0.6 or pd._compute_iou(rep, r) >= 0.5:
                group.append(r)
                placed = True
                break
        if not placed:
            merged.append([r])

    boxes = [_union_box(g, ctx["frame_area"]) for g in merged]
    return _score(
        boxes, ctx["variance_map"], ctx["diff_map"],
        ctx["scale"], ctx["threshold"],
    )[:5]


def _strategy_c_coverage(ctx: dict) -> List[PipRegion]:
    """baselineスコアに面積比の重みを掛けて全体枠を優遇する再ランク"""
    base = _score(
        ctx["candidates"], ctx["variance_map"], ctx["diff_map"],
        ctx["scale"], ctx["threshold"],
    )
    w = ctx["cov_weight"]
    reranked = sorted(
        base,
        key=lambda r: r.pip_score * (1.0 + w * r.area_ratio),
        reverse=True,
    )
    return reranked[:5]


STRATEGY_FUNCS = {
    "baseline": _strategy_baseline,
    "A": _strategy_a_cluster,
    "B": _strategy_b_contain,
    "C": _strategy_c_coverage,
}


# ---------------------------------------------------------------------------
# 描画・出力
# ---------------------------------------------------------------------------
def _annotate(
    frame: np.ndarray, regions: List[PipRegion], title: str,
) -> np.ndarray:
    """先頭(USED)を緑、他を黄で描画。USEDを最後に重ねて前面に残す"""
    canvas = frame.copy()
    order = sorted(enumerate(regions), key=lambda rr: rr[0] == 0)
    for idx, region in order:
        used = idx == 0
        color = COLOR_USED if used else COLOR_OTHER
        thickness = 3 if used else 2
        x1, y1 = region.x, region.y
        x2, y2 = region.x + region.w, region.y + region.h
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)

        label = f"#{idx + 1} score={region.pip_score:.2f} {region.w}x{region.h}"
        if used:
            label += " [USED]"
        (tw, th), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1
        )
        ly = max(0, y1 - th - 6)
        cv2.rectangle(
            canvas, (x1, ly), (x1 + tw + 6, ly + th + 6), color, -1
        )
        cv2.putText(
            canvas, label, (x1 + 3, ly + th + 1),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA,
        )

    cv2.putText(
        canvas, title, (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA,
    )
    return canvas


def _print_comparison(results: Dict[str, List[PipRegion]]) -> None:
    print()
    print("  戦略ごとの代表矩形(USED)の比較")
    print("  " + "-" * 66)
    print("  戦略      pip_score  位置(x,y)      サイズ(WxH)   面積比  候補数")
    for name in STRATEGIES:
        if name not in results:
            continue
        regs = results[name]
        if not regs:
            print(f"  {name:<9} {'-':>8}   (検出なし)")
            continue
        u = regs[0]
        print(
            f"  {name:<9} {u.pip_score:>8.2f}  "
            f"({u.x:>4},{u.y:>4})   {u.w:>4}x{u.h:<4}  "
            f"{u.area_ratio:>6.3f}  {len(regs):>4}"
        )
    print()
    print("  ※ どれが真のPiPに近いかは *_pip_<strategy>.png を目視で見比べて判断")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PiP矩形検出の可視化・戦略比較ツール",
    )
    parser.add_argument("video", help="PiPを含む動画ファイルのパス")
    parser.add_argument(
        "-o", "--output-prefix",
        help="出力画像の接頭辞（既定: 入力と同じ場所の入力名）",
    )
    parser.add_argument(
        "-n", "--frames", type=int, default=30,
        help="検出に用いるサンプリングフレーム数（既定: 30）",
    )
    parser.add_argument(
        "-t", "--threshold", type=float, default=pd.DEFAULT_PIP_SCORE_THRESHOLD,
        help=f"pip_score の検出閾値（既定: {pd.DEFAULT_PIP_SCORE_THRESHOLD}）",
    )
    parser.add_argument(
        "--strategy", default="all",
        help=(
            "比較する戦略をカンマ区切りで指定（既定: all＝baseline/A/B/C 全て）"
            "。例: --strategy A,B / --strategy baseline"
        ),
    )
    parser.add_argument(
        "--cluster-margin", type=float, default=0.02,
        help="戦略Aの近接判定マージン（フレーム短辺比、既定: 0.02）",
    )
    parser.add_argument(
        "--cov-weight", type=float, default=2.0,
        help="戦略Cの面積比の重み（既定: 2.0）",
    )
    parser.add_argument(
        "--min-area-ratio", type=float, default=0.03,
        help="候補の最小面積比（既定: 0.03）",
    )
    parser.add_argument(
        "--max-area-ratio", type=float, default=0.75,
        help="候補の最大面積比（既定: 0.75）",
    )
    args = parser.parse_args()

    if not os.path.exists(args.video):
        logger.error("動画ファイルが見つかりません: %s", args.video)
        return 1

    requested = [s.strip() for s in args.strategy.split(",") if s.strip()]
    if "all" in requested:
        strategies = STRATEGIES
    else:
        invalid = [s for s in requested if s not in STRATEGIES]
        if invalid:
            logger.error(
                "不明な戦略: %s（選択肢: %s, all）",
                ",".join(invalid), ",".join(STRATEGIES),
            )
            return 1
        strategies = requested

    logger.info("フレームをサンプリング中: %s", args.video)
    frames = sample_frames_from_video(args.video, n_frames=args.frames)
    if len(frames) < 5:
        logger.error(
            "フレームが不足しています（5枚以上必要）: %s", args.video
        )
        return 1

    fh, fw = frames[0].shape[:2]
    variance_map, diff_map, scale = _build_maps(frames)
    candidates = _raw_candidates(
        variance_map, scale, args.min_area_ratio, args.max_area_ratio
    )
    logger.info("候補矩形: %d件（スコア付与前・重複除去済み）", len(candidates))

    ctx = {
        "candidates": candidates,
        "variance_map": variance_map,
        "diff_map": diff_map,
        "scale": scale,
        "threshold": args.threshold,
        "fh": fh, "fw": fw, "frame_area": fh * fw,
        "cluster_margin": args.cluster_margin,
        "cov_weight": args.cov_weight,
    }

    base = frames[len(frames) // 2]
    if args.output_prefix:
        prefix = args.output_prefix
    else:
        prefix, _ = os.path.splitext(args.video)

    results: Dict[str, List[PipRegion]] = {}
    for name in strategies:
        regs = STRATEGY_FUNCS[name](ctx)
        results[name] = regs
        out_path = f"{prefix}_pip_{name}.png"
        annotated = _annotate(base, regs, f"strategy={name}")
        if cv2.imwrite(out_path, annotated):
            logger.info("[%s] 注釈画像を保存: %s", name, out_path)
        else:
            logger.error("[%s] 画像の保存に失敗: %s", name, out_path)

    print(f"\n  対象: {os.path.basename(args.video)}")
    _print_comparison(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
