#!/usr/bin/env python3
"""
映像指紋（視覚特徴量）検索ツール

動画ファイルから AKAZE + VLAD + PCA ベースの映像指紋を生成し、
データベースに登録済みの映像と照合して類似映像を検索するスクリプト。
既存の audio_from_video_search.py（音声指紋検索）とは異なり、
映像の視覚的特徴量を用いた検索を行う。

検索の流れ:
  1. フレーム単位指紋の近傍検索（ANN）と得票集計で候補絞り込み
  2. フレーム単位の時間整合照合とPiP矩形照合で確定
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            logging.FileHandler("visual_search.log"),
        ],
    )


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


def _format_similarity(similarity: float) -> str:
    """類似度に応じた表示テキストを返す"""
    if similarity >= 0.8:
        return f"HIGH   ({similarity:.3f})"
    elif similarity >= 0.5:
        return f"MEDIUM ({similarity:.3f})"
    else:
        return f"LOW    ({similarity:.3f})"


def _format_duration(seconds: float) -> str:
    """秒数を mm:ss 形式にフォーマットする"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def _render_bar(
    total_duration: float,
    regions: list,
    bar_width: int = 60,
    key: str = "query",
) -> str:
    """一致区間をバーで可視化"""
    if total_duration <= 0:
        return "|" + "-" * bar_width + "|"

    bar = ["-"] * bar_width
    start_key = f"{key}_start"
    end_key = f"{key}_end"

    for region in regions:
        s = region.get(start_key, 0)
        e = region.get(end_key, 0)
        i_start = int(s / total_duration * bar_width)
        i_end = int(e / total_duration * bar_width) + 1
        i_start = max(0, min(i_start, bar_width - 1))
        i_end = max(i_start + 1, min(i_end, bar_width))
        for i in range(i_start, i_end):
            bar[i] = "\u2588"

    return "|" + "".join(bar) + "|"


def _print_match_location(match_details: dict) -> None:
    """映像マッチ位置の詳細を表示"""
    matched = match_details.get("matched_frames", 0)
    total = match_details.get("total_frames", 0)
    ratio = match_details.get("match_ratio", 0)
    regions = match_details.get("regions", [])
    q_dur = match_details.get("query_duration", 0)
    db_dur = match_details.get("db_duration", 0)

    print(f"     🎯 映像マッチ分析:")
    print(
        f"        一致フレーム: {matched}/{total} "
        f"({ratio * 100:.1f}%)"
    )

    if not regions:
        print("        一致区間なし")
        return

    for j, reg in enumerate(regions, 1):
        qs = _format_duration(reg["query_start"])
        qe = _format_duration(reg["query_end"])
        ds = _format_duration(reg["db_start"])
        de = _format_duration(reg["db_end"])
        q_len = reg["query_end"] - reg["query_start"]
        d_len = reg["db_end"] - reg["db_start"]
        fc = reg.get("frame_count", 0)
        avg = reg.get("avg_similarity", 0)
        print(
            f"        区間{j}: クエリ {qs} - {qe} "
            f"({q_len:.1f}s) → DB {ds} - {de} ({d_len:.1f}s) "
            f"[{fc}フレーム, 類似度{avg:.3f}]"
        )

    # クエリ映像のバー可視化
    if q_dur > 0:
        print(
            f"     クエリ映像 ({_format_duration(q_dur)}):"
        )
        bar = _render_bar(q_dur, regions, key="query")
        print(f"      {bar}")
        print(
            f"       0:00{' ' * 48}"
            f"{_format_duration(q_dur)}"
        )

    # DB映像のバー可視化
    if db_dur > 0:
        print(
            f"     DB映像 ({_format_duration(db_dur)}):"
        )
        bar = _render_bar(db_dur, regions, key="db")
        print(f"      {bar}")
        print(
            f"       0:00{' ' * 48}"
            f"{_format_duration(db_dur)}"
        )

    print(
        "     📍 凡例: "
        "█ = 一致区間, - = 非一致"
    )


