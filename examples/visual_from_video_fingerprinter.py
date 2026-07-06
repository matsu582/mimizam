#!/usr/bin/env python3
"""
映像指紋（視覚特徴量）登録ツール

指定されたフォルダ内の動画ファイルから AKAZE + VLAD + PCA ベースの
映像指紋を生成し、データベースに登録するスクリプト。
既存の audio_from_video_fingerprinter.py（音声指紋）とは異なり、
映像の視覚的特徴量を用いた指紋を生成する。
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from mimizam import (
    Mimizam,
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


def load_model(
    mimizam: Mimizam,
    model_path: str,
) -> None:
    """VLAD/PCAモデルを読み込む"""
    logger = logging.getLogger(__name__)
    if not os.path.isfile(model_path):
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {model_path}\n"
            "scripts/train_pretrained_model.py でモデルを生成してください"
        )
    logger.info(f"モデルを読み込み: {model_path}")
    mimizam.load_video_model(model_path)


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

        except Exception as exc:
            logger.error(f"  エラー ({video_path}): {exc}")
            continue

    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="映像指紋（視覚特徴量）登録ツール - AKAZE + VLAD + PCA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # 事前学習済みモデルを使って動画を登録
  python visual_from_video_fingerprinter.py /path/to/videos --model models/akaze_vlad_pca_pretrained.pkl

  # 単一ファイルを登録
  python visual_from_video_fingerprinter.py /path/to/video.mp4 --model models/akaze_vlad_pca_pretrained.pkl

  # モデルの事前学習は scripts/train_pretrained_model.py で実行:
  #   python scripts/train_pretrained_model.py --coco-dir /path/to/coco/val2017

  # MySQLバックエンドを使用
  python visual_from_video_fingerprinter.py /path/to/videos --model model.pkl --db-type mysql \\
      --db-host localhost --db-name mimizam --db-user user --db-password pass
""",
    )

    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="動画ファイルまたはフォルダのパス（--rebuild時は不要）",
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
        required=True,
        help="VLAD/PCAモデルファイルのパス（.pkl、必須）。"
             "scripts/train_pretrained_model.py で事前学習したモデルを指定。"
             "検索時にvisual_from_video_search.pyで同じモデルを指定する必要あり",
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
        "--rebuild",
        action="store_true",
        help="DB内の全映像指紋を保存済み記述子から再生成。"
             "モデル更新後に元映像なしで指紋を再計算する",
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
        # Mimizamシステムを初期化
        logger.info("Mimizamシステムを初期化中...")
        mimizam = create_mimizam_instance(args)

        # VLAD/PCAモデルの読み込み
        load_model(mimizam, args.model)

        # --rebuild: DB内の指紋を記述子から再生成
        if args.rebuild:
            logger.info("指紋再生成モード: DB内の全映像を再生成...")
            rebuild_stats = mimizam.rebuild_video_fingerprints(
                args.video_db
            )
            logger.info(
                f"再生成完了: "
                f"{rebuild_stats['success']}/"
                f"{rebuild_stats['total']}件成功, "
                f"{rebuild_stats['skip']}件スキップ"
            )
            return 0

        # 登録モード: targetが必要
        if args.target is None:
            logger.error("登録先の動画ファイルまたはフォルダを指定してください")
            return 1

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

        # 映像指紋の登録
        processed = process_video_files(
            video_files, mimizam, args.video_db
        )

        # 統計情報を表示
        stats = mimizam.get_video_database_stats(args.video_db)
        logger.info(
            f"映像指紋DB統計 - "
            f"映像数: {stats.get('videos', 0)}, "
            f"フレーム指紋: {stats.get('frame_fingerprints', 0)}"
        )

        logger.info(f"処理完了: {processed}/{len(video_files)}本を登録")
        return 0

    except KeyboardInterrupt:
        logger.info("ユーザーにより中断されました")
        return 1
    except Exception:
        logger.exception("予期しないエラーが発生しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
