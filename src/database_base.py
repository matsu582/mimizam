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
    - エラーログは必ず self._log_error() を使用して統一的に出力する。
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def _log_error(self, operation: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """
        統一されたエラーログ出力
        
        Args:
            operation: 実行していた操作名 (例: "MySQL connection", "table creation")
            error: 発生した例外
            context: 追加のコンテキスト情報
        """
        error_msg = f"{operation} error: {error}"
        if context:
            error_msg += f" | Context: {context}"
        self.logger.error(error_msg)
    
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


# エクスポートするシンボルを定義
__all__ = [
    'Fingerprint',
    'Song',
    'DatabaseConfig',
    'DatabaseBackend'
]
