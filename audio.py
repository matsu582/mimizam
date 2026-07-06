"""
mimizam.audio - 音声指紋のサブパッケージ名前空間

音声指紋に関わる公開シンボルのみを再エクスポートする。動画依存
（opencv-contrib 等）を一切読み込まないため、`import mimizam.audio` は
音声のみ利用の依存境界を明確にする。既存の `import mimizam` からの利用も
引き続き可能（後方互換）。
"""

from .src.audio_fingerprinter import (
    AudioFingerprinter,
    Peak,
    SpectrogramAnalyzer,
    HashGenerator,
)
from .src.fingerprint_database import (
    FingerprintDatabase,
    FingerprintMatcher,
    create_sqlite_config,
    create_mysql_config,
    create_postgresql_config,
    create_elasticsearch_config,
)
from .src.database_base import DatabaseConfig, Song, Fingerprint
from .src.adaptive_parameters import AdaptiveParameterTuner, PerformanceMonitor
from .src.time_alignment import dominant_time_offset

__all__ = [
    "AudioFingerprinter",
    "Peak",
    "SpectrogramAnalyzer",
    "HashGenerator",
    "FingerprintDatabase",
    "FingerprintMatcher",
    "DatabaseConfig",
    "Song",
    "Fingerprint",
    "create_sqlite_config",
    "create_mysql_config",
    "create_postgresql_config",
    "create_elasticsearch_config",
    "AdaptiveParameterTuner",
    "PerformanceMonitor",
    "dominant_time_offset",
]
