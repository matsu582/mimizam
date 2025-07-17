"""
動画音声指紋生成ツール

指定されたフォルダ内の動画ファイルから音声を抽出し、
Shazam風アルゴリズムを使用して音声指紋を作成するスクリプト
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Tuple
import tempfile
import subprocess

# インストール済みのmimizamパッケージからインポート

from mimizam import (
        Mimizam, create_mimizam_sqlite, create_mimizam_mysql,
        create_mimizam_postgresql, create_mimizam_elasticsearch,
        DatabaseConfig
)

# サポートされている動画ファイル拡張子
VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
    '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts'
}

# サポートされている音声ファイル拡張子（既存の音声ファイルが存在する場合）
AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'
}


def setup_logging(verbose: bool = False):
    """ログ設定のセットアップ"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('video_fingerprinter.log')
        ]
    )


def create_mimizam_instance(args) -> Mimizam:
    """コマンドライン引数に基づいてMimizamインスタンスを作成する"""
    
    # 指紋生成器の設定を準備
    fingerprinter_config = {
        'enable_adaptive_params': determine_adaptive_setting(args),
        'audible_only': getattr(args, 'audible_only', False)
    }
    
    # matcher_configは指紋生成には不要だが、一貫性のためNoneを設定
    matcher_config = None
    
    # データベースタイプに基づいてMimizamインスタンスを作成
    if args.db_type == 'sqlite':
        return create_mimizam_sqlite(args.database, matcher_config, **fingerprinter_config)
    
    elif args.db_type == 'mysql':
        if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            raise ValueError("MySQL requires --db-host, --db-name, --db-user, and --db-password")
        return create_mimizam_mysql(
            host=args.db_host,
            port=args.db_port or 3306,
            database=args.db_name,
            username=args.db_user,
            password=args.db_password,
            matcher_config=matcher_config,
            **fingerprinter_config
        )
    
    elif args.db_type == 'postgresql':
        if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            raise ValueError("PostgreSQL requires --db-host, --db-name, --db-user, and --db-password")
        return create_mimizam_postgresql(
            host=args.db_host,
            port=args.db_port or 5432,
            database=args.db_name,
            username=args.db_user,
            password=args.db_password,
            matcher_config=matcher_config,
            **fingerprinter_config
        )
    
    elif args.db_type == 'elasticsearch':
        if not args.db_host:
            raise ValueError("Elasticsearch requires --db-host")
        return create_mimizam_elasticsearch(
            host=args.db_host,
            port=args.db_port or 9200,
            index_name=args.db_name or "video_fingerprints",
            matcher_config=matcher_config,
            **fingerprinter_config
        )
    
    else:
        raise ValueError(f"Unsupported database type: {args.db_type}")


def determine_adaptive_setting(args) -> bool:
    """コマンドライン引数から適応パラメータ設定を決定する"""
    # 優先順位: --no-adaptive > --enable-adaptive > デフォルト (True)
    if args.enable_adaptive and args.no_adaptive:
        logger = logging.getLogger(__name__)
        logger.warning("Both --enable-adaptive and --no-adaptive specified. Using --no-adaptive.")
        return False
    elif args.no_adaptive:
        return False
    elif args.enable_adaptive:
        return True
    else:
        return True  # デフォルトは有効


class VideoAudioExtractor:
    """ffmpegを使用して動画ファイルから音声を抽出する"""
    
    def __init__(self):
        self.temp_dir = None
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix='video_audio_')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
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


