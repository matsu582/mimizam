"""
mimizam.video - 映像指紋のサブパッケージ名前空間

映像指紋に関わる公開シンボルのみを再エクスポートする。このモジュールの
import 時点で opencv-contrib 等の映像依存を読み込むため、依存境界が明確になる
（音声のみ利用では `mimizam.audio` を使えば映像依存を読み込まない）。
"""

from .src.video_fingerprinter import (
    VideoFingerprinter,
    VideoFingerprintConfig,
    FrameSelector,
    VLADEncoder,
    VideoFingerprint,
    normalize_frame,
)
from .src.video_database import VideoFingerprintDatabase
from .src.pip_detector import (
    detect_pip_regions,
    sample_frames_from_video,
    PipRegion,
)
from .src.database_base import Video

__all__ = [
    "VideoFingerprinter",
    "VideoFingerprintConfig",
    "FrameSelector",
    "VLADEncoder",
    "VideoFingerprint",
    "normalize_frame",
    "VideoFingerprintDatabase",
    "detect_pip_regions",
    "sample_frames_from_video",
    "PipRegion",
    "Video",
]
