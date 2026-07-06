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
    create_mimizam_mariadb,
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
from .src.adaptive_parameters import AdaptiveParameterTuner,PerformanceMonitor
from .src.time_alignment import dominant_time_offset

# 映像系（video_fingerprinter/video_database/pip_detector）は opencv-contrib 等の
# 重い依存を必要とする。音声のみの利用で `import mimizam` が動画依存の欠落で落ちない
# よう、これらは PEP 562 の遅延インポート（初回アクセス時に解決）にする。
_LAZY_IMPORTS = {
    'VideoFingerprinter': '.src.video_fingerprinter',
    'VideoFingerprintConfig': '.src.video_fingerprinter',
    'FrameSelector': '.src.video_fingerprinter',
    'VLADEncoder': '.src.video_fingerprinter',
    'VideoFingerprint': '.src.video_fingerprinter',
    'normalize_frame': '.src.video_fingerprinter',
    'VideoFingerprintDatabase': '.src.video_database',
    'detect_pip_regions': '.src.pip_detector',
    'sample_frames_from_video': '.src.pip_detector',
    'PipRegion': '.src.pip_detector',
}


def __getattr__(name: str):
    """映像系シンボルを初回アクセス時に遅延インポートする（PEP 562）"""
    module_path = _LAZY_IMPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(module_path, __name__)
    value = getattr(module, name)
    globals()[name] = value  # 以降はキャッシュ済みの属性を参照
    return value


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY_IMPORTS.keys()))


__version__ = "1.0.3"

__all__ = [
    # メインAPI
    'Mimizam',
    'create_mimizam_sqlite',
    'create_mimizam_mysql',
    'create_mimizam_mariadb',
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
    'normalize_frame',
    
    # PiP検出
    'detect_pip_regions',
    'sample_frames_from_video',
    'PipRegion',
    
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
    'dominant_time_offset',
]