def print_search_results(
    results: List[Dict[str, Any]],
    query_name: str,
    show_details: bool = False,
) -> None:
    """検索結果を表示する"""

    # 信頼度0.3以上のマッチのみ対象
    valid_results = [
        r for r in results if r.get("similarity", 0) >= 0.3
    ]

    if not valid_results:
        print(f"\n  マッチなし: '{query_name}'")
        if results:
            print(f"  （低信頼度の結果が {len(results)} 件あります）")
        print("  データベースに映像を追加するか、映像品質を確認してください")
        return

    print(f"\n  {len(valid_results)} 件のマッチが見つかりました: '{query_name}'")
    if len(results) > len(valid_results):
        excluded = len(results) - len(valid_results)
        print(f"  （低信頼度の {excluded} 件は除外）")
    print("-" * 70)

    for i, result in enumerate(valid_results, 1):
        video = result.get("video")
        similarity = result.get("similarity", 0)
        video_sim = result.get("video_similarity")
        frame_sim = result.get("frame_similarity")

        title = video.title if video else "不明"
        file_path = video.file_path if video else "不明"
        duration = video.duration if video else 0

        print(f"  {i}. {title}")
        print(f"     最終スコア: {_format_similarity(similarity)}")

        if show_details:
            if video_sim is not None:
                print(f"     映像全体類似度: {video_sim:.3f}")
            if frame_sim is not None:
                print(f"     フレーム類似度: {frame_sim:.3f} (PiP対策)")
            if duration > 0:
                print(f"     映像長: {_format_duration(duration)}")
            if video and video.frame_count:
                print(f"     フレーム数: {video.frame_count}")

            # 映像マッチ位置の可視化
            match_details = result.get("match_details")
            if match_details:
                _print_match_location(match_details)

        print(f"     ファイル: {file_path}")

        if i < len(valid_results):
            print()


def search_single_file(
    file_path: str,
    mimizam: Mimizam,
    top_k: int = 5,
    use_frame_matching: bool = True,
    show_details: bool = False,
    video_db_path: Optional[str] = None,
    detect_pip: bool = False,
) -> None:
    """
    単一の動画ファイルで映像指紋検索を実行する

    Args:
        file_path: 検索対象の動画ファイルパス
        mimizam: Mimizamインスタンス
        top_k: 返す結果の最大数
        use_frame_matching: フレーム単位マッチングを使用するか
        show_details: 詳細情報を表示するか
        video_db_path: 映像指紋DBのパス
        detect_pip: PiP検出を有効化するか
    """
    logger = logging.getLogger(__name__)

    try:
        query_name = Path(file_path).name
        logger.info(f"検索中: {query_name}")

        results = mimizam.search_video(
            query_file_path=file_path,
            top_k=top_k,
            use_frame_matching=use_frame_matching,
            detect_pip=detect_pip,
            video_db_path=video_db_path,
        )

        logger.info(f"候補: {len(results)} 件")
        print_search_results(results, query_name, show_details)

    except Exception as exc:
        logger.error(f"検索エラー ({file_path}): {exc}")


