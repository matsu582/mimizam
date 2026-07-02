#!/usr/bin/env python3
"""
映像指紋（視覚特徴量）登録ツール

指定されたフォルダ内の動画ファイルから AKAZE + VLAD + PCA ベースの
映像指紋を生成し、データベースに登録するスクリプト。
既存の video_fingerprinter.py（音声指紋）とは異なり、
映像の視覚的特徴量を用いた指紋を生成する。
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from mimizam import (
    DatabaseConfig,
    Mimizam,
    Video,
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch,
)

# サポートされている動画ファイル拡張子
VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm",
    ".m4v", ".3gp", ".ogv", ".ts", ".mts", ".m2ts",
}


def setup_logging(verbose: bool = False) -> None:
    """ログ設定のセットアップ"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("visual_fingerprinter.log"),
        ],
    )


def find_video_files(folder_path: str) -> List[str]:
    """
    指定されたフォルダ内の動画ファイルを検索する

    Args:
        folder_path: 検索するフォルダのパス

    Returns:
        動画ファイルパスのリスト
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"フォルダが見つかりません: {folder_path}")

    video_files = []
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in VIDEO_EXTENSIONS:
            video_files.append(str(file_path))

    return sorted(video_files)


def create_mimizam_instance(args) -> Mimizam:
    """コマンドライン引数に基づいてMimizamインスタンスを作成する"""
    if args.db_type == "sqlite":
        return create_mimizam_sqlite(args.database)

    elif args.db_type == "mysql":
        if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            raise ValueError(
                "MySQLには --db-host, --db-name, --db-user, --db-password が必要です"
            )
        return create_mimizam_mysql(
            host=args.db_host,
            port=args.db_port or 3306,
            database=args.db_name,
            username=args.db_user,
            password=args.db_password,
        )

    elif args.db_type == "postgresql":
        if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            raise ValueError(
                "PostgreSQLには --db-host, --db-name, --db-user, --db-password が必要です"
            )
        return create_mimizam_postgresql(
            host=args.db_host,
            port=args.db_port or 5432,
            database=args.db_name,
            username=args.db_user,
            password=args.db_password,
        )

    elif args.db_type == "elasticsearch":
        if not args.db_host:
            raise ValueError("Elasticsearchには --db-host が必要です")
        return create_mimizam_elasticsearch(
            host=args.db_host,
            port=args.db_port or 9200,
            index_name=args.db_name or "visual_fingerprints",
        )

    raise ValueError(f"未対応のデータベースタイプ: {args.db_type}")


def train_model_if_needed(
    mimizam: Mimizam,
    video_files: List[str],
    model_path: Optional[str] = None,
) -> None:
    """必要に応じてVLAD/PCAモデルを学習する"""
    logger = logging.getLogger(__name__)
    vfp = mimizam._get_video_fingerprinter()

    # 保存済みモデルがあれば読み込み
    if model_path and os.path.isfile(model_path):
        logger.info(f"保存済みモデルを読み込み: {model_path}")
        vfp.load_model(model_path)
        return

    if vfp.is_trained:
        return

    # 学習用の映像を選択（最大10本または全て）
    train_files = video_files[:10]
    logger.info(
        f"VLAD/PCAモデルを学習中 ({len(train_files)}本の映像を使用)..."
    )
    stats = vfp.train_from_videos(train_files)
    logger.info(
        f"モデル学習完了: "
        f"記述子数={stats.get('total_descriptors', '?')}, "
        f"分散保持率={stats.get('pca_variance_ratio', 0):.1%}"
    )

    # モデルを保存
    if model_path:
        vfp.save_model(model_path)
        logger.info(f"モデルを保存: {model_path}")


def process_video_files(
    video_files: List[str],
    mimizam: Mimizam,
    video_db_path: Optional[str] = None,
) -> int:
    """
    動画ファイルを処理し、映像指紋をデータベースに追加する

    Args:
        video_files: 動画ファイルパスの一覧
        mimizam: Mimizamインスタンス
        video_db_path: 映像指紋DBのパス

    Returns:
        正常に処理されたファイル数
    """
    logger = logging.getLogger(__name__)
    processed_count = 0

    for i, video_path in enumerate(video_files, 1):
        try:
            title = Path(video_path).stem
            logger.info(
                f"[{i}/{len(video_files)}] 処理中: {title}"
            )

            video_id = mimizam.add_video(
                file_path=video_path,
                title=title,
                video_db_path=video_db_path,
            )

            if video_id:
                logger.info(f"  登録成功: {title} (ID: {video_id})")
                processed_count += 1
            else:
                logger.error(f"  登録失敗: {title}")

        except Exception as e:
            logger.error(f"  エラー ({video_path}): {e}")
            continue

    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="映像指紋（視覚特徴量）登録ツール - AKAZE + VLAD + PCA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # フォルダ内の動画を登録
  python visual_fingerprinter.py /path/to/videos

  # 単一ファイルを登録
  python visual_fingerprinter.py /path/to/video.mp4

  # モデルを保存して再利用
  python visual_fingerprinter.py /path/to/videos --model model.pkl

  # MySQLバックエンドを使用
  python visual_fingerprinter.py /path/to/videos --db-type mysql \\
      --db-host localhost --db-name mimizam --db-user user --db-password pass
""",
    )

    parser.add_argument(
        "target",
        help="動画ファイルまたはフォルダのパス",
    )
    parser.add_argument(
        "--database", "-d",
        default="visual_fingerprints.db",
        help="音声指紋DBのパス（デフォルト: visual_fingerprints.db）",
    )
    parser.add_argument(
        "--video-db",
        default=None,
        help="映像指紋DBのパス（省略時は音声DBと同じバックエンドを使用）",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="VLAD/PCAモデルの保存先/読み込み元パス（.pkl）。"
             "K-Means辞書(VLAD量子化用)とPCA変換器を保持。"
             "検索時にvisual_search.pyで同じモデルを指定する必要あり",
    )
    parser.add_argument(
        "--db-type",
        choices=["sqlite", "mysql", "postgresql", "elasticsearch"],
        default="sqlite",
        help="データベースバックエンドタイプ（デフォルト: sqlite）",
    )
    parser.add_argument("--db-host", help="データベースホスト")
    parser.add_argument("--db-port", type=int, help="データベースポート")
    parser.add_argument("--db-name", help="データベース名")
    parser.add_argument("--db-user", help="データベースユーザー名")
    parser.add_argument("--db-password", help="データベースパスワード")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="検出した動画ファイルの一覧のみ表示（登録しない）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログを出力",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # 入力パスの検証
        target = Path(args.target)
        if not target.exists():
            logger.error(f"パスが見つかりません: {args.target}")
            return 1

        # 動画ファイルの収集
        if target.is_file():
            if target.suffix.lower() not in VIDEO_EXTENSIONS:
                logger.error(f"未対応のファイル形式: {target.suffix}")
                return 1
            video_files = [str(target)]
        else:
            video_files = find_video_files(args.target)

        logger.info(f"動画ファイル: {len(video_files)}本")

        if not video_files:
            logger.warning("動画ファイルが見つかりません")
            return 0

        if args.list_only:
            print("\n動画ファイル一覧:")
            for vf in video_files:
                print(f"  {vf}")
            return 0

        # Mimizamシステムを初期化
        logger.info("Mimizamシステムを初期化中...")
        mimizam = create_mimizam_instance(args)

        # VLAD/PCAモデルの学習/読み込み
        train_model_if_needed(mimizam, video_files, args.model)

        # 映像指紋の登録
        processed = process_video_files(
            video_files, mimizam, args.video_db
        )

        # 統計情報を表示
        stats = mimizam.get_video_database_stats(args.video_db)
        logger.info(
            f"映像指紋DB統計 - "
            f"映像数: {stats.get('videos', 0)}, "
            f"映像指紋: {stats.get('video_fingerprints', 0)}, "
            f"フレーム指紋: {stats.get('frame_fingerprints', 0)}"
        )

        logger.info(f"処理完了: {processed}/{len(video_files)}本を登録")
        return 0

    except KeyboardInterrupt:
        logger.info("ユーザーにより中断されました")
        return 1
    except Exception as e:
        logger.exception("予期しないエラーが発生しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
