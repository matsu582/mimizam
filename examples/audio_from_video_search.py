"""
動画音声検索ツール

このスクリプトは動画ファイルから音声を抽出し、
Shazam風アルゴリズムを使用して指紋データベースでのマッチを検索する。
簡素化された音声指紋生成にMimizam APIを使用。
"""

import os
import sys
import argparse
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import tempfile
import subprocess

# インストール済みのmimizamパッケージからインポート
from mimizam import Mimizam, create_mimizam_sqlite, create_mimizam_mysql, create_mimizam_postgresql, create_mimizam_elasticsearch, DatabaseConfig
from mimizam import dominant_time_offset

# サポートされている動画ファイル拡張子
VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
    '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts'
}

# サポートされている音声ファイル拡張子
AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'
}


class VideoAudioExtractor:
    """ffmpegを使用して動画ファイルから音声を抽出する"""
    
    def __init__(self):
        self.temp_dir = None
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix='video_search_')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def check_ffmpeg(self) -> bool:
        """ffmpegが利用可能かチェックする"""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def extract_audio(self, video_path: str, output_path: str = None) -> str:
        """
        動画ファイルから音声を抽出する
        
        Args:
            video_path: 動画ファイルのパス
            output_path: 出力音声ファイルのパス（オプション）
            
        Returns:
            抽出された音声ファイルのパス
        """
        if not self.check_ffmpeg():
            raise RuntimeError("ffmpeg not found. Please install ffmpeg to extract audio from videos.")
        
        if output_path is None:
            video_name = Path(video_path).stem
            output_path = os.path.join(self.temp_dir, f"{video_name}.wav")
        
        # 音声をWAVとして抽出するFFmpegコマンド
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # 動画なし
            '-acodec', 'pcm_s16le',  # PCM 16ビット リトルエンディアン
            '-ar', '22050',  # サンプルレート
            '-ac', '1',  # モノラル
            '-y',  # 出力ファイルを上書き
            output_path
        ]
        
        try:
            self.logger.info(f"Extracting audio from {video_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.debug(f"FFmpeg output: {result.stderr}")
            return output_path
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to extract audio from {video_path}: {e.stderr}")
            raise


def is_media_file(file_path: str) -> bool:
    """ファイルがサポートされているメディアファイルかチェックする"""
    suffix = Path(file_path).suffix.lower()
    return suffix in VIDEO_EXTENSIONS or suffix in AUDIO_EXTENSIONS


def _get_audio_path(file_path: str, extractor: Optional[VideoAudioExtractor]) -> str:
    """メディアファイルから音声パスを抽出する"""
    suffix = Path(file_path).suffix.lower()
    
    if suffix in VIDEO_EXTENSIONS:
        if extractor is None:
            raise ValueError("Video file provided but no extractor available")
        return extractor.extract_audio(file_path)
    
    return file_path


def _format_confidence_level(confidence: float) -> Tuple[str, str]:
    """信頼度の絵文字とテキストを取得する"""
    if confidence >= 0.8:
        return "🟢", "HIGH"
    elif confidence >= 0.5:
        return "🟡", "MEDIUM"
    else:
        return "🔴", "LOW"


def _format_time_offset(offset: float) -> str:
    """時間オフセットを人間が読める形式に変換する"""
    if offset >= 0:
        return f"+{offset:.1f}s"
    
    abs_time = abs(offset)
    hours = int(abs_time // 3600)
    minutes = int((abs_time % 3600) // 60)
    seconds = int(abs_time % 60)
    
    if hours > 0:
        return f"at {hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"at {minutes}:{seconds:02d}"


def _format_time_range(start_time: float, end_time: float) -> str:
    """時間範囲を人間が読める形式でフォーマットする"""
    def format_single_time(time_val: float) -> str:
        # 負の値の場合は絶対値を使って時分秒に変換
        abs_time = abs(time_val)
        hours = int(abs_time // 3600)
        minutes = int((abs_time % 3600) // 60)
        seconds = int(abs_time % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    return f"{format_single_time(start_time)} - {format_single_time(end_time)}"


def _format_time_mmss(seconds: float) -> str:
    """秒数を分:秒形式でフォーマットする"""
    abs_time = abs(seconds)
    hours = int(abs_time // 3600)
    minutes = int((abs_time % 3600) // 60)
    secs = int(abs_time % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def _print_match_results(matches: List[Dict[str, Any]], file_name: str, 
                        show_details: bool = False) -> None:
    """オプションの詳細マッチ情報付きで検索結果を表示する"""
    # MEDIUM以上（信頼度0.5以上）のマッチのみを対象とする
    valid_matches = [match for match in matches if match['confidence'] >= 0.5]
    
    if not valid_matches:
        print(f"\n❌ No reliable matches found for '{file_name}'")
        if len(matches) > 0:
            low_count = len(matches)
            print(f"   Found {low_count} low-confidence matches (excluded)")
        print("   Try adding more songs to the database or check audio quality")
        return
    
    print(f"\n🎵 Found {len(valid_matches)} reliable matches for '{file_name}':")
    if len(matches) > len(valid_matches):
        excluded_count = len(matches) - len(valid_matches)
        print(f"   (Excluded {excluded_count} low-confidence matches)")
    print("-" * 80)
    
    for i, match in enumerate(valid_matches, 1):
        # マッチ結果から情報を取得
        song_info = match.get('song_info', {})
        confidence = match['confidence']
        match_count = match['match_count']
        time_offset = match.get('time_offset', 0)
        time_scale = match.get('time_scale', 1.0)
        freq_scale = match.get('freq_scale', 1.0)
        
        conf_emoji, conf_text = _format_confidence_level(confidence)
        
        # song_infoから表示情報を取得（フォールバック付き）
        title = song_info.get('title', 'Unknown Title')
        artist = song_info.get('artist', 'Unknown Artist')
        file_path = song_info.get('file_path', 'Unknown File')
        
        print(f"{i}. {conf_emoji} {title} by {artist}")
        print(f"   Confidence: {confidence:.2%} ({conf_text})")
        print(f"   Matches: {match_count} fingerprints")
        print(f"   Time offset: {_format_time_offset(time_offset)}")
        
        # 標準でない場合、速度/ピッチの変化を表示
        if abs(time_scale - 1.0) > 0.01 or abs(freq_scale - 1.0) > 0.01:
            print(f"   Speed variation: {time_scale:.2f}x, Pitch: {freq_scale:.2f}x")
        
        print(f"   File: {file_path}")
        
        # 要求され、利用可能な場合は詳細マッチ情報を表示
        if show_details and 'detailed_info' in match:
            _print_detailed_match_info_from_result(match)
        
        if i < len(valid_matches):
            print()


def _render_bar(total_duration: float, regions: list,
                bar_width: int = 60, key: str = "query") -> str:
    """一致区間をバーで可視化する（movie_search と同方式）"""
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


def _print_detailed_match_info_from_result(match_result: Dict[str, Any]) -> None:
    """マッチ結果の詳細情報を movie_search と同じレイアウト（英語）で表示する"""
    if 'detailed_info' not in match_result:
        print("   ⚠️  No detailed information available")
        return

    details = match_result['detailed_info']
    stats = details.get('statistics', {})
    positions = details.get('match_positions', [])

    aligned = stats.get('aligned_matches', 0)
    total = stats.get('total_matches', 0)
    ratio = stats.get('alignment_ratio', 0)

    print("   --- Audio Match ---")
    print(f"   Time-aligned matches: {aligned}/{total} ({ratio:.1%})")

    if not positions:
        return

    # 全マッチの中央値はノイズに引かれてズレるため、最頻ビン（最大整列クラスタ）の
    # 中心を代表オフセットに採り、その±2秒に整列する一致だけで区間を決める。
    time_diffs = [pos['time_diff'] for pos in positions]
    dominant_offset = dominant_time_offset(time_diffs)
    consistent = [
        p for p in positions
        if abs(p['time_diff'] - dominant_offset) < 2.0
    ]
    if not consistent:
        return

    q_times = [p['query_time'] for p in consistent]
    db_times = [p['db_time'] for p in consistent]
    q_start, q_end = min(q_times), max(q_times)
    db_start, db_end = min(db_times), max(db_times)
    span_q = q_end - q_start
    span_db = db_end - db_start

    print(
        f"   Match region: Query "
        f"{_format_time_mmss(q_start)} - {_format_time_mmss(q_end)} "
        f"({span_q:.1f}s) -> DB "
        f"{_format_time_mmss(db_start)} - {_format_time_mmss(db_end)} "
        f"({span_db:.1f}s)"
    )

    regions = [{
        "query_start": q_start,
        "query_end": max(q_end, q_start + 0.5),
        "db_start": db_start,
        "db_end": max(db_end, db_start + 0.5),
    }]

    # クエリ全長は search_song が付与（=クエリ指紋の最大 time_offset）。
    query_duration = match_result.get('query_duration', 0.0) or 0.0
    # DB全長は楽曲の実長。無ければ一致した db_time の最大値で代替する。
    song_info = match_result.get('song_info', {})
    db_duration = song_info.get('duration') or 0.0
    if db_duration <= 0:
        db_range = stats.get('db_time_range', (0.0, 0.0))
        db_duration = db_range[1] if db_range and db_range[1] > 0 else 0.0

    if query_duration > 0:
        print(f"   Query Audio ({_format_time_mmss(query_duration)}):")
        bar = _render_bar(query_duration, regions, key="query")
        print(f"    {bar}")
        print(f"     0:00{' ' * 48}{_format_time_mmss(query_duration)}")

    if db_duration > 0:
        print(f"   Database Audio ({_format_time_mmss(db_duration)}):")
        bar = _render_bar(db_duration, regions, key="db")
        print(f"    {bar}")
        print(f"     0:00{' ' * 48}{_format_time_mmss(db_duration)}")


def search_single_file(file_path: str,
                      mimizam: Mimizam,
                      extractor: Optional[VideoAudioExtractor] = None,
                      show_details: bool = False) -> None:
    """
    Mimizamを使用して単一メディアファイルのマッチを検索する
    
    Args:
        file_path: メディアファイルのパス
        mimizam: Mimizamインスタンス
        extractor: VideoAudioExtractorインスタンス（動画ファイル用）
        show_details: 詳細マッチ情報を表示するかどうか
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Searching: {Path(file_path).name}")
        
        # 音声パスを取得（必要に応じて抽出）
        audio_path = _get_audio_path(file_path, extractor)
        if audio_path != file_path:
            logger.info(f"Audio extracted to: {audio_path}")
        
        # Mimizamを使用してマッチを検索
        matches = mimizam.search_song(
            audio_path, 
            min_confidence=0.0,  # 低い閾値で全ての結果を取得
            top_k=mimizam.matcher.max_results
        )
        
        # Mimizamの結果をvideo_searchの形式に変換
        converted_matches = []
        for match in matches:
            song = match['song']
            details = match['details']
            
            converted_match = {
                'song_info': {
                    'title': song.title,
                    'artist': song.artist,
                    'file_path': song.file_path,
                    'duration': song.duration,
                },
                'confidence': match['confidence'],
                'match_count': match['match_count'],
                'query_duration': match.get('query_duration', 0.0),
                'time_offset': details.get('time_offset', 0),
                'time_scale': details.get('time_scale', 1.0),
                'freq_scale': details.get('freq_scale', 1.0)
            }
            
            # 詳細情報があれば追加
            if show_details and 'detailed_info' in details:
                converted_match['detailed_info'] = details['detailed_info']
            
            converted_matches.append(converted_match)
        
        logger.info(f"Found {len(converted_matches)} potential matches")
        
        if len(converted_matches) == 0:
            logger.warning("No matches found - unable to identify audio")
            print(f"\n❌ No matches found for '{Path(file_path).name}'")
            print("   Try adding more songs to the database or check audio quality")
            return
        
        # オプションの詳細付きで結果を表示
        _print_match_results(converted_matches, Path(file_path).name, show_details)
        
    except Exception as e:
        logger.error(f"Error searching {file_path}: {e}")


def search_folder(folder_path: str,
                 mimizam: Mimizam,
                 show_details: bool = False) -> None:
    """
    Mimizamを使用してフォルダ内のすべてのメディアファイルのマッチを検索する
    
    Args:
        folder_path: メディアファイルを含むフォルダのパス
        mimizam: Mimizamインスタンス
        show_details: 詳細マッチ情報を表示するかどうか
    """
    logger = logging.getLogger(__name__)
    
    # すべてのメディアファイルを検索
    folder = Path(folder_path)
    media_files = []
    
    for file_path in folder.rglob('*'):
        if file_path.is_file() and is_media_file(str(file_path)):
            media_files.append(str(file_path))
    
    if not media_files:
        logger.warning(f"No media files found in {folder_path}")
        return
    
    logger.info(f"Found {len(media_files)} media files to search")
    
    with VideoAudioExtractor() as extractor:
        for i, file_path in enumerate(media_files, 1):
            print(f"\n{'='*20} File {i}/{len(media_files)} {'='*20}")
            search_single_file(file_path, mimizam, extractor, show_details)


def setup_logging(verbose: bool = False) -> None:
    """ログ設定のセットアップ"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('video_search.log')
        ]
    )


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Search for audio matches in fingerprint database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python audio_from_video_search.py /path/to/video.mp4
  python audio_from_video_search.py /path/to/video.mp4 --details
  python audio_from_video_search.py /path/to/folder --database custom.db --details
  python audio_from_video_search.py /path/to/audio.mp3 --verbose --details
  python audio_from_video_search.py /path/to/folder --min-confidence 0.7 --details
  python audio_from_video_search.py /path/to/video.mp4 --disable-adaptive --details
        """
    )
    
    parser.add_argument(
        'target',
        help='Path to media file or folder to search'
    )
    
    parser.add_argument(
        '--database', '-d',
        default='video_fingerprints.db',
        help='Path to fingerprint database (default: video_fingerprints.db)'
    )
    
    parser.add_argument(
        '--backend', '-b',
        choices=['sqlite', 'mysql', 'postgresql', 'elasticsearch'],
        default='sqlite',
        help='Database backend to use (default: sqlite)'
    )
    
    parser.add_argument(
        '--min-confidence', '-c',
        type=float,
        default=0.5,
        help='Minimum confidence threshold (0.0-1.0, default: 0.5 for MEDIUM+ reliability)'
    )
    
    parser.add_argument(
        '--max-results', '-n',
        type=int,
        default=10,
        help='Maximum number of results to display (default: 10)'
    )
    
    parser.add_argument(
        '--details', '-D',
        action='store_true',
        help='Show detailed match position information including timeline visualization'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--disable-adaptive',
        action='store_true',
        help='Disable adaptive fingerprint generation (default: enable)'
    )

    parser.add_argument(
        '--audible-only',
        action='store_true',
        help='Use only audible frequency range (20Hz-20kHz) for fingerprint generation'
    )

    parser.add_argument(
        '--scoring-method',
        choices=['hybrid', 'histogram', 'detailed'],
        default='hybrid',
        help='Scoring method: hybrid (2-stage), histogram (histogram-based), detailed (multi-faceted)'
    )
    
    args = parser.parse_args()
    
    # ログの設定
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # ターゲットパスを検証
        if not os.path.exists(args.target):
            logger.error(f"Target not found: {args.target}")
            return 1
        
        # 適切なバックエンドでMimizamを初期化
        logger.info("Initializing Mimizam...")
        
        # 指紋生成器設定を作成
        fingerprinter_config = {
            'enable_adaptive_params': not args.disable_adaptive,
            'audible_only': args.audible_only
        }
        
        # マッチャー設定を作成
        matcher_config = {
            'min_confidence': args.min_confidence,
            'max_results': args.max_results,
            'scoring_method': args.scoring_method
        }
        
        if args.backend == 'sqlite':
            # SQLite用のデータベースを検証
            if not os.path.exists(args.database):
                logger.error(f"SQLite database not found: {args.database}")
                logger.info("Run audio_from_video_fingerprinter.py first to create a database")
                return 1
            
            mimizam = create_mimizam_sqlite(args.database, matcher_config, **fingerprinter_config)
        
        elif args.backend == 'mysql':
            config = DatabaseConfig(backend='mysql')
            mimizam = Mimizam(config, fingerprinter_config, matcher_config)
        
        elif args.backend == 'postgresql':
            config = DatabaseConfig(backend='postgresql')
            mimizam = Mimizam(config, fingerprinter_config, matcher_config)
        
        elif args.backend == 'elasticsearch':
            config = DatabaseConfig(backend='elasticsearch')
            mimizam = Mimizam(config, fingerprinter_config, matcher_config)
        
        # データベース統計を表示
        stats = mimizam.database.get_database_stats()
        logger.info(f"Database stats - Songs: {stats['songs']}, Fingerprints: {stats['fingerprints']}")
        
        if stats['songs'] == 0:
            logger.error("Database is empty!")
            logger.info("Run audio_from_video_fingerprinter.py first to add songs to the database")
            return 1
        
        # 適応指紋生成ステータス
        if not args.disable_adaptive:
            logger.info("Using adaptive fingerprinting for optimal performance...")
        
        # ターゲットがファイルかフォルダかを判断
        target_path = Path(args.target)
        
        if target_path.is_file():
            # 単一ファイルを検索
            if not is_media_file(args.target):
                logger.error(f"Unsupported file type: {target_path.suffix}")
                return 1
            
            with VideoAudioExtractor() as extractor:
                search_single_file(args.target, mimizam, extractor, args.details)
        
        elif target_path.is_dir():
            # フォルダを検索
            search_folder(args.target, mimizam, args.details)
        
        else:
            logger.error(f"Invalid target: {args.target}")
            return 1
        
        logger.info("Search completed")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Search cancelled by user")
        return 1
    except Exception as e:
        logger.exception("An unexpected error occurred")
        # logger.error(f"Unexpected error: {e}", stack_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