def search_folder(
    folder_path: str,
    mimizam: Mimizam,
    top_k: int = 5,
    use_frame_matching: bool = True,
    show_details: bool = False,
    video_db_path: Optional[str] = None,
    detect_pip: bool = False,
) -> None:
    """
    フォルダ内の全動画ファイルで映像指紋検索を実行する

    Args:
        folder_path: 検索対象のフォルダパス
        mimizam: Mimizamインスタンス
        top_k: 返す結果の最大数
        use_frame_matching: フレーム単位マッチングを使用するか
        show_details: 詳細情報を表示するか
        video_db_path: 映像指紋DBのパス
        detect_pip: PiP検出を有効化するか
    """
    logger = logging.getLogger(__name__)

    folder = Path(folder_path)
    video_files = sorted(
        str(f) for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not video_files:
        logger.warning(f"動画ファイルが見つかりません: {folder_path}")
        return

    logger.info(f"{len(video_files)} 本の動画を検索します")

    for i, file_path in enumerate(video_files, 1):
        print(f"\n{'='*20} [{i}/{len(video_files)}] {'='*20}")
        search_single_file(
            file_path, mimizam, top_k,
            use_frame_matching, show_details, video_db_path,
            detect_pip,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="映像指紋（視覚特徴量）検索ツール - AKAZE + VLAD + PCA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # 単一ファイルで検索
  python visual_from_video_search.py /path/to/query.mp4 --model model.pkl

  # 詳細情報付きで検索
  python visual_from_video_search.py /path/to/query.mp4 --model model.pkl --details

  # フォルダ内の全動画で検索
  python visual_from_video_search.py /path/to/folder --model model.pkl --details

  # フレーム単位マッチングを無効化（高速モード）
  python visual_from_video_search.py /path/to/query.mp4 --model model.pkl --no-frame-matching

  # MySQLバックエンドを使用
  python visual_from_video_search.py /path/to/query.mp4 --model model.pkl --db-type mysql \\
      --db-host localhost --db-name mimizam --db-user user --db-password pass

modelファイルは scripts/train_pretrained_model.py で事前学習。
AKAZE記述子→VLAD集約→PCA圧縮の変換パイプラインを保持し、
登録時と検索時で同じ変換を適用するために必須。
""",
    )

    parser.add_argument(
        "target",
        help="検索対象の動画ファイルまたはフォルダのパス",
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
             "AKAZE記述子→VLAD→PCA変換に使用。"
             "scripts/train_pretrained_model.py で事前学習",
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
        "--top-k", "-k",
        type=int,
        default=5,
        help="表示する最大結果数（デフォルト: 5）",
    )
    parser.add_argument(
        "--no-frame-matching",
        action="store_true",
        help="フレーム単位マッチングを無効化（高速モード）",
    )
    parser.add_argument(
        "--detect-pip",
        action="store_true",
        help="PiP（ピクチャー・イン・ピクチャー）検出を有効化",
    )
    parser.add_argument(
        "--details", "-D",
        action="store_true",
        help="映像全体/フレーム類似度などの詳細情報を表示",
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
        if not os.path.exists(args.target):
            logger.error(f"パスが見つかりません: {args.target}")
            return 1

        # Mimizamシステムを初期化
        logger.info("Mimizamシステムを初期化中...")
        mimizam = create_mimizam_instance(args)

        # VLAD/PCAモデルの読み込み（検索時も指紋生成に必須）
        if not os.path.isfile(args.model):
            logger.error(f"モデルファイルが見つかりません: {args.model}")
            logger.info(
                "visual_from_video_fingerprinter.py --model model.pkl で"
                "モデルを生成してください"
            )
            return 1
        mimizam.load_video_model(args.model)
        logger.info(f"モデル読み込み完了: {args.model}")

        # 映像指紋DB統計を表示
        stats = mimizam.get_video_database_stats(args.video_db)
        video_count = stats.get("videos", 0)
        logger.info(
            f"映像指紋DB統計 - "
            f"映像数: {video_count}, "
            f"フレーム指紋: {stats.get('frame_fingerprints', 0)}"
        )

        if video_count == 0:
            logger.error("データベースが空です")
            logger.info(
                "visual_from_video_fingerprinter.py を使って映像を登録してください"
            )
            return 1

        use_frame = not args.no_frame_matching
        target_path = Path(args.target)

        if target_path.is_file():
            if target_path.suffix.lower() not in VIDEO_EXTENSIONS:
                logger.error(f"未対応のファイル形式: {target_path.suffix}")
                return 1

            search_single_file(
                args.target, mimizam,
                top_k=args.top_k,
                use_frame_matching=use_frame,
                show_details=args.details,
                video_db_path=args.video_db,
                detect_pip=args.detect_pip,
            )

        elif target_path.is_dir():
            search_folder(
                args.target, mimizam,
                top_k=args.top_k,
                use_frame_matching=use_frame,
                show_details=args.details,
                video_db_path=args.video_db,
                detect_pip=args.detect_pip,
            )

        else:
            logger.error(f"無効なパス: {args.target}")
            return 1

        logger.info("検索完了")
        return 0

    except KeyboardInterrupt:
        logger.info("ユーザーにより中断されました")
        return 1
    except Exception:
        logger.exception("予期しないエラーが発生しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
