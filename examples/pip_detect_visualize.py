#!/usr/bin/env python3
"""
PiP矩形検出の可視化ツール

PiP（ピクチャインピクチャ）を含む動画に対して、mimizam が検出した矩形を
確認するための診断ツール。検索とは独立に、`detect_pip_regions` が返す矩形
（座標・サイズ・pip_score）を動画フレーム上に重ねて画像として保存し、
一覧をテキストでも出力する。

「PiPが正しく認識されているか」を目視確認する用途を想定している。

検出ロジックは検索経路（VideoFingerprinter.fingerprint_pip_regions）と同一で、
`sample_frames_from_video` でサンプリングしたフレームを `detect_pip_regions`
に渡す。表示では pip_score 降順で全矩形を描画し、実際に検索で使われる上位
（--max-regions 件）を強調表示する。

使い方:
    uv run ./examples/pip_detect_visualize.py <動画パス>
    uv run ./examples/pip_detect_visualize.py <動画パス> -o out.png --max-regions 1

出力:
    - 矩形を重ねた注釈画像（既定は入力と同じ場所に *_pip.png）
    - 検出矩形の一覧（標準出力）
"""

import argparse
import logging
import os
import sys
from typing import List

import cv2
import numpy as np

from mimizam import (
    PipRegion,
    detect_pip_regions,
    sample_frames_from_video,
)
from mimizam.src.video_fingerprinter import VideoFingerprintConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 検索で使われる矩形（上位）と、それ以外（参考表示）の色（BGR）
COLOR_USED = (0, 200, 0)      # 緑: 実際に検索で使用される矩形
COLOR_OTHER = (0, 200, 255)   # 黄: 検出されたが検索対象外の矩形


def _pick_base_frame(frames: List[np.ndarray]) -> np.ndarray:
    """矩形を描画する背景フレーム（中央付近のフレーム）を選ぶ"""
    return frames[len(frames) // 2]


def _annotate(
    frame: np.ndarray,
    regions: List[PipRegion],
    used_count: int,
) -> np.ndarray:
    """フレームに矩形と注釈を描画した画像を返す"""
    canvas = frame.copy()
    # 検索対象外(黄)を先に描画し、使用矩形(緑)を最後に重ねて前面に出す
    order = sorted(
        enumerate(regions, start=1),
        key=lambda rr: rr[0] <= used_count,
    )
    for rank, region in order:
        used = rank <= used_count
        color = COLOR_USED if used else COLOR_OTHER
        thickness = 3 if used else 2

        x1, y1 = region.x, region.y
        x2, y2 = region.x + region.w, region.y + region.h
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)

        label = (
            f"#{rank} score={region.pip_score:.2f} "
            f"{region.w}x{region.h}"
        )
        if used:
            label += " [USED]"

        # ラベル背景を敷いて可読性を確保
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
    return canvas


def _print_regions(regions: List[PipRegion], used_count: int) -> None:
    if not regions:
        print("  PiP矩形は検出されませんでした")
        return
    print(f"  検出矩形: {len(regions)}件（pip_score降順）")
    print(
        "  " + "-" * 68 + "\n"
        "  順位  pip_score  位置(x,y)      サイズ(WxH)   面積比   使用"
    )
    for rank, r in enumerate(regions, start=1):
        used = "○" if rank <= used_count else ""
        print(
            f"  {rank:>3}   {r.pip_score:>8.2f}  "
            f"({r.x:>4},{r.y:>4})   {r.w:>4}x{r.h:<4}  "
            f"{r.area_ratio:>6.3f}   {used}"
        )


def main() -> int:
    default_max = VideoFingerprintConfig().pip_max_regions

    parser = argparse.ArgumentParser(
        description="PiP矩形検出の可視化ツール",
    )
    parser.add_argument("video", help="PiPを含む動画ファイルのパス")
    parser.add_argument(
        "-o", "--output",
        help="注釈画像の出力パス（既定: 入力と同じ場所に *_pip.png）",
    )
    parser.add_argument(
        "-n", "--frames", type=int, default=30,
        help="検出に用いるサンプリングフレーム数（既定: 30）",
    )
    parser.add_argument(
        "-t", "--threshold", type=float, default=0.5,
        help="pip_score の検出閾値（既定: 0.5）",
    )
    parser.add_argument(
        "-k", "--max-regions", type=int, default=default_max,
        help=(
            "検索で使用する上位矩形数として強調表示する件数"
            f"（既定: {default_max}＝設定値）"
        ),
    )
    args = parser.parse_args()

    if not os.path.exists(args.video):
        logger.error("動画ファイルが見つかりません: %s", args.video)
        return 1

    logger.info("フレームをサンプリング中: %s", args.video)
    frames = sample_frames_from_video(args.video, n_frames=args.frames)
    if not frames:
        logger.error(
            "フレームを読み込めませんでした（対応形式か破損か確認）: %s",
            args.video,
        )
        return 1

    logger.info("PiP矩形を検出中（%dフレーム）...", len(frames))
    regions = detect_pip_regions(
        frames, pip_score_threshold=args.threshold
    )

    print()
    print(f"  対象: {os.path.basename(args.video)}")
    _print_regions(regions, args.max_regions)
    print()

    base = _pick_base_frame(frames)
    annotated = _annotate(base, regions, args.max_regions)

    if args.output:
        out_path = args.output
    else:
        root, _ = os.path.splitext(args.video)
        out_path = f"{root}_pip.png"

    if cv2.imwrite(out_path, annotated):
        logger.info("注釈画像を保存しました: %s", out_path)
    else:
        logger.error("画像の保存に失敗しました: %s", out_path)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