def find_media_files(folder_path: str) -> Tuple[List[str], List[str]]:
    """
    指定されたフォルダ内の動画および音声ファイルを検索する
    
    Args:
        folder_path: 検索するフォルダのパス
        
    Returns:
        (動画ファイル一覧, 音声ファイル一覧)のタプル
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    
    video_files = []
    audio_files = []
    
    for file_path in folder.rglob('*'):
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            if suffix in VIDEO_EXTENSIONS:
                video_files.append(str(file_path))
            elif suffix in AUDIO_EXTENSIONS:
                audio_files.append(str(file_path))
    
    return video_files, audio_files


def generate_song_id(file_path: str) -> str:
    """ファイルパスからユニークな楽曲IDを生成する"""
    return Path(file_path).stem.replace(' ', '_').lower()


def process_video_files(video_files: List[str], 
                       mimizam: Mimizam,
                       extractor: VideoAudioExtractor) -> int:
    """
    動画ファイルを処理し、音声指紋をデータベースに追加する
    
    Args:
        video_files: 動画ファイルパスの一覧
        mimizam: Mimizamインスタンス
        extractor: VideoAudioExtractorインスタンス
        
    Returns:
        正常に処理されたファイル数
    """
    logger = logging.getLogger(__name__)
    processed_count = 0
    
    for i, video_path in enumerate(video_files, 1):
        try:
            logger.info(f"Processing video {i}/{len(video_files)}: {Path(video_path).name}")
            
            # 動画から音声を抽出
            audio_path = extractor.extract_audio(video_path)
            
            # 楽曲メタデータを生成
            song_id = generate_song_id(video_path)
            title = Path(video_path).stem
            artist = "Unknown Artist"
            
            # Mimizamを使用して楽曲を追加
            result_song_id = mimizam.add_song(audio_path, title, artist, song_id)
            if result_song_id:
                logger.info(f"✅ Successfully added {title} to database (ID: {result_song_id})")
                processed_count += 1
            else:
                logger.error(f"❌ Failed to add {title} to database")
                
        except Exception as e:
            logger.error(f"❌ Error processing {video_path}: {e}")
            continue
    
    return processed_count


def process_audio_files(audio_files: List[str],
                       mimizam: Mimizam) -> int:
    """
    音声ファイルを処理し、指紋をデータベースに追加する
    
    Args:
        audio_files: 音声ファイルパスの一覧
        mimizam: Mimizamインスタンス
        
    Returns:
        正常に処理されたファイル数
    """
    logger = logging.getLogger(__name__)
    processed_count = 0
    
    for i, audio_path in enumerate(audio_files, 1):
        try:
            logger.info(f"Processing audio {i}/{len(audio_files)}: {Path(audio_path).name}")
            
            # 楽曲メタデータを生成
            song_id = generate_song_id(audio_path)
            title = Path(audio_path).stem
            artist = "Unknown Artist"
            
            # Mimizamを使用して楽曲を追加
            result_song_id = mimizam.add_song(audio_path, title, artist, song_id)
            if result_song_id:
                logger.info(f"✅ Successfully added {title} to database (ID: {result_song_id})")
                processed_count += 1
            else:
                logger.error(f"❌ Failed to add {title} to database")
                
        except Exception as e:
            logger.error(f"❌ Error processing {audio_path}: {e}")
            continue
    
    return processed_count


def initialize_fingerprinter(args) -> Mimizam:
    """設定ログと共にMimizamインスタンスを初期化する"""
    logger = logging.getLogger(__name__)
    
    logger.info("Initializing Mimizam system...")
    
    # Mimizamインスタンスを作成して返す
    mimizam = create_mimizam_instance(args)
    
    # 設定をログ出力
    enable_adaptive = determine_adaptive_setting(args)
    logger.info(f"Adaptive parameters: {'ON' if enable_adaptive else 'OFF'}")
    
    return mimizam


def process_all_files(video_files: List[str], audio_files: List[str], 
                     mimizam: Mimizam) -> int:
    """すべての動画および音声ファイルを処理する"""
    logger = logging.getLogger(__name__)
    total_processed = 0
    
    # 動画ファイルを処理
    if video_files:
        logger.info(f"Processing {len(video_files)} video files...")
        with VideoAudioExtractor() as extractor:
            processed = process_video_files(video_files, mimizam, extractor)
            total_processed += processed
            logger.info(f"Processed {processed}/{len(video_files)} video files")
    
    # 音声ファイルを処理
    if audio_files:
        logger.info(f"Processing {len(audio_files)} audio files...")
        processed = process_audio_files(audio_files, mimizam)
        total_processed += processed
        logger.info(f"Processed {processed}/{len(audio_files)} audio files")
    
    return total_processed


def show_performance_summary(mimizam: Mimizam) -> None:
    """監視が有効な場合にパフォーマンスサマリーを表示する"""
    logger = logging.getLogger(__name__)
    
    if hasattr(mimizam.fingerprinter, 'performance_monitor') and mimizam.fingerprinter.performance_monitor:
        logger.info("Performance Summary:")
        try:
            summary = mimizam.fingerprinter.performance_monitor.get_performance_summary()
            for line in summary.split('\n'):
                if line.strip():
                    logger.info(f"  {line}")
        except Exception as e:
            logger.debug(f"Could not get performance summary: {e}")


def setup_logging(verbose: bool = False) -> None:
    """ログ設定のセットアップ"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('video_fingerprinter.log')
        ]
    )


