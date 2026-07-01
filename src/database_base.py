"""
データベースバックエンドの基底クラスとデータ構造

音声指紋用データベースの共通インターフェースを定義
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
import logging
from dataclasses import dataclass


@dataclass
class Fingerprint:
    """音声フィンガープリントハッシュを表現"""
    hash_value: str
    time_offset: float
    song_id: Optional[str] = None


@dataclass
class Song:
    """データベース内の楽曲を表現"""
    id: str
    title: str
    artist: str
    file_path: str
    meta: Optional[dict] = None 
    created_at: Optional[str] = None


@dataclass
class Video:
    """データベース内の映像を表現"""
    id: str
    title: str
    file_path: str
    duration: Optional[float] = None
    frame_count: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class DatabaseConfig:
    """データベース接続設定"""
    backend: str  # 'sqlite', 'mysql', 'postgres', 'elasticsearch'
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    file_path: Optional[str] = None  # SQLite用
    
    # Elasticsearch固有の設定
    index_name: Optional[str] = None
    ca_certs: Optional[str] = None
    verify_certs: bool = True
    
    # Elasticsearchインデックス設定
    es_songs_shards: int = 1
    es_songs_replicas: int = 0
    es_fingerprints_shards: int = 3
    es_fingerprints_replicas: int = 0
    
    # 接続プール設定
    pool_size: int = 5
    pool_timeout: int = 30


class DatabaseBackend(ABC):
    """
    データベースバックエンドの抽象基底クラス
    
    エラーハンドリング契約:
    - CRUD操作メソッド (connect, create_tables, add_song, add_fingerprints, delete_song): 
      成功時True、失敗時False を返す。例外は投げない。
    - クエリメソッド (search_fingerprints, get_song, list_songs, get_database_stats, get_fingerprints_by_song):
      成功時は適切なデータを返す。致命的エラー時は例外を投げる可能性がある。
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    
    @abstractmethod
    def connect(self) -> bool:
        """
        データベースに接続
        
        Returns:
            成功時True、失敗時False。例外は投げない。
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """データベースから切断"""
        pass
    
    @abstractmethod
    def create_tables(self) -> bool:
        """
        必要なテーブル/インデックスを作成
        
        Returns:
            成功時True、失敗時False。例外は投げない。
        """
        pass
    
    @abstractmethod
    def add_song(self, song: Song) -> bool:
        """
        楽曲を追加
        
        Returns:
            成功時True、失敗時False。例外は投げない。
        """
        pass
    
    @abstractmethod
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """
        フィンガープリントを追加
        
        Returns:
            成功時True、失敗時False。例外は投げない。
        """
        pass
    
    @abstractmethod
    def delete_song(self, song_id: str) -> bool:
        """
        楽曲を削除
        
        Returns:
            成功時True、失敗時False。例外は投げない。
        """
        pass
    
    @abstractmethod
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """フィンガープリントを検索。致命的エラー時は例外を投げる可能性がある。"""
        pass
    
    @abstractmethod
    def get_song(self, song_id: str) -> Optional[Song]:
        """楽曲情報を取得。致命的エラー時は例外を投げる可能性がある。"""
        pass
    
    @abstractmethod
    def list_songs(self) -> List[Song]:
        """全楽曲をリスト表示。致命的エラー時は例外を投げる可能性がある。"""
        pass
    
    @abstractmethod
    def get_database_stats(self) -> Dict[str, int]:
        """データベース統計を取得。致命的エラー時は例外を投げる可能性がある。"""
        pass

    @abstractmethod
    def get_fingerprints_by_song(self, song_id: str) -> List[Fingerprint]:
        """指定した楽曲のフィンガープリントを取得。致命的エラー時は例外を投げる可能性がある。"""
        pass

    # ===== 映像指紋メソッド =====
    # デフォルト実装はNotImplementedError。各バックエンドで上書きして使用。

    def add_video(self, video: 'Video') -> bool:
        """映像メタデータを追加"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def add_video_fingerprint(
        self, video_id: str, fingerprint: bytes, dimensions: int,
        descriptor_count: int = 0
    ) -> bool:
        """映像全体指紋を保存（fingerprintはfloat32のバイト列）"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]]
    ) -> bool:
        """フレーム単位指紋を一括保存（各要素は(frame_index, timestamp, fp_bytes)）"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def search_video_fingerprints(
        self, query_fp: bytes, dimensions: int, top_k: int = 10,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """映像全体指紋で候補検索"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def get_frame_fingerprints(
        self, video_id: str
    ) -> List[Tuple[int, float, bytes]]:
        """指定映像のフレーム指紋を取得"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def get_video(self, video_id: str) -> Optional['Video']:
        """映像情報を取得"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def list_videos(self) -> List['Video']:
        """全映像をリスト取得"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def delete_video(self, video_id: str) -> bool:
        """映像と関連指紋を削除"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")

    def get_video_stats(self) -> Dict[str, int]:
        """映像指紋の統計を取得"""
        raise NotImplementedError("このバックエンドは映像指紋に未対応です")


# エクスポートするシンボルを定義
__all__ = [
    'Fingerprint',
    'Song',
    'Video',
    'DatabaseConfig',
    'DatabaseBackend'
]
