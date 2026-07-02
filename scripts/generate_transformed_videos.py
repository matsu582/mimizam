#!/usr/bin/env python3
"""
映像指紋検証用 改変動画生成ツール

入力映像に対して回転・拡大縮小・アスペクト比変更・PiP（Picture-in-Picture）
などの幾何変換を適用し、映像指紋の耐性検証用テストデータを生成する。

使用例:
  # 単一映像に全変換を適用
  python scripts/generate_transformed_videos.py input.mp4 -o output_dir/

  # 複数映像を指定
  python scripts/generate_transformed_videos.py video1.mp4 video2.mp4 -o output_dir/

  # 変換タイプを指定（回転のみ）
  python scripts/generate_transformed_videos.py input.mp4 -t rotate

  # PiP変換のみ
  python scripts/generate_transformed_videos.py input.mp4 -t pip

  # PiPの画像背景に使う映像を指定
  python scripts/generate_transformed_videos.py input.mp4 -t pip --bg-video bg.mp4
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# 変換パターン定義
ROTATE_TRANSFORMS = [
    {"type": "rotate", "params": {"angle": 15}, "suffix": "rotate_15"},
    {"type": "rotate", "params": {"angle": 30}, "suffix": "rotate_30"},
    {"type": "rotate", "params": {"angle": 45}, "suffix": "rotate_45"},
    {"type": "rotate", "params": {"angle": 90}, "suffix": "rotate_90"},
    {"type": "rotate", "params": {"angle": 180}, "suffix": "rotate_180"},
]

SCALE_TRANSFORMS = [
    {"type": "scale", "params": {"scale": 1.5}, "suffix": "scale_1.5x"},
    {"type": "scale", "params": {"scale": 2.0}, "suffix": "scale_2.0x"},
    {"type": "scale", "params": {"scale": 0.75}, "suffix": "scale_0.75x"},
    {"type": "scale", "params": {"scale": 0.5}, "suffix": "scale_0.5x"},
]

ASPECT_TRANSFORMS = [
    {"type": "aspect", "params": {}, "suffix": "aspect_4_3"},
]

PIP_TRANSFORMS = [
    {"type": "pip_corner", "params": {"scale": 0.25},
     "suffix": "pip_corner_25pct_noise"},
    {"type": "pip_center", "params": {"scale": 0.5, "bg": "black"},
     "suffix": "pip_center_50pct_black"},
    {"type": "pip_center", "params": {"scale": 0.33, "bg": "black"},
     "suffix": "pip_center_33pct_black"},
    {"type": "pip_center", "params": {"scale": 0.5, "bg": "image"},
     "suffix": "pip_center_50pct_image"},
    {"type": "pip_center", "params": {"scale": 0.33, "bg": "image"},
     "suffix": "pip_center_33pct_image"},
]

ALL_TRANSFORMS = (
    ROTATE_TRANSFORMS
    + SCALE_TRANSFORMS
    + ASPECT_TRANSFORMS
    + PIP_TRANSFORMS
)

TRANSFORM_GROUPS = {
    "all": ALL_TRANSFORMS,
    "rotate": ROTATE_TRANSFORMS,
    "scale": SCALE_TRANSFORMS,
    "aspect": ASPECT_TRANSFORMS,
    "pip": PIP_TRANSFORMS,
}


def transform_video(
    input_path: str,
    output_path: str,
    transform_type: str,
    params: Dict,
    bg_video_path: Optional[str] = None,
) -> int:
    """映像に幾何変換を適用して新しいファイルを生成する。

    Args:
        input_path: 入力映像のパス
        output_path: 出力映像のパス
        transform_type: 変換タイプ (rotate/scale/aspect/pip_corner/pip_center)
        params: 変換パラメータ
        bg_video_path: PiP画像背景用の映像パス（省略時は入力映像リストの別映像を使用）

    Returns:
        処理したフレーム数
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"  エラー: 映像を開けません: {input_path}", file=sys.stderr)
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 出力サイズの計算
    pip_w, pip_h = 0, 0
    if transform_type == "rotate":
        angle = params["angle"]
        if angle in (90, 270):
            out_w, out_h = h, w
        elif angle == 180:
            out_w, out_h = w, h
        else:
            rad = np.radians(angle)
            cos_a, sin_a = abs(np.cos(rad)), abs(np.sin(rad))
            out_w = int(w * cos_a + h * sin_a)
            out_h = int(w * sin_a + h * cos_a)

    elif transform_type == "scale":
        scale = params["scale"]
        out_w = int(w * scale)
        out_h = int(h * scale)

    elif transform_type == "aspect":
        out_w = int(w * 3 / 4)
        out_h = h

    elif transform_type in ("pip_corner", "pip_center"):
        pip_scale = params.get("scale", 0.5)
        out_w, out_h = w, h
        pip_w = int(w * pip_scale)
        pip_h = int(h * pip_scale)

    else:
        print(f"  エラー: 未知の変換タイプ: {transform_type}", file=sys.stderr)
        cap.release()
        return 0

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

    np.random.seed(42)

    # PiPノイズ背景: 静的ノイズ（圧縮効率のため全フレーム共通）
    static_noise_bg = None
    if transform_type == "pip_corner":
        static_noise_bg = np.random.randint(
            50, 200, (out_h, out_w, 3), dtype=np.uint8
        )

    # PiP画像背景の準備
    bg_image = None
    if transform_type == "pip_center" and params.get("bg") == "image":
        if bg_video_path and os.path.isfile(bg_video_path):
            bg_cap = cv2.VideoCapture(bg_video_path)
            ret, bg_frame = bg_cap.read()
            if ret:
                bg_image = cv2.resize(bg_frame, (out_w, out_h))
            bg_cap.release()
        if bg_image is None:
            # 背景映像が指定されていない場合はグレー背景にフォールバック
            bg_image = np.full(
                (out_h, out_w, 3), 128, dtype=np.uint8
            )

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if transform_type == "rotate":
            angle = params["angle"]
            if angle == 90:
                transformed = cv2.rotate(
                    frame, cv2.ROTATE_90_CLOCKWISE
                )
            elif angle == 180:
                transformed = cv2.rotate(frame, cv2.ROTATE_180)
            elif angle == 270:
                transformed = cv2.rotate(
                    frame, cv2.ROTATE_90_COUNTERCLOCKWISE
                )
            else:
                center = (w // 2, h // 2)
                mat = cv2.getRotationMatrix2D(center, angle, 1.0)
                mat[0, 2] += (out_w - w) / 2
                mat[1, 2] += (out_h - h) / 2
                transformed = cv2.warpAffine(
                    frame, mat, (out_w, out_h),
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(0, 0, 0),
                )

        elif transform_type == "scale":
            transformed = cv2.resize(
                frame, (out_w, out_h),
                interpolation=cv2.INTER_LINEAR,
            )

        elif transform_type == "aspect":
            transformed = cv2.resize(
                frame, (out_w, out_h),
                interpolation=cv2.INTER_LINEAR,
            )

        elif transform_type == "pip_corner":
            bg = static_noise_bg.copy()
            small = cv2.resize(frame, (pip_w, pip_h))
            x_off = out_w - pip_w - 20
            y_off = out_h - pip_h - 20
            bg[y_off:y_off + pip_h, x_off:x_off + pip_w] = small
            transformed = bg

        elif transform_type == "pip_center":
            if params.get("bg") == "image" and bg_image is not None:
                bg = bg_image.copy()
            else:
                bg = np.zeros((out_h, out_w, 3), dtype=np.uint8)
            small = cv2.resize(frame, (pip_w, pip_h))
            x_off = (out_w - pip_w) // 2
            y_off = (out_h - pip_h) // 2
            bg[y_off:y_off + pip_h, x_off:x_off + pip_w] = small
            transformed = bg

        out.write(transformed)
        frame_count += 1

    cap.release()
    out.release()
    return frame_count


def process_video(
    video_path: str,
    output_dir: str,
    transforms: List[Dict],
    bg_video_path: Optional[str] = None,
    skip_existing: bool = True,
) -> None:
    """1本の映像に対して指定された変換を全て適用する。

    Args:
        video_path: 入力映像のパス
        output_dir: 出力ディレクトリ
        transforms: 適用する変換リスト
        bg_video_path: PiP画像背景用の映像パス
        skip_existing: 既存ファイルをスキップするかどうか
    """
    video_name = Path(video_path).stem
    video_out_dir = os.path.join(output_dir, video_name)
    os.makedirs(video_out_dir, exist_ok=True)

    print(f"\n=== {video_name} ===")

    for t in transforms:
        suffix = t["suffix"]
        out_path = os.path.join(
            video_out_dir, f"{video_name}_{suffix}.mp4"
        )

        if skip_existing and os.path.exists(out_path):
            print(f"  スキップ（既存）: {suffix}")
            continue

        print(f"  生成中: {suffix} ...", end=" ", flush=True)
        count = transform_video(
            video_path, out_path, t["type"], t["params"],
            bg_video_path=bg_video_path,
        )
        if count > 0:
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"完了 ({count}フレーム, {size_mb:.1f}MB)")
        else:
            print("失敗")


