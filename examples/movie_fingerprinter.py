#!/usr/bin/env python3
"""
動画統合指紋登録ツール

動画ファイルから音声指紋と映像指紋の両方を生成し、
同一のUUIDでデータベースに登録する。
audio_from_video_fingerprinter.py（音声）とvisual_from_video_fingerprinter.py（映像）を
統合したスクリプト。
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
            logging.FileHandler("movie_fingerprinter.log"),
        ],
    )


def create_mimizam_instance(args) -> Mimizam:
    """コマンドライン引数に基づいてMimizamインスタンスを作成する"""
    if args.db_type == "sqlite":
        return create_mimizam_sqlite(args.database)

    elif args.db_type == "mysql":
        if not all([args.db_host, args.db_name,
                    args.db_user, args.db_password]):
            raise ValueError(
                "MySQLには --db-host, --db-name, "
                "--db-user, --db-password が必要です"
            )
        return create_mimizam_mysql(
            host=args.db_host,
            port=args.db_port or 3306,
            database=args.db_name,
            username=args.db_user,
            password=args.db_password,
        )

    elif args.db_type == "postgresql":
        if not all([args.db_host, args.db_name,
                    args.db_user, args.db_password]):
            raise ValueError(
                "PostgreSQLには --db-host, --db-name, "
                "--db-user, --db-password が必要です"
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
            index_name=args.db_name or "movie_fingerprints",
        )

    raise ValueError(f"未対応のデータベースタイプ: {args.db_type}")


def find_video_files(folder_path: str) -> List[str]:
    """フォルダ内の動画ファイルを検索する"""
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(
            f"フォルダが見つかりません: {folder_path}"
        )

    video_files = []
    for file_path in folder.rglob("*"):
        if (file_path.is_file()
                and file_path.suffix.lower() in VIDEO_EXTENSIONS):
            video_files.append(str(file_path))

    return sorted(video_files)


def process_video_files(
    video_files: List[str],
    mimizam: Mimizam,
    video_db_path: Optional[str] = None,
    skip_audio: bool = False,
    skip_visual: bool = False,
) -> int:
    """
    動画ファイルに対して音声指紋と映像指紋を同一UUIDで登録する

    Args:
        video_files: 動画ファイルパスの一覧
        mimizam: Mimizamインスタンス
        video_db_path: 映像指紋DBのパス
        skip_audio: 音声指紋の生成をスキップ
        skip_visual: 映像指紋の生成をスキップ

    Returns:
        正常に処理されたファイル数
    """
    logger = logging.getLogger(__name__)
    processed_count = 0

    for i, video_path in enumerate(video_files, 1):
        title = Path(video_path).stem
        logger.info(f"[{i}/{len(video_files)}] 処理中: {title}")

        # 音声＋映像を同一IDで登録（統合登録はAPI側で実施）
        result = mimizam.add_movie(
            file_path=video_path,
            title=title,
            video_db_path=video_db_path,
            skip_audio=skip_audio,
            skip_visual=skip_visual,
        )

        audio_ok = result["audio_registered"]
        visual_ok = result["visual_registered"]
        shared_id = result["id"]

        if (not skip_audio) and not audio_ok:
            logger.error("  音声指紋: 登録失敗")
        if (not skip_visual) and not visual_ok:
            logger.error("  映像指紋: 登録失敗")

        if audio_ok or visual_ok:
            processed_count += 1
            modes = []
            if audio_ok:
                modes.append("音声")
            if visual_ok:
                modes.append("映像")
            logger.info(
                f"  登録完了: {title} "
                f"({'+'.join(modes)}, ID: {shared_id})"
            )
        else:
            logger.error(f"  登録失敗: {title}")

    return processed_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="動画統合指紋登録ツール（音声+映像）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # 音声+映像の両方の指紋を登録
  python movie_fingerprinter.py /path/to/videos --model model.pki

  # 映像指紋のみ登録（音声スキップ）
  python movie_fingerprinter.py /path/to/videos --model model.pki --skip-audio

  # 音声指紋のみ登録（映像スキップ）
  python movie_fingerprinter.py /path/to/videos --model model.pki --skip-visual

  # フレーム選定の処理内訳を計測しながら登録
  python movie_fingerprinter.py /path/to/videos --model model.pki --profile

  # シーン検出の評価fpsを4に下げて登録（retrieve回数を削減し高速化）
  python movie_fingerprinter.py /path/to/videos --model model.pki \\
      --scene-eval-fps 4 --profile
""",
    )

    parser.add_argument(
        "target",
        help="動画ファイルまたはフォルダのパス",
    )
    parser.add_argument(
        "--database", "-d",
        default="movie_fingerprints.db",
        help="DBのパス（音声・映像指紋を同一ファイルに格納、デフォルト: movie_fingerprints.db）",
    )
    parser.add_argument(
        "--model", "-m",
        required=True,
        help="映像指紋用VLAD/PCAモデルファイルのパス（必須）",
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
        "--skip-audio",
        action="store_true",
        help="音声指紋の生成をスキップ（映像のみ登録）",
    )
    parser.add_argument(
        "--skip-visual",
        action="store_true",
        help="映像指紋の生成をスキップ（音声のみ登録）",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="検出した動画ファイルの一覧のみ表示",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログを出力",
    )
    parser.add_argument(
        "--scene-eval-fps",
        type=float,
        default=None,
        help="シーン検出の評価fps（既定4.0）。下げるとretrieve回数が減り"
             "高速化するが、極端に速いカットを取りこぼす可能性がある",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="フレーム選定の処理内訳（grab/retrieve/resize/シーン検出/"
             "ヒストグラム等の所要時間）をログ出力する",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        if args.skip_audio and args.skip_visual:
            logger.error(
                "--skip-audio と --skip-visual を同時に指定できません"
            )
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

        # Mimizamシステムを初期化
        logger.info("Mimizamシステムを初期化中...")
        mimizam = create_mimizam_instance(args)

        # 映像指紋の実行時設定（環境変数ではなくConfig経由で渡す）
        mimizam.configure_video(
            scene_eval_fps=args.scene_eval_fps or None,
            profile_frames=args.profile or None,
        )

        # 映像モデルの読み込み（映像指紋が有効な場合）
        if not args.skip_visual:
            if not os.path.isfile(args.model):
                logger.error(
                    f"モデルファイルが見つかりません: {args.model}"
                )
                return 1
            logger.info(f"映像モデル読み込み: {args.model}")
            mimizam.load_video_model(args.model)

        # 登録処理（音声・映像とも同一DBに格納）
        processed = process_video_files(
            video_files, mimizam,
            video_db_path=args.database,
            skip_audio=args.skip_audio,
            skip_visual=args.skip_visual,
        )

        # 統計情報を表示
        audio_stats = mimizam.get_database_stats()
        logger.info(
            f"音声指紋DB - "
            f"楽曲数: {audio_stats.get('songs', 0)}, "
            f"指紋数: {audio_stats.get('fingerprints', 0)}"
        )

        video_stats = mimizam.get_video_database_stats(args.database)
        logger.info(
            f"映像指紋DB - "
            f"映像数: {video_stats.get('videos', 0)}, "
            f"フレーム指紋: {video_stats.get('frame_fingerprints', 0)}"
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
