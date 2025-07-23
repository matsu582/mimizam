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


def _print_detailed_match_info_from_result(match_result: Dict[str, Any]) -> None:
    """マッチ結果から詳細情報を表示"""
    if 'detailed_info' not in match_result:
        print("      ⚠️  No detailed information available")
        return
    
    details = match_result['detailed_info']
    stats = details['statistics']
    match_positions = details['match_positions']
    
    print("   📊 Detailed Match Analysis:")
    print(f"      Total fingerprint matches: {stats['total_matches']}")
    print(f"      Time-aligned matches: {stats['aligned_matches']} ({stats['alignment_ratio']:.1%})")
    
    if not match_positions:
        print("      ⚠️  No match positions available")
        return
    
    # 時間差の統計を計算
    time_diffs = [pos['time_diff'] for pos in match_positions]
    time_diffs.sort()
    
    # 最頻値（中央値で近似）
    median_offset = time_diffs[len(time_diffs)//2]
    
    # クエリとDBの時間範囲
    query_times = [pos['query_time'] for pos in match_positions]
    db_times = [pos['db_time'] for pos in match_positions]
    
    query_start, query_end = min(query_times), max(query_times)
    db_start, db_end = min(db_times), max(db_times)
    
    print(f"      Best time alignment: {_format_time_offset(median_offset)}")
    print(f"      Query audio: {query_start:.1f}s - {query_end:.1f}s ({query_end-query_start:.1f}s)")
    print(f"      Database audio: {db_start:.1f}s - {db_end:.1f}s ({db_end-db_start:.1f}s)")
    
    # どの部分が一致しているかを分析
    est_query_start_in_db = query_start + median_offset
    est_query_end_in_db = query_end + median_offset
    
    print("   🎯 Match Location Analysis:")
    if median_offset < 0:
        # より厳しいフィルタリングで正確なマッチクラスターを特定
        consistent_matches = [pos for pos in match_positions 
                            if abs(pos['time_diff'] - median_offset) < 0.5]  # 0.5秒以内の誤差に厳格化
        
        if consistent_matches:
            consistent_db_times = [pos['db_time'] for pos in consistent_matches]
            consistent_query_times = [pos['query_time'] for pos in consistent_matches]
            
            actual_match_start = min(consistent_db_times)
            actual_match_end = max(consistent_db_times)
            actual_match_duration = actual_match_end - actual_match_start
            
            # クエリ側の対応する範囲も計算
            query_match_start = min(consistent_query_times)
            query_match_end = max(consistent_query_times)
            query_match_duration = query_match_end - query_match_start
            
            print(f"      • Query matches database from {_format_time_range(actual_match_start, actual_match_end)}")
            print(f"      • Actual match duration: {actual_match_duration:.1f}s (DB) / {query_match_duration:.1f}s (Query)")
            
            # より正確なカバレッジ情報
            if actual_match_duration < (query_end - query_start) * 0.5:  # 50%未満で部分マッチ
                coverage_pct = (query_match_duration / (query_end - query_start)) * 100
                print(f"      • Coverage: {coverage_pct:.1f}% of query audio matched (partial match)")
            else:
                print("      • Strong match coverage detected")
        else:
            print("      • No consistent match cluster found")
    else:
        print(f"      • Query appears to match DB at: {_format_time_range(est_query_start_in_db, est_query_end_in_db)}")
    
    # DB内での相対位置
    if db_end > db_start:
        relative_start = ((est_query_start_in_db - db_start) / (db_end - db_start)) * 100
        coverage = ((query_end - query_start) / (db_end - db_start)) * 100
        print(f"      • Query starts at {relative_start:.1f}% into database audio")
        print(f"      • Query covers {coverage:.1f}% of database duration")
    
    # 視覚化の追加 - マッチデータを使用
    if median_offset < 0:
        # より厳しいフィルタリングでマッチクラスターを再取得
        consistent_matches = [pos for pos in match_positions 
                            if abs(pos['time_diff'] - median_offset) < 0.5]
        
        if consistent_matches:
            consistent_db_times = [pos['db_time'] for pos in consistent_matches]
            consistent_query_times = [pos['query_time'] for pos in consistent_matches]
            
            actual_match_start = min(consistent_db_times)
            actual_match_end = max(consistent_db_times)
            query_match_start = min(consistent_query_times)
            query_match_end = max(consistent_query_times)
            
            _print_match_visualization(query_start, query_end, db_start, db_end,
                                     est_query_start_in_db, est_query_end_in_db,
                                     actual_match_start, actual_match_end,
                                     query_match_start, query_match_end, median_offset)
        else:
            _print_match_visualization(query_start, query_end, db_start, db_end, 
                                     est_query_start_in_db, est_query_end_in_db,
                                     offset=median_offset)
    else:
        _print_match_visualization(query_start, query_end, db_start, db_end, 
                                 est_query_start_in_db, est_query_end_in_db,
                                 offset=median_offset)


def _print_match_visualization(query_start: float, query_end: float,
                             db_start: float, db_end: float,
                             est_query_start_in_db: float = None, est_query_end_in_db: float = None,
                             actual_match_start: float = None, actual_match_end: float = None,
                             query_match_start: float = None, query_match_end: float = None,
                             offset: float = 0) -> None:
    """クエリとDBの対応関係を視覚化 - 実測データ優先、ない場合推定データ"""
    
    width = 60
    
    # 実測データがある場合は優先使用
    if (actual_match_start is not None and actual_match_end is not None and 
        query_match_start is not None and query_match_end is not None):
        print("   🎯 Audio Match Visualization (using measured data):")
        # 実測データを使用
        _print_accurate_visualization(query_start, query_end, db_start, db_end,
                                    actual_match_start, actual_match_end,
                                    query_match_start, query_match_end, width)
    else:
        print("   🎯 Audio Match Visualization (using estimated data):")
        # 推定データを使用
        _print_estimated_visualization(query_start, query_end, db_start, db_end,
                                     est_query_start_in_db, est_query_end_in_db,
                                     offset, width)


def _print_accurate_visualization(query_start: float, query_end: float,
                                db_start: float, db_end: float,
                                actual_match_start: float, actual_match_end: float,
                                query_match_start: float, query_match_end: float,
                                width: int) -> None:
    """実測データを使用した正確な視覚化"""
    # クエリ側の表示
    query_total_duration = query_end - query_start
    query_match_duration = query_match_end - query_match_start
    
    print(f"      Query Audio (total {query_total_duration:.0f}s) ✅ Measured:")
    
    query_timeline = ['-'] * width
    if query_total_duration > 0:
        # クエリでのマッチ開始・終了位置
        match_start_ratio = query_match_start / query_total_duration
        match_end_ratio = query_match_end / query_total_duration
        
        match_start_pos = max(0, int(width * match_start_ratio))
        match_end_pos = min(width-1, int(width * match_end_ratio))
        
        for i in range(match_start_pos, match_end_pos + 1):
            if 0 <= i < width:
                query_timeline[i] = '█'
    
    print(f"      |{''.join(query_timeline)}|")
    
    query_total_formatted = _format_time_mmss(query_total_duration)
    print(f"       0:00{' ' * (width-10)}{query_total_formatted}")
    print(f"       └─ Match: {_format_time_mmss(query_match_start)} - {_format_time_mmss(query_match_end)} ({query_match_duration:.0f}s)")
    
    # DB側の表示
    db_total_duration = db_end - db_start
    actual_match_duration = actual_match_end - actual_match_start
    
    print(f"       ↓ Matches DB at {actual_match_start/60:.0f}:{int(actual_match_start%60):02d}")
    print(f"      Database Audio (total {db_total_duration:.0f}s) ✅ Measured:")
    
    db_timeline = ['-'] * width
    if db_total_duration > 0:
        # DB内でのマッチ位置
        match_start_ratio = actual_match_start / db_total_duration
        match_end_ratio = actual_match_end / db_total_duration
        
        match_start_pos = max(0, int(width * match_start_ratio))
        match_end_pos = min(width-1, int(width * match_end_ratio))
        
        for i in range(match_start_pos, match_end_pos + 1):
            if 0 <= i < width:
                db_timeline[i] = '█'
    
    print(f"      |{''.join(db_timeline)}|")
    
    db_total_formatted = _format_time_mmss(db_total_duration)
    print(f"       0:00{' ' * (width-10)}{db_total_formatted}")
    print(f"       └─ Match: {_format_time_mmss(actual_match_start)} - {_format_time_mmss(actual_match_end)} ({actual_match_duration:.0f}s)")
    print("      📍 Legend:")
    print("         █ = Matching audio region (accurate position based on measured data)")
    print("         - = Non-matching audio")


def _print_estimated_visualization(query_start: float, query_end: float,
                                 db_start: float, db_end: float,
                                 est_query_start_in_db: float, est_query_end_in_db: float,
                                 offset: float, width: int) -> None:
    """推定データを使用した視覚化"""
    # Offsetが負の場合（consistent_matchesと同じロジック）
    if offset < 0:
        # 実際のマッチした範囲を計算
        actual_match_start_db = abs(offset)
        actual_match_end_db = actual_match_start_db + (query_end - query_start)
        
        # クエリ側のマッチ範囲（常に0から始まると仮定）
        query_match_start = 0.0
        query_match_end = query_end - query_start
        
        # クエリ全体の長さを推定（マッチした部分が全体のどの部分かを表示）
        query_total_duration = query_match_end * 1.6  # 推定：マッチ部分が全体の約60%
        
        print(f"      Query Audio (total ~{query_total_duration:.0f}s) ⚠️ Estimated:")
        
        # クエリのタイムライン表示 - 前半部分がマッチ
        query_timeline = ['-'] * width
        match_ratio = query_match_end / query_total_duration
        match_width = max(1, int(width * match_ratio))
        
        for i in range(match_width):
            if i < width:
                query_timeline[i] = '█'
        
        print(f"      |{''.join(query_timeline)}|")
        
        query_total_formatted = _format_time_mmss(query_total_duration)
        print(f"       0:00{' ' * (width-10)}{query_total_formatted}")
        print(f"       └─ Match: {_format_time_mmss(query_match_start)} - {_format_time_mmss(query_match_end)} ({query_match_end:.0f}s)")
        
        # DB側の表示
        print(f"       ↓ Query start matches DB at {_format_time_mmss(actual_match_start_db)}")
        
        # Database timeline - 全DB中のマッチ位置を表示
        db_duration = db_end - db_start
        print(f"      Database Audio (total {db_duration:.0f}s) ⚠️ Estimated:")
        
        db_timeline = ['-'] * width
        
        if db_duration > 0:
            # DBでのマッチ位置を計算
            match_start_pos = max(0, min(width-1, int(actual_match_start_db / db_duration * width)))
            match_end_pos = max(match_start_pos, min(width-1, int(actual_match_end_db / db_duration * width)))
            
            for i in range(match_start_pos, match_end_pos + 1):
                if 0 <= i < width:
                    db_timeline[i] = '█'
        
        print(f"      |{''.join(db_timeline)}|")
        
        db_total_formatted = _format_time_mmss(db_duration)
        print(f"       0:00{' ' * (width-10)}{db_total_formatted}")
        print(f"       └─ Match: {_format_time_mmss(actual_match_start_db)} - {_format_time_mmss(actual_match_end_db)}")
        
    else:
        # 正のオフセットの場合
        query_duration = query_end - query_start
        print(f"      Query Audio ({query_duration:.1f}s) ⚠️ Estimated:")
        query_bar = "█" * width
        print(f"      |{query_bar}|")
        
        query_total_formatted = _format_time_mmss(query_duration)
        print(f"       0:00{' ' * (width-10)}{query_total_formatted}")
        
        db_duration = db_end - db_start
        print(f"      Database Audio ({db_duration:.1f}s) ⚠️ Estimated:")
        db_timeline = ['-'] * width
        if est_query_end_in_db > db_start:
            end_pos = min(width-1, int((est_query_end_in_db - db_start) / db_duration * width))

            for i in range(0, end_pos + 1):
                if 0 <= i < width:
                    db_timeline[i] = '█'
        print(f"      |{''.join(db_timeline)}|")
        
        db_total_formatted = _format_time_mmss(db_duration)
        print(f"       0:00{' ' * (width-10)}{db_total_formatted}")
    
    print(f"      ⏰ Technical: Query matches DB at {_format_time_mmss(est_query_start_in_db)} - {_format_time_mmss(est_query_end_in_db)}")
    print("      📍 Legend:")
    print("         █ = Matching audio region (estimated position based on calculated data)")
    print("         - = Non-matching audio")
    print("      ⚠️  Note: Using estimated data, actual position may differ slightly")


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
                    'file_path': song.file_path
                },
                'confidence': match['confidence'],
                'match_count': match['match_count'],
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
  python video_search.py /path/to/video.mp4
  python video_search.py /path/to/video.mp4 --details
  python video_search.py /path/to/folder --database custom.db --details
  python video_search.py /path/to/audio.mp3 --verbose --details
  python video_search.py /path/to/folder --min-confidence 0.7 --details
  python video_search.py /path/to/video.mp4 --disable-adaptive --details
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
                logger.info("Run video_fingerprinter.py first to create a database")
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
            logger.info("Run video_fingerprinter.py first to add songs to the database")
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
