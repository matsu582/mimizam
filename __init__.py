"""
mimizam - 音声・映像指紋システム

Shazam風音声指紋 + AKAZE/VLAD/PCAベースの映像指紋を提供。
音声・映像の指紋を生成してデータベースと照合することで、
メディアを識別します。

主要コンポーネント:
- AudioFingerprinter: 音声指紋生成
- VideoFingerprinter: 映像指紋生成
- FingerprintDatabase: データベース管理
- FingerprintMatcher: 音声マッチング
"""

# すべてのパブリックAPIをsrcから再エクスポート
from .src.mimizam import (
    Mimizam,
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch
)

from .src.audio_fingerprinter import AudioFingerprinter, Peak, SpectrogramAnalyzer, HashGenerator
from .src.fingerprint_database import (
    FingerprintDatabase, 
    FingerprintMatcher, 
    create_sqlite_config, 
    create_mysql_config, 
    create_postgresql_config, 
    create_elasticsearch_config
)
from .src.database_base import DatabaseConfig, Song, Fingerprint, Video
from .src.video_fingerprinter import (
    VideoFingerprinter,
    VideoFingerprintConfig,
    FrameSelector,
    VLADEncoder,
    VideoFingerprint,
)
from .src.video_database import VideoFingerprintDatabase
from .src.adaptive_parameters import AdaptiveParameterTuner,PerformanceMonitor

__version__ = "1.0.3"

__all__ = [
    # メインAPI
    'Mimizam',
    'create_mimizam_sqlite',
    'create_mimizam_mysql',
    'create_mimizam_postgresql',
    'create_mimizam_elasticsearch',
    
    # 音声フィンガープリンティング
    'AudioFingerprinter',
    'Fingerprint',
    'Peak',
    'SpectrogramAnalyzer',
    'HashGenerator',
    
    # 映像フィンガープリンティング
    'VideoFingerprinter',
    'VideoFingerprintConfig',
    'FrameSelector',
    'VLADEncoder',
    'VideoFingerprint',
    'VideoFingerprintDatabase',
    'Video',
    
    # データベース
    'FingerprintDatabase',
    'FingerprintMatcher',
    'Song',
    'DatabaseConfig',
    'create_sqlite_config', 
    'create_mysql_config', 
    'create_postgresql_config', 
    'create_elasticsearch_config',
    
    # 高度な機能
    'AdaptiveParameterTuner',
    'PerformanceMonitor',
]
