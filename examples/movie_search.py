#!/usr/bin/env python3
"""
動画統合検索ツール

動画ファイルから音声指紋と映像指紋の両方で検索し、
結果を統合して表示する。
audio_from_video_search.py（音声検索）とvisual_from_video_search.py（映像検索）を
統合したスクリプト。

同一UUIDで登録された音声・映像の結果をIDで結合し、
統合スコアを算出する。

統合スコアの算出
----------------
音声指紋の信頼度と映像指紋の実効映像スコア（被覆率・得票率を反映した
スコア。詳細は docs/video_fingerprint_spec.md 3.3 を参照）を突き合わせる。

    両モダリティ一致（かつ位置が乖離しない）:
        統合 = √(音声信頼度 × 実効映像スコア)   （幾何平均）
    片方のみ / 位置乖離あり:
        統合 = max(音声信頼度, 実効映像スコア) × 0.8

統合スコアが 0.3 未満の結果は除外する。

位置乖離チェック
----------------
同一映像で音声・映像の両方が一致しても、音声が指すDB区間と映像が指す
DB区間が大きく離れている（隙間 > 30秒）場合は、別々の箇所での偶発一致で
あり「音声＋映像の二重一致」とは認めない。この場合は幾何平均で持ち上げず
単独モダリティ評価に切り替え、表示に「※音声位置が映像と乖離（二重一致
から除外）」を明記する。これにより、誤整列由来の薄い一致が二重一致で
過大評価される偽陽性を抑制する。

統合検索のパラメータ
--------------------
    位置乖離許容    30.0秒   音声DB区間と映像DB区間の隙間がこれを超えると乖離扱い
    統合スコア閾値  0.3      これ未満の統合スコアは結果から除外
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mimizam import (
    Mimizam,
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch,
    DatabaseConfig,
    dominant_time_offset,
)

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
            logging.FileHandler("movie_search.log"),
        ],
    )


def create_mimizam_instance(args) -> Mimizam:
    """コマンドライン引数に基づいてMimizamインスタンスを作成する"""
    fingerprinter_config = {
        "enable_adaptive_params": True,
    }
    matcher_config = {
        "min_confidence": 0.1,
        "max_results": args.top_k * 4,
        "scoring_method": "hybrid",
    }

    if args.db_type == "sqlite":
        return create_mimizam_sqlite(
            args.database, matcher_config,
            **fingerprinter_config,
        )

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
            matcher_config=matcher_config,
            **fingerprinter_config,
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
            matcher_config=matcher_config,
            **fingerprinter_config,
        )

    elif args.db_type == "elasticsearch":
        if not args.db_host:
            raise ValueError("Elasticsearchには --db-host が必要です")
        return create_mimizam_elasticsearch(
            host=args.db_host,
            port=args.db_port or 9200,
            index_name=args.db_name or "movie_fingerprints",
            matcher_config=matcher_config,
            **fingerprinter_config,
        )

    raise ValueError(f"未対応のデータベースタイプ: {args.db_type}")


def _get_video_duration(file_path: str) -> float:
    """ffprobeで動画の長さ（秒）を取得する"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "format=duration",
             "-of", "csv=p=0", file_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0