def print_summary(output_dir: str) -> None:
    """生成結果のサマリを表示する。"""
    total_size = 0
    total_files = 0

    print(f"\n=== 生成結果 ===")
    for root, _dirs, files in sorted(os.walk(output_dir)):
        for f in sorted(files):
            if not f.endswith(".mp4"):
                continue
            fpath = os.path.join(root, f)
            sz = os.path.getsize(fpath) / 1024 / 1024
            total_size += sz
            total_files += 1
            rel = os.path.relpath(fpath, output_dir)
            print(f"  {rel}: {sz:.1f}MB")

    print(f"\n合計: {total_files}ファイル, {total_size:.1f}MB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="映像指紋検証用 改変動画生成ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
変換タイプ:
  all     全変換（デフォルト）
  rotate  回転のみ (15°, 30°, 45°, 90°, 180°)
  scale   拡大縮小のみ (0.5x, 0.75x, 1.5x, 2.0x)
  aspect  アスペクト比変更のみ (16:9→4:3)
  pip     PiP（Picture-in-Picture）のみ

使用例:
  python scripts/generate_transformed_videos.py video.mp4 -o out/
  python scripts/generate_transformed_videos.py *.mp4 -t rotate -o out/
  python scripts/generate_transformed_videos.py video.mp4 -t pip --bg-video bg.mp4
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="入力映像ファイルのパス（複数指定可）",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="transformed_videos",
        help="出力ディレクトリ（デフォルト: transformed_videos）",
    )
    parser.add_argument(
        "-t", "--type",
        choices=list(TRANSFORM_GROUPS.keys()),
        default="all",
        help="適用する変換タイプ（デフォルト: all）",
    )
    parser.add_argument(
        "--bg-video",
        default=None,
        help="PiP画像背景用の映像ファイルパス",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="既存ファイルを上書き",
    )

    args = parser.parse_args()

    # 入力ファイルの存在確認
    for inp in args.inputs:
        if not os.path.isfile(inp):
            print(f"エラー: ファイルが見つかりません: {inp}", file=sys.stderr)
            sys.exit(1)

    transforms = TRANSFORM_GROUPS[args.type]
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"変換タイプ: {args.type} ({len(transforms)}パターン)")
    print(f"入力映像: {len(args.inputs)}本")
    print(f"出力先: {args.output_dir}")

    # PiP画像背景の決定
    bg_video = args.bg_video
    if bg_video is None and len(args.inputs) > 1:
        # 複数映像が指定されている場合、別の映像を背景に使用
        bg_video = args.inputs[0]

    for i, video_path in enumerate(args.inputs):
        # 画像背景用に自分以外の映像を選択
        current_bg = bg_video
        if current_bg == video_path and len(args.inputs) > 1:
            current_bg = args.inputs[(i + 1) % len(args.inputs)]

        process_video(
            video_path,
            args.output_dir,
            transforms,
            bg_video_path=current_bg,
            skip_existing=not args.overwrite,
        )

    print_summary(args.output_dir)


if __name__ == "__main__":
    main()
