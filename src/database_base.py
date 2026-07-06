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
    hash_value: int
    time_offset: float
    song_id: Optional[str] = None


def group_query_times(
    query_fingerprints: List['Fingerprint'],
) -> Dict[int, List[float]]:
    """クエリ指紋を hash_value -> query_time群 に集約する

    同一ハッシュが複数のquery_timeに現れる多重度を保持するためのヘルパ。
    dict(``{hash: time}``)化すると最後の1件しか残らず、match_count・
    時間整列・信頼度が歪むため、各ハッシュに紐づく全query_timeをリストで
    保持する。DB検索側はこのキー集合(distinctなハッシュ)で候補を引き、
    返り行ごとに該当する全query_timeへ展開して多重度を復元する。

    Args:
        query_fingerprints: クエリフィンガープリントのリスト

    Returns:
        hash_value をキー、query_time(float)のリストを値とする辞書
    """
    grouped: Dict[int, List[float]] = {}
    for fp in query_fingerprints:
        grouped.setdefault(fp.hash_value, []).append(float(fp.time_offset))
    return grouped


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
        raise NotImplementedError("This backend does not support video fingerprinting")

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]]
    ) -> bool:
        """フレーム単位指紋を一括保存（各要素は(frame_index, timestamp, fp_bytes)）"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームのANN近傍から映像別の得票・類似度を集計

        戻り値: {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        raise NotImplementedError("This backend does not support video fingerprinting")

    def get_frame_fingerprints(
        self, video_id: str
    ) -> List[Tuple[int, float, bytes]]:
        """指定映像のフレーム指紋を取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def get_frame_fingerprints_batch(
        self, video_ids: List[str]
    ) -> Dict[str, List[Tuple[int, float, bytes]]]:
        """複数映像のフレーム指紋をまとめて取得

        デフォルトは個別取得へのフォールバック。
        リモートDBのバックエンドは1クエリ実装でオーバーライドする。
        """
        return {
            vid: self.get_frame_fingerprints(vid)
            for vid in video_ids
        }

    def get_video(self, video_id: str) -> Optional['Video']:
        """映像情報を取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def list_videos(self) -> List['Video']:
        """全映像をリスト取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def delete_video(self, video_id: str) -> bool:
        """映像と関連指紋を削除"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def add_frame_descriptors(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes, int]],
    ) -> bool:
        """フレーム単位AKAZE記述子を保存（再生成用）"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def get_frame_descriptors(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes, int]]:
        """指定映像のフレーム記述子を取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, bytes, int]]]:
        """全映像のフレーム記述子を取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")

    def get_video_stats(self) -> Dict[str, int]:
        """映像指紋の統計を取得"""
        raise NotImplementedError("This backend does not support video fingerprinting")


# エクスポートするシンボルを定義
__all__ = [
    'Fingerprint',
    'Song',
    'Video',
    'DatabaseConfig',
    'DatabaseBackend',
    'group_query_times',
]
