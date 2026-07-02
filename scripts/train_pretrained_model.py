#!/usr/bin/env python3
"""
AKAZE + VLAD + PCA 事前学習済みモデルの構築スクリプト

大規模画像/動画データセットからAKAZE記述子を抽出し、
K-Means codebook + PCA変換器を学習して .pkl ファイルとして保存する。
出力モデルは VLADEncoder.load_model() で読み込み可能。

フロー:
  1. 画像/動画フレームからAKAZE記述子を抽出
  2. 全記述子で K-Means codebook を学習
  3. 画像/フレームごとに VLAD ベクトルを計算
  4. VLAD ベクトル群に PCA を学習
  5. codebook + PCA を .pkl として保存

依存パッケージ:
  pip install opencv-python numpy scikit-learn

使用例:
  # COCO val2017 で学習
  python scripts/train_pretrained_model.py \\
      --coco-dir /path/to/coco/val2017 \\
      -o models/akaze_vlad_pca_pretrained.pkl

  # COCO + UCF-101 で学習（推奨）
  python scripts/train_pretrained_model.py \\
      --coco-dir /path/to/coco/train2017 \\
      --ucf-dir /path/to/UCF-101 \\
      -o models/akaze_vlad_pca_pretrained.pkl

  # PCA次元数を変更
  python scripts/train_pretrained_model.py \\
      --coco-dir /path/to/coco/val2017 \\
      --pca-dim 256 \\
      -o models/model_pca256.pkl
"""

import argparse
import glob
import logging
import os
import pickle
import sys
import time

import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import PCA

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CODEBOOK_SIZE = 64
DEFAULT_PCA_DIM = 512
DEFAULT_MAX_DESC_PER_IMAGE = 500
DEFAULT_MAX_KMEANS_SAMPLES = 2_000_000
RANDOM_SEED = 42


