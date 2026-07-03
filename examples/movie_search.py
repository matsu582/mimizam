#!/usr/bin/env python3
"""
動画統合検索ツール

動画ファイルから音声指紋と映像指紋の両方で検索し、
結果を統合して表示する。
video_search.py（音声検索）とvisual_search.py（映像検索）を
統合したスクリプト。

同一UUIDで登録された音声・映像の結果をIDで結合し、
統合スコアを算出する。
"""

import argparse
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from mimizam import (
    Mimizam,
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch,
    DatabaseConfig,
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


def extract_audio(video_path: str, temp_dir: str) -> str:
    """ffmpegで動画から音声を抽出する"""
    video_name = Path(video_path).stem
    output_path = os.path.join(temp_dir, f"{video_name}.wav")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "22050",
        "-ac", "1",
        "-y",
        output_path,
    ]

    subprocess.run(
        cmd, capture_output=True, text=True, check=True,
    )
    return output_path


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
            bar[i] = "\u2588"

    return "|" + "".join(bar) + "|"


def merge_results(
    audio_results: List[Dict[str, Any]],
    visual_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    音声検索と映像検索の結果をIDで結合し統合スコアを算出する

    同一UUIDで登録されている場合、song_idとvideo_idが一致する。
    両方一致した場合は高スコア、片方のみでも結果に含める。

    Args:
        audio_results: 音声検索結果
        visual_results: 映像検索結果

    Returns:
        統合された検索結果のリスト
    """
    # 音声結果をIDでインデックス化
    audio_map: Dict[str, Dict] = {}
    for match in audio_results:
        song = match.get("song")
        if song:
            sid = song.song_id if hasattr(song, "song_id") else str(song)
            audio_map[sid] = match

    # 映像結果をIDでインデックス化
    visual_map: Dict[str, Dict] = {}
    for result in visual_results:
        vid = result.get("video_id", "")
        visual_map[vid] = result

    # 全IDの和集合で統合
    all_ids = set(audio_map.keys()) | set(visual_map.keys())
    merged = []

    for item_id in all_ids:
        audio = audio_map.get(item_id)
        visual = visual_map.get(item_id)

        a_score = 0.0
        v_score = 0.0
        entry: Dict[str, Any] = {"id": item_id}

        if audio:
            a_score = audio.get("confidence", 0)
            entry["audio_confidence"] = a_score
            entry["audio_match"] = audio

        if visual:
            v_score = visual.get("similarity", 0)
            entry["visual_similarity"] = v_score
            entry["visual_match"] = visual

        # 統合スコア: 幾何平均ベース
        # 両方一致→高い、片方のみ→中程度の高め、両方低い→低いまま
        if a_score > 0 and v_score > 0:
            entry["combined_score"] = math.sqrt(a_score * v_score)
        else:
            entry["combined_score"] = max(a_score, v_score) * 0.8

        # タイトルの取得
        title = _extract_title(audio, visual)
        entry["title"] = title

        # ファイルパスの取得
        file_path = _extract_file_path(audio, visual)
        entry["file_path"] = file_path

        merged.append(entry)

    merged.sort(key=lambda x: x["combined_score"], reverse=True)
    return merged


def _extract_title(
    audio: Optional[Dict], visual: Optional[Dict],
) -> str:
    """音声/映像結果からタイトルを取得する"""
    if audio:
        song = audio.get("song")
        if song and hasattr(song, "title"):
            return song.title
    if visual:
        video = visual.get("video")
        if video and hasattr(video, "title"):
            return video.title
    return "不明"


def _extract_file_path(
    audio: Optional[Dict], visual: Optional[Dict],
) -> str:
    """音声/映像結果からファイルパスを取得する"""
    if visual:
        video = visual.get("video")
        if video and hasattr(video, "file_path"):
            return video.file_path
    if audio:
        song = audio.get("song")
        if song and hasattr(song, "file_path"):
            return song.file_path
    return "不明"


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
            _print_audio_match_detail(details)

    # 映像情報
    if v_sim is not None:
        visual = result.get("visual_match", {})
        video_sim = visual.get("video_similarity")
        frame_sim = visual.get("frame_similarity")
        video = visual.get("video")

        print(f"     --- 映像マッチ ---")
        print(f"     映像類似度: {v_sim:.3f}")
        if video_sim is not None:
            print(f"     全体指紋: {video_sim:.3f}")
        if frame_sim is not None:
            print(f"     フレーム指紋: {frame_sim:.3f}")
        if video and hasattr(video, "duration") and video.duration > 0:
            print(f"     映像長: {_format_duration(video.duration)}")

        match_details = visual.get("match_details")
        if match_details:
            _print_visual_match_detail(match_details)


def _print_audio_match_detail(details: Dict) -> None:
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

    # 一致区間の計算（時間差の中央値でクラスタリング）
    time_diffs = sorted(
        pos["time_diff"] for pos in positions
    )
    median_offset = time_diffs[len(time_diffs) // 2]

    # 中央値±0.5秒以内の一致ポジションを集計
    consistent = [
        p for p in positions
        if abs(p["time_diff"] - median_offset) < 0.5
    ]

    if consistent:
        db_times = [p["db_time"] for p in consistent]
        q_times = [p["query_time"] for p in consistent]
        db_start, db_end = min(db_times), max(db_times)
        q_start, q_end = min(q_times), max(q_times)
        db_dur = db_end - db_start
        q_dur = q_end - q_start

        print(
            f"     一致区間: クエリ "
            f"{_format_duration(q_start)} - "
            f"{_format_duration(q_end)} ({q_dur:.1f}s) → "
            f"DB {_format_duration(db_start)} - "
            f"{_format_duration(db_end)} ({db_dur:.1f}s)"
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

    audio_results: List[Dict] = []
    visual_results: List[Dict] = []

    # 音声検索
    if not skip_audio:
        temp_dir = tempfile.mkdtemp(prefix="movie_search_")
        try:
            audio_path = extract_audio(file_path, temp_dir)
            raw_matches = mimizam.search_song(
                audio_path,
                min_confidence=0.0,
                top_k=top_k * 4,
            )
            # 結果を変換
            for match in raw_matches:
                song = match["song"]
                details = match["details"]
                entry = {
                    "song": song,
                    "confidence": match["confidence"],
                    "match_count": match["match_count"],
                    "time_offset": details.get("time_offset", 0),
                    "time_scale": details.get("time_scale", 1.0),
                    "freq_scale": details.get("freq_scale", 1.0),
                }
                if show_details and "detailed_info" in details:
                    entry["detailed_info"] = details["detailed_info"]
                audio_results.append(entry)
            logger.info(f"音声候補: {len(audio_results)} 件")
        except Exception as exc:
            logger.warning(f"音声検索エラー: {exc}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # 映像検索
    if not skip_visual:
        try:
            visual_results = mimizam.search_video(
                query_file_path=file_path,
                top_k=top_k * 4,
                use_frame_matching=use_frame_matching,
                detect_pip=detect_pip,
                video_db_path=video_db_path,
            )
            logger.info(f"映像候補: {len(visual_results)} 件")
        except Exception as exc:
            logger.warning(f"映像検索エラー: {exc}")

    # 結果の統合
    merged = merge_results(audio_results, visual_results)
    logger.info(f"統合候補: {len(merged)} 件")

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
                f"映像指紋: "
                f"{video_stats.get('video_fingerprints', 0)}, "
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