def _format_duration(seconds: float) -> str:
    """秒数を mm:ss 形式にフォーマットする"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def _format_similarity(similarity: float) -> str:
    """類似度に応じた表示テキストを返す"""
    if similarity >= 0.8:
        return f"HIGH   ({similarity:.3f})"
    elif similarity >= 0.5:
        return f"MEDIUM ({similarity:.3f})"
    else:
        return f"LOW    ({similarity:.3f})"


def _format_time_offset(offset: float) -> str:
    """時間オフセットを人間が読める形式に変換する"""
    abs_time = abs(offset)
    hours = int(abs_time // 3600)
    minutes = int((abs_time % 3600) // 60)
    seconds = int(abs_time % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


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
            bar[i] = "█"

    return "|" + "".join(bar) + "|"


def print_merged_results(
    results: List[Dict[str, Any]],
    query_name: str,
    show_details: bool = False,
    top_k: int = 5,
) -> None:
    """統合検索結果を表示する"""

    # 信頼度0.3以上のマッチのみ対象
    valid = [r for r in results if r["combined_score"] >= 0.3]
    valid = valid[:top_k]

    if not valid:
        print(f"\n  マッチなし: '{query_name}'")
        if results:
            print(f"  （低信頼度の結果が {len(results)} 件あります）")
        return

    print(
        f"\n  {len(valid)} 件のマッチが見つかりました: "
        f"'{query_name}'"
    )
    print("-" * 70)

    for i, result in enumerate(valid, 1):
        title = result["title"]
        combined = result["combined_score"]
        a_conf = result.get("audio_confidence")
        v_sim = result.get("visual_similarity")

        # マッチ種別の表示
        match_types = []
        if a_conf is not None:
            match_types.append("音声")
        if v_sim is not None:
            match_types.append("映像")
        type_str = "+".join(match_types)
        if result.get("position_diverged") and a_conf is not None and v_sim is not None:
            type_str += " ※音声位置が映像と乖離（二重一致から除外）"

        print(f"  {i}. {title}")
        print(
            f"     統合スコア: {_format_similarity(combined)}"
            f"  [{type_str}]"
        )

        if show_details:
            _print_detail_section(result)

        print(f"     ファイル: {result['file_path']}")

        if i < len(valid):
            print()


def _print_detail_section(result: Dict[str, Any]) -> None:
    """詳細情報セクションを表示する"""
    a_conf = result.get("audio_confidence")
    v_sim = result.get("visual_similarity")

    # 音声情報
    if a_conf is not None:
        audio = result.get("audio_match", {})
        match_count = audio.get("match_count", 0)
        time_offset = audio.get("time_offset", 0)
        time_scale = audio.get("time_scale", 1.0)
        freq_scale = audio.get("freq_scale", 1.0)

        print(f"     --- 音声マッチ ---")
        print(f"     信頼度: {a_conf:.2%}")
        print(f"     指紋一致数: {match_count}")
        print(
            f"     時間オフセット: "
            f"at {_format_time_offset(time_offset)}"
        )

        if abs(time_scale - 1.0) > 0.01 or abs(freq_scale - 1.0) > 0.01:
            print(
                f"     速度変化: {time_scale:.2f}x, "
                f"ピッチ: {freq_scale:.2f}x"
            )

        # 音声の詳細マッチ位置
        details = audio.get("detailed_info")
        if details:
            q_dur = result.get("query_duration", 0)
            # DB曲の長さを推定
            db_dur = 0.0
            v_match = result.get("visual_match")
            if v_match:
                video = v_match.get("video")
                if video and hasattr(video, "duration"):
                    db_dur = video.duration
            if db_dur <= 0:
                st = details.get("statistics", {})
                db_range = st.get(
                    "db_time_range", (0, 0)
                )
                db_dur = db_range[1] if db_range[1] > 0 else 0
            _print_audio_match_detail(
                details, q_dur, db_dur,
            )

    # 映像情報
    if v_sim is not None:
        visual = result.get("visual_match", {})
        video_sim = visual.get("video_similarity")
        frame_sim = visual.get("frame_similarity")
        votes = visual.get("vote_count")
        video = visual.get("video")

        print(f"     --- 映像マッチ ---")
        print(f"     映像類似度: {v_sim:.3f}")
        if votes is not None:
            print(f"     候補得票(ANN): {votes}票 平均類似度: "
                  f"{(video_sim or 0.0):.3f}")
        if frame_sim is not None:
            print(f"     フレーム指紋: {frame_sim:.3f}")
        if video and hasattr(video, "duration") and video.duration > 0:
            print(f"     映像長: {_format_duration(video.duration)}")

        match_details = visual.get("match_details")
        if match_details:
            _print_visual_match_detail(match_details)


def _print_audio_match_detail(
    details: Dict,
    query_duration: float = 0,
    db_duration: float = 0,
) -> None:
    """音声マッチの詳細位置情報を表示する"""
    stats = details.get("statistics", {})
    positions = details.get("match_positions", [])

    aligned = stats.get("aligned_matches", 0)
    total = stats.get("total_matches", 0)
    ratio = stats.get("alignment_ratio", 0)

    print(
        f"     時間整列マッチ: {aligned}/{total} "
        f"({ratio:.1%})"
    )

    if not positions:
        return

    # 一致区間の計算（時間差の最頻ビンでクラスタリング）
    # 全マッチの中央値は全編に散るノイズに引かれて誤位置を示すため、
    # 最大整列クラスタ＝最頻ビンの中心を代表オフセットに採る。
    time_diffs = [pos["time_diff"] for pos in positions]
    dominant_offset = dominant_time_offset(time_diffs)

    # 最頻オフセット±2秒以内の一致ポジションを集計
    consistent = [
        p for p in positions
        if abs(p["time_diff"] - dominant_offset) < 2.0
    ]

    if consistent:
        db_times = [p["db_time"] for p in consistent]
        q_times = [p["query_time"] for p in consistent]
        db_start, db_end = min(db_times), max(db_times)
        q_start, q_end = min(q_times), max(q_times)
        span_db = db_end - db_start
        span_q = q_end - q_start

        print(
            f"     一致区間: クエリ "
            f"{_format_duration(q_start)} - "
            f"{_format_duration(q_end)} ({span_q:.1f}s) → "
            f"DB {_format_duration(db_start)} - "
            f"{_format_duration(db_end)} ({span_db:.1f}s)"
        )

        # バー可視化
        regions = [{
            "query_start": q_start,
            "query_end": max(q_end, q_start + 0.5),
            "db_start": db_start,
            "db_end": max(db_end, db_start + 0.5),
        }]

        if query_duration > 0:
            print(
                f"     クエリ音声 "
                f"({_format_duration(query_duration)}):"
            )
            bar = _render_bar(
                query_duration, regions, key="query",
            )
            print(f"      {bar}")
            print(
                f"       0:00{' ' * 48}"
                f"{_format_duration(query_duration)}"
            )

        if db_duration > 0:
            print(
                f"     DB音声 "
                f"({_format_duration(db_duration)}):"
            )
            bar = _render_bar(
                db_duration, regions, key="db",
            )
            print(f"      {bar}")
            print(
                f"       0:00{' ' * 48}"
                f"{_format_duration(db_duration)}"
            )


def _print_visual_match_detail(match_details: Dict) -> None:
    """映像マッチの詳細位置情報を表示する"""
    matched = match_details.get("matched_frames", 0)
    total = match_details.get("total_frames", 0)
    ratio = match_details.get("match_ratio", 0)
    regions = match_details.get("regions", [])
    q_dur = match_details.get("query_duration", 0)
    db_dur = match_details.get("db_duration", 0)

    print(
        f"     一致フレーム: {matched}/{total} "
        f"({ratio * 100:.1f}%)"
    )

    if not regions:
        print("     一致区間なし")
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
            f"     区間{j}: クエリ {qs} - {qe} "
            f"({q_len:.1f}s) → DB {ds} - {de} ({d_len:.1f}s) "
            f"[{fc}フレーム, 類似度{avg:.3f}]"
        )

    # バー可視化
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


def search_single_file(
    file_path: str,
    mimizam: Mimizam,
    top_k: int = 5,
    use_frame_matching: bool = True,
    detect_pip: bool = False,
    show_details: bool = False,
    video_db_path: Optional[str] = None,
    skip_audio: bool = False,
    skip_visual: bool = False,
) -> None:
    """
    単一の動画ファイルで音声+映像の統合検索を実行する

    Args:
        file_path: 検索対象の動画ファイルパス
        mimizam: Mimizamインスタンス
        top_k: 返す結果の最大数
        use_frame_matching: フレーム単位マッチングを使用するか
        detect_pip: PiP検出を有効化するか
        show_details: 詳細情報を表示するか
        video_db_path: 映像指紋DBのパス
        skip_audio: 音声検索をスキップ
        skip_visual: 映像検索をスキップ
    """
    logger = logging.getLogger(__name__)
    query_name = Path(file_path).name
    logger.info(f"検索中: {query_name}")

    # 音声＋映像の統合検索（統合スコア・位置乖離チェックはAPI側で実施）
    merged = mimizam.search_movie(
        query_file_path=file_path,
        top_k=top_k,
        use_frame_matching=use_frame_matching,
        detect_pip=detect_pip,
        video_db_path=video_db_path,
        skip_audio=skip_audio,
        skip_visual=skip_visual,
    )
    logger.info(f"統合候補: {len(merged)} 件")

    # クエリ動画の長さを取得してマージ結果に付与
    q_dur = _get_video_duration(file_path)
    if q_dur > 0:
        for entry in merged:
            entry["query_duration"] = q_dur

    # 結果の表示
    print_merged_results(
        merged, query_name, show_details, top_k,
    )


def search_folder(
    folder_path: str,
    mimizam: Mimizam,
    top_k: int = 5,
    use_frame_matching: bool = True,
    detect_pip: bool = False,
    show_details: bool = False,
    video_db_path: Optional[str] = None,
    skip_audio: bool = False,
    skip_visual: bool = False,
) -> None:
    """フォルダ内の全動画で統合検索を実行する"""
    logger = logging.getLogger(__name__)

    folder = Path(folder_path)
    video_files = sorted(
        str(f) for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not video_files:
        logger.warning(
            f"動画ファイルが見つかりません: {folder_path}"
        )
        return

    logger.info(f"{len(video_files)} 本の動画を検索します")

    for i, fp in enumerate(video_files, 1):
        print(f"\n{'=' * 20} [{i}/{len(video_files)}] {'=' * 20}")
        search_single_file(
            fp, mimizam, top_k,
            use_frame_matching, detect_pip,
            show_details, video_db_path,
            skip_audio, skip_visual,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="動画統合検索ツール（音声+映像）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用例:
  # 音声+映像の両方で検索
  python movie_search.py /path/to/query.mp4 \\
      --model model.pki --details

  # 映像のみで検索（音声スキップ）
  python movie_search.py /path/to/query.mp4 \\
      --model model.pki --skip-audio --details

  # PiP検出付きで検索
  python movie_search.py /path/to/query.mp4 \\
      --model model.pki --detect-pip --details
""",
    )

    parser.add_argument(
        "target",
        help="検索対象の動画ファイルまたはフォルダのパス",
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
        "--top-k", "-k",
        type=int,
        default=5,
        help="表示する最大結果数（デフォルト: 5）",
    )
    parser.add_argument(
        "--no-frame-matching",
        action="store_true",
        help="映像フレーム単位マッチングを無効化（高速モード）",
    )
    parser.add_argument(
        "--detect-pip",
        action="store_true",
        help="PiP（ピクチャー・イン・ピクチャー）検出を有効化",
    )
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="音声検索をスキップ（映像のみ検索）",
    )
    parser.add_argument(
        "--skip-visual",
        action="store_true",
        help="映像検索をスキップ（音声のみ検索）",
    )
    parser.add_argument(
        "--details", "-D",
        action="store_true",
        help="詳細な一致位置情報を表示",
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
        help="シーン検出の評価fps（既定4.0）。登録時と同じ値に揃える必要がある。"
             "登録を8fpsで行った場合は検索も8を指定する",
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

        if not os.path.exists(args.target):
            logger.error(f"パスが見つかりません: {args.target}")
            return 1

        # Mimizamシステムを初期化
        logger.info("Mimizamシステムを初期化中...")
        mimizam = create_mimizam_instance(args)

        # 映像指紋の実行時設定（環境変数ではなくConfig経由で渡す）
        mimizam.configure_video(scene_eval_fps=args.scene_eval_fps or None)

        # 映像モデルの読み込み
        if not args.skip_visual:
            if not os.path.isfile(args.model):
                logger.error(
                    f"モデルファイルが見つかりません: {args.model}"
                )
                return 1
            mimizam.load_video_model(args.model)
            logger.info(f"映像モデル読み込み完了: {args.model}")

        # DB統計を表示
        audio_stats = mimizam.get_database_stats()
        logger.info(
            f"音声指紋DB - "
            f"楽曲数: {audio_stats.get('songs', 0)}, "
            f"指紋数: {audio_stats.get('fingerprints', 0)}"
        )

        if not args.skip_visual:
            video_stats = mimizam.get_video_database_stats(
                args.database
            )
            logger.info(
                f"映像指紋DB - "
                f"映像数: {video_stats.get('videos', 0)}, "
                f"フレーム指紋: "
                f"{video_stats.get('frame_fingerprints', 0)}"
            )

        use_frame = not args.no_frame_matching
        target_path = Path(args.target)

        if target_path.is_file():
            if target_path.suffix.lower() not in VIDEO_EXTENSIONS:
                logger.error(
                    f"未対応のファイル形式: {target_path.suffix}"
                )
                return 1

            search_single_file(
                args.target, mimizam,
                top_k=args.top_k,
                use_frame_matching=use_frame,
                detect_pip=args.detect_pip,
                show_details=args.details,
                video_db_path=args.database,
                skip_audio=args.skip_audio,
                skip_visual=args.skip_visual,
            )

        elif target_path.is_dir():
            search_folder(
                args.target, mimizam,
                top_k=args.top_k,
                use_frame_matching=use_frame,
                detect_pip=args.detect_pip,
                show_details=args.details,
                video_db_path=args.database,
                skip_audio=args.skip_audio,
                skip_visual=args.skip_visual,
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