def parse_args():
    parser = argparse.ArgumentParser(
        description="AKAZE + VLAD + PCA 事前学習済みモデルの構築",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
推奨データセット:
  COCO (https://cocodataset.org/):
    wget http://images.cocodataset.org/zips/val2017.zip     # 778MB, 5000枚
    wget http://images.cocodataset.org/zips/train2017.zip   # 18GB, 118K枚

  UCF-101 (https://www.crcv.ucf.edu/data/UCF101.php):
    wget https://www.crcv.ucf.edu/data/UCF101/UCF101.rar    # 6.5GB, 13K動画

PCA次元数の目安:
  128次元 (512B/指紋): 小規模・同ジャンル映像向け
  256次元 (1KB/指紋):  中規模向け
  512次元 (2KB/指紋):  大規模・異ジャンル混在向け（推奨）
""",
    )

    parser.add_argument(
        "--coco-dir",
        help="COCO画像ディレクトリ（train2017/val2017 等）",
    )
    parser.add_argument(
        "--ucf-dir",
        help="UCF-101動画ディレクトリ",
    )
    parser.add_argument(
        "--image-dir",
        action="append",
        default=[],
        help="追加の画像ディレクトリ（複数指定可）",
    )
    parser.add_argument(
        "--video-dir",
        action="append",
        default=[],
        help="追加の動画ディレクトリ（複数指定可）",
    )
    parser.add_argument(
        "-o", "--output",
        default="models/akaze_vlad_pca_pretrained.pkl",
        help="出力モデルファイルパス（デフォルト: models/akaze_vlad_pca_pretrained.pkl）",
    )
    parser.add_argument(
        "--codebook-size", "-K",
        type=int,
        default=DEFAULT_CODEBOOK_SIZE,
        help=f"K-Meansクラスタ数（デフォルト: {DEFAULT_CODEBOOK_SIZE}）",
    )
    parser.add_argument(
        "--pca-dim",
        type=int,
        default=DEFAULT_PCA_DIM,
        help=f"PCA出力次元数（デフォルト: {DEFAULT_PCA_DIM}）",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=50000,
        help="処理する画像の最大数（デフォルト: 50000）",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=2000,
        help="処理する動画の最大数（デフォルト: 2000）",
    )
    parser.add_argument(
        "--max-desc-per-image",
        type=int,
        default=DEFAULT_MAX_DESC_PER_IMAGE,
        help=f"画像あたりの最大記述子数（デフォルト: {DEFAULT_MAX_DESC_PER_IMAGE}）",
    )
    parser.add_argument(
        "--video-interval",
        type=float,
        default=2.0,
        help="動画のフレームサンプリング間隔（秒、デフォルト: 2.0）",
    )

    args = parser.parse_args()

    if (
        not args.coco_dir
        and not args.ucf_dir
        and not args.image_dir
        and not args.video_dir
    ):
        parser.error(
            "--coco-dir, --ucf-dir, --image-dir, --video-dir の"
            "いずれかを指定してください"
        )

    return args


def extract_akaze_from_image(
    image_path: str, akaze, max_desc: int
) -> np.ndarray:
    """画像からAKAZE記述子を抽出"""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.array([])

    h, w = img.shape[:2]
    if max(h, w) > 1280:
        scale = 1280.0 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale)

    kps, desc = akaze.detectAndCompute(img, None)
    if desc is None or len(desc) == 0:
        return np.array([])

    if len(desc) > max_desc:
        rng = np.random.default_rng(RANDOM_SEED)
        indices = rng.choice(len(desc), size=max_desc, replace=False)
        desc = desc[indices]

    return desc.astype(np.float32)


def extract_akaze_from_video(
    video_path: str, akaze, max_desc: int, sample_interval: float
) -> list:
    """動画からフレームごとのAKAZE記述子リストを返す"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    frame_interval = max(1, int(fps * sample_interval))

    frame_descs = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            if max(h, w) > 1280:
                scale = 1280.0 / max(h, w)
                gray = cv2.resize(gray, None, fx=scale, fy=scale)

            kps, desc = akaze.detectAndCompute(gray, None)
            if desc is not None and len(desc) > 0:
                if len(desc) > max_desc:
                    rng = np.random.default_rng(RANDOM_SEED + frame_idx)
                    indices = rng.choice(len(desc), size=max_desc, replace=False)
                    desc = desc[indices]
                frame_descs.append(desc.astype(np.float32))

        frame_idx += 1

    cap.release()
    return frame_descs


def collect_image_descriptors(
    image_dir: str, akaze, max_images: int, max_desc: int
) -> list:
    """画像ディレクトリからフレーム単位の記述子リストを収集"""
    image_files = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
        image_files.extend(glob.glob(os.path.join(image_dir, ext)))
        image_files.extend(
            glob.glob(os.path.join(image_dir, "**", ext), recursive=True)
        )
    image_files = sorted(set(image_files))

    if not image_files:
        logger.warning(f"画像が見つかりません: {image_dir}")
        return []

    if len(image_files) > max_images:
        rng = np.random.default_rng(RANDOM_SEED)
        indices = rng.choice(len(image_files), size=max_images, replace=False)
        image_files = [image_files[i] for i in sorted(indices)]

    logger.info(f"画像: {len(image_files)}枚を処理中 ({image_dir})")
    per_image = []
    processed = 0
    start_time = time.time()

    for i, img_path in enumerate(image_files):
        desc = extract_akaze_from_image(img_path, akaze, max_desc)
        if len(desc) > 0:
            per_image.append(desc)
            processed += 1

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (len(image_files) - i - 1) / rate
            total_desc = sum(len(d) for d in per_image)
            logger.info(
                f"  [{i+1}/{len(image_files)}] "
                f"記述子: {total_desc:,}, 残り: {remaining:.0f}秒"
            )

    elapsed = time.time() - start_time
    total_desc = sum(len(d) for d in per_image)
    logger.info(
        f"画像処理完了: {processed}枚, "
        f"記述子: {total_desc:,}, "
        f"{elapsed:.1f}秒"
    )
    return per_image


def collect_video_descriptors(
    video_dir: str,
    akaze,
    max_videos: int,
    max_desc: int,
    sample_interval: float,
) -> list:
    """動画ディレクトリからフレーム単位の記述子リストを収集"""
    video_files = []
    for ext in ("*.avi", "*.mp4", "*.mkv", "*.mov", "*.wmv"):
        video_files.extend(
            glob.glob(os.path.join(video_dir, "**", ext), recursive=True)
        )
    video_files = sorted(set(video_files))

    if not video_files:
        logger.warning(f"動画が見つかりません: {video_dir}")
        return []

    if len(video_files) > max_videos:
        rng = np.random.default_rng(RANDOM_SEED)
        indices = rng.choice(len(video_files), size=max_videos, replace=False)
        video_files = [video_files[i] for i in sorted(indices)]

    logger.info(f"動画: {len(video_files)}本を処理中 ({video_dir})")
    per_frame = []
    processed = 0
    start_time = time.time()

    for i, video_path in enumerate(video_files):
        frame_descs = extract_akaze_from_video(
            video_path, akaze, max_desc, sample_interval
        )
        per_frame.extend(frame_descs)
        if frame_descs:
            processed += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (len(video_files) - i - 1) / rate
            total_desc = sum(len(d) for d in per_frame)
            logger.info(
                f"  [{i+1}/{len(video_files)}] "
                f"記述子: {total_desc:,}, 残り: {remaining:.0f}秒"
            )

    elapsed = time.time() - start_time
    total_desc = sum(len(d) for d in per_frame)
    logger.info(
        f"動画処理完了: {processed}本, "
        f"記述子: {total_desc:,}, "
        f"{elapsed:.1f}秒"
    )
    return per_frame


def compute_vlad_vector(
    descriptors: np.ndarray, codebook: MiniBatchKMeans
) -> np.ndarray:
    """記述子群からVLADベクトルを計算（intra-normalization適用）"""
    k = codebook.n_clusters
    d = descriptors.shape[1]
    centers = codebook.cluster_centers_

    desc_f = descriptors.astype(np.float32)
    labels = codebook.predict(desc_f)

    vlad = np.zeros((k, d), dtype=np.float32)
    for i, lbl in enumerate(labels):
        vlad[lbl] += desc_f[i] - centers[lbl]

    for j in range(k):
        norm_val = np.linalg.norm(vlad[j])
        if norm_val > 1e-6:
            vlad[j] /= norm_val

    return vlad.flatten()


def main():
    args = parse_args()

    if hasattr(cv2, 'AKAZE_create'):
        akaze = cv2.AKAZE_create()
    elif hasattr(cv2, 'xfeatures2d_AKAZE'):
        akaze = cv2.xfeatures2d_AKAZE.create()
    else:
        logger.error(
            "AKAZEが利用できません。"
            "opencv-contrib-python をインストールしてください"
        )
        sys.exit(1)
    per_unit_descriptors = []

    # COCO画像の処理
    if args.coco_dir:
        if not os.path.isdir(args.coco_dir):
            logger.error(f"ディレクトリが見つかりません: {args.coco_dir}")
            sys.exit(1)
        descs = collect_image_descriptors(
            args.coco_dir, akaze, args.max_images, args.max_desc_per_image
        )
        per_unit_descriptors.extend(descs)

    # UCF-101動画の処理
    if args.ucf_dir:
        if not os.path.isdir(args.ucf_dir):
            logger.error(f"ディレクトリが見つかりません: {args.ucf_dir}")
            sys.exit(1)
        descs = collect_video_descriptors(
            args.ucf_dir, akaze, args.max_videos,
            args.max_desc_per_image, args.video_interval,
        )
        per_unit_descriptors.extend(descs)

    # 追加画像ディレクトリ
    for img_dir in args.image_dir:
        if os.path.isdir(img_dir):
            descs = collect_image_descriptors(
                img_dir, akaze, args.max_images, args.max_desc_per_image
            )
            per_unit_descriptors.extend(descs)

    # 追加動画ディレクトリ
    for vid_dir in args.video_dir:
        if os.path.isdir(vid_dir):
            descs = collect_video_descriptors(
                vid_dir, akaze, args.max_videos,
                args.max_desc_per_image, args.video_interval,
            )
            per_unit_descriptors.extend(descs)

    if not per_unit_descriptors:
        logger.error("記述子が抽出できませんでした")
        sys.exit(1)

    total_desc = sum(len(d) for d in per_unit_descriptors)
    desc_dim = per_unit_descriptors[0].shape[1]
    logger.info(
        f"合計: {len(per_unit_descriptors)}サンプル, "
        f"{total_desc:,}記述子 ({desc_dim}次元)"
    )

    # K-Means codebook学習
    logger.info("全記述子を結合中...")
    combined = np.vstack(per_unit_descriptors).astype(np.float32)

    if len(combined) > DEFAULT_MAX_KMEANS_SAMPLES:
        rng = np.random.default_rng(RANDOM_SEED)
        indices = rng.choice(
            len(combined), size=DEFAULT_MAX_KMEANS_SAMPLES, replace=False
        )
        combined = combined[indices]
        logger.info(f"K-Means用サンプリング: {len(combined):,}個")

    k = args.codebook_size
    logger.info(f"K-Means学習中 (K={k}, {len(combined):,}記述子)...")
    start = time.time()
    codebook = MiniBatchKMeans(
        n_clusters=k,
        batch_size=min(10000, len(combined)),
        random_state=RANDOM_SEED,
        n_init=3,
        max_iter=300,
    )
    codebook.fit(combined)
    del combined
    logger.info(f"K-Means完了: {time.time() - start:.1f}秒")

    # 画像/フレームごとのVLADを計算してPCA学習
    vlad_dim = k * desc_dim
    logger.info(
        f"VLAD計算中... ({len(per_unit_descriptors)}サンプル, "
        f"VLAD次元: {vlad_dim})"
    )
    start = time.time()
    vlad_samples = []
    for i, desc in enumerate(per_unit_descriptors):
        if len(desc) >= 5:
            vlad_samples.append(compute_vlad_vector(desc, codebook))
        if (i + 1) % 2000 == 0:
            logger.info(f"  VLAD: [{i+1}/{len(per_unit_descriptors)}]")

    del per_unit_descriptors
    logger.info(
        f"VLAD完了: {len(vlad_samples)}個, {time.time() - start:.1f}秒"
    )

    vlad_matrix = np.array(vlad_samples)
    pca_dim = min(args.pca_dim, vlad_matrix.shape[0], vlad_dim)

    logger.info(f"PCA学習中: {vlad_dim}→{pca_dim}次元...")
    start = time.time()
    pca = PCA(n_components=pca_dim, random_state=RANDOM_SEED)
    pca.fit(vlad_matrix)
    del vlad_matrix, vlad_samples

    variance_ratio = float(np.sum(pca.explained_variance_ratio_))
    logger.info(
        f"PCA完了: {time.time() - start:.1f}秒, "
        f"分散保持率: {variance_ratio:.1%}"
    )

    # VLADEncoder.load_model() 互換形式で保存
    from src.video_fingerprinter import VideoFingerprintConfig
    config = VideoFingerprintConfig(
        codebook_size=k,
        pca_dimensions=pca_dim,
    )
    model_data = {
        "codebook": codebook,
        "pca": pca,
        "descriptor_dim": desc_dim,
        "config": config,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "wb") as f:
        pickle.dump(model_data, f, protocol=pickle.HIGHEST_PROTOCOL)

    file_size_kb = os.path.getsize(args.output) / 1024
    logger.info(f"モデル保存: {args.output} ({file_size_kb:.1f}KB)")

    print("\n=== 事前学習済みモデル統計 ===")
    print(f"  codebookサイズ (K):  {k}")
    print(f"  記述子次元:          {desc_dim}")
    print(f"  VLAD次元:            {vlad_dim}")
    print(f"  PCA出力次元:         {pca_dim}")
    print(f"  分散保持率:          {variance_ratio:.1%}")
    print(f"  指紋サイズ:          {pca_dim * 4}バイト")
    print(f"  学習記述子数:        {total_desc:,}")
    print(f"  ファイルサイズ:      {file_size_kb:.1f}KB")
    print(f"  出力:                {args.output}")


if __name__ == "__main__":
    # scripts/ から実行する場合のパス調整
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    main()