def validate_and_get_media_files(args) -> Tuple[List[str], List[str]]:
    """パスを検証してメディアファイルを取得する"""
    logger = logging.getLogger(__name__)
    
    if not os.path.exists(args.folder):
        logger.error(f"Path not found: {args.folder}")
        raise FileNotFoundError(f"Path not found: {args.folder}")

    target_path = Path(args.folder)
    
    # ファイル指定時はそのファイルのみ処理
    if target_path.is_file():
        suffix = target_path.suffix.lower()
        video_files, audio_files = [], []
        if suffix in VIDEO_EXTENSIONS:
            video_files = [str(target_path)]
        elif suffix in AUDIO_EXTENSIONS:
            audio_files = [str(target_path)]
        else:
            logger.error(f"Unsupported file type: {suffix}")
            raise ValueError(f"Unsupported file type: {suffix}")
    else:
        # フォルダの場合は従来通り
        logger.info(f"Searching for media files in: {args.folder}")
        video_files, audio_files = find_media_files(args.folder)

    logger.info(f"Found {len(video_files)} video files")
    logger.info(f"Found {len(audio_files)} audio files")
    
    return video_files, audio_files


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Extract audio from video files and create audio fingerprints',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python video_fingerprinter.py /path/to/videos
  python video_fingerprinter.py /path/to/videos --database custom.db
  python video_fingerprinter.py /path/to/videos --recursive --verbose
  python video_fingerprinter.py /path/to/videos --no-adaptive --verbose
  python video_fingerprinter.py /path/to/videos --no-adaptive
        """
    )
    
    parser.add_argument(
        'folder',
        help='Path to folder containing video files'
    )
    
    parser.add_argument(
        '--database', '-d',
        default='video_fingerprints.db',
        help='Path to SQLite database file (default: video_fingerprints.db)'
    )
    
    parser.add_argument(
        '--db-type',
        choices=['sqlite', 'mysql', 'postgresql', 'elasticsearch'],
        default='sqlite',
        help='Database backend type (default: sqlite)'
    )
    
    parser.add_argument(
        '--db-host',
        help='Database host (for MySQL/PostgreSQL/Elasticsearch)'
    )
    
    parser.add_argument(
        '--db-port',
        type=int,
        help='Database port'
    )
    
    parser.add_argument(
        '--db-name',
        help='Database name (for MySQL/PostgreSQL) or index name (for Elasticsearch)'
    )
    
    parser.add_argument(
        '--db-user',
        help='Database username'
    )
    
    parser.add_argument(
        '--db-password',
        help='Database password'
    )
    
    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Search subfolders recursively (enabled by default)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--enable-adaptive',
        action='store_true',
        help='Enable adaptive parameter tuning'
    )
    
    parser.add_argument(
        '--no-adaptive',
        action='store_true',
        help='Disable adaptive parameter tuning (deprecated, use --enable-adaptive instead)'
    )

    parser.add_argument(
        '--audible-only',
        action='store_true',
        help='Use only audible frequency range (20Hz-20kHz) for fingerprinting'
    )
    
    
    
    parser.add_argument(
        '--list-only',
        action='store_true',
        help='Only list found files without processing'
    )
    
    args = parser.parse_args()
    
    # ログの設定
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        video_files, audio_files = validate_and_get_media_files(args)

        if args.list_only:
            print("\nVideo files:")
            for video in video_files:
                print(f"  {video}")
            print("\nAudio files:")
            for audio in audio_files:
                print(f"  {audio}")
            return 0

        if len(video_files) == 0 and len(audio_files) == 0:
            logger.warning("No media files found!")
            return 0

        # Mimizamシステムを初期化
        mimizam = initialize_fingerprinter(args)

        # 初期データベース統計を表示
        stats = mimizam.get_database_stats()
        logger.info(f"Database stats - Songs: {stats['songs']}, Fingerprints: {stats['fingerprints']}")

        total_processed = 0

        # すべてのファイルを処理
        total_processed = process_all_files(video_files, audio_files, mimizam)

        # 最終データベース統計を表示
        stats = mimizam.get_database_stats()
        logger.info(f"Final database stats - Songs: {stats['songs']}, Fingerprints: {stats['fingerprints']}")

        # パフォーマンスサマリーを表示
        show_performance_summary(mimizam)

        logger.info(f"✅ Successfully processed {total_processed} files")

        # タイプに基づいてデータベースの場所を表示
        if mimizam.database.config.backend == 'sqlite':
            logger.info(f"Database saved to: {mimizam.database.config.file_path}")
        else:
            logger.info(f"Data saved to {mimizam.database.config.backend} database: {mimizam.database.config.host}:{mimizam.database.config.port}")

        return 0

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
