"""Elasticsearchデータベースバックエンド実装

シャード数・レプリカ数の推奨設定:

【楽曲インデックス (songs)】
- 小規模 (1万曲未満): shards=1, replicas=0
- 中規模 (1-10万曲): shards=2, replicas=1  
- 大規模 (10万曲以上): shards=3-5, replicas=1-2

【フィンガープリントインデックス (fingerprints)】
- 小規模 (100万FP未満): shards=2, replicas=0
- 中規模 (100万-1000万FP): shards=3-5, replicas=1
- 大規模 (1000万FP以上): shards=5-10, replicas=1-2

【本番環境での推奨事項】
- レプリカ数は少なくとも1以上（可用性のため）
- シャード数はノード数を考慮して設定
- パフォーマンスと可用性のバランスを考慮
"""

from typing import List, Optional, Dict, Tuple
from datetime import datetime
import traceback
from ..database_base import DatabaseBackend, DatabaseConfig, Song, Fingerprint
from ..exceptions import ConnectionError, QueryError, log_and_raise

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import TransportError as ElasticsearchException
    from elasticsearch.helpers import bulk
    ELASTICSEARCH_AVAILABLE = True
except ImportError as e:
    Elasticsearch = None
    ElasticsearchException = Exception
    ELASTICSEARCH_AVAILABLE = False


class ElasticsearchBackend(DatabaseBackend):
    """Elasticsearchデータベースバックエンド"""
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.client = None
        self.songs_index = f"{config.index_name or 'fingerprints'}_songs"
        self.fingerprints_index = f"{config.index_name or 'fingerprints'}_fingerprints"
    
    def connect(self) -> bool:
        """Elasticsearchクラスターに接続"""
        try:
            if not ELASTICSEARCH_AVAILABLE or Elasticsearch is None:
                self.logger.error("elasticsearch module is not available")
                return False
            
            # 接続設定を構築（パフォーマンス最適化）
            hosts = [f"http://{self.config.host}:{self.config.port or 9200}"]
            
            es_config = {
                'hosts': hosts,
                'request_timeout': self.config.pool_timeout or 300,  # タイムアウトを大幅延長
                'verify_certs': getattr(self.config, 'verify_certs', True),
                # 接続プール最適化（Elasticsearch 8.x対応）
                'connections_per_node': self.config.pool_size or 25,  # maxsizeの代替
                'retry_on_timeout': True,
                'max_retries': 3,
                'retry_on_status': [502, 503, 504],
                # HTTP Keep-Alive最適化
                'http_compress': True,  # HTTP圧縮有効化
                'headers': {
                    'Connection': 'keep-alive',
                    'Keep-Alive': 'timeout=300, max=1000'
                }
            }
            
            # 認証設定
            if self.config.username and self.config.password:
                es_config['basic_auth'] = (self.config.username, self.config.password)
            
            # SSL設定（HTTPS URLを使用）
            if self.config.ca_certs:
                hosts = [f"https://{self.config.host}:{self.config.port or 9200}"]
                es_config['hosts'] = hosts
                es_config['ca_certs'] = self.config.ca_certs
            
            self.client = Elasticsearch(**es_config)
            self.logger.info(f"Elasticsearch client created: {es_config}")
            
            # 接続テスト
            self.logger.info("Pinging Elasticsearch cluster...")
            if self.client.ping():
                self.logger.info(f"Connected to Elasticsearch cluster: {self.config.host}:{self.config.port}")
                
                # クラスター設定の最適化（Elasticsearch 8.x対応 - 最小限設定のみ）
                try:
                    # 基本的な接続テストのみ
                    cluster_health = self.client.cluster.health()
                    self.logger.info(f"Elasticsearch cluster health: {cluster_health.get('status', 'unknown')}")
                except Exception as optimize_error:
                    self.logger.warning(f"Elasticsearch connection test error: {optimize_error}")
                
                return True
            else:
                self.logger.error("Failed to connect to Elasticsearch cluster")
                return False
                
        except Exception as e:
            self.logger.error(f"Elasticsearch connection error: {e}", extra={"host": self.config.host, "port": self.config.port})
            return False
    
    def disconnect(self) -> None:
        """Elasticsearchクラスターから切断"""
        if self.client:
            self.client.close()
            self.client = None
    
    def create_tables(self) -> bool:
        """Elasticsearchインデックスを作成（Elasticsearch 8.x最適化版）"""
        try:
            # 楽曲インデックスのマッピング
            songs_mapping = {
                "settings": {
                    "number_of_shards": self.config.es_songs_shards,
                    "number_of_replicas": self.config.es_songs_replicas,
                    "refresh_interval": "30s"
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "title": {
                            "type": "text", 
                            "analyzer": "standard",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256
                                }
                            }
                        },
                        "artist": {
                            "type": "text", 
                            "analyzer": "standard",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256
                                }
                            }
                        },
                        "file_path": {"type": "keyword"},
                        "meta": {"type": "object", "enabled": True},
                        "created_at": {"type": "date"}
                    }
                }
            }
            
            # フィンガープリントインデックスのマッピング
            fingerprints_mapping = {
                "settings": {
                    "number_of_shards": self.config.es_fingerprints_shards,
                    "number_of_replicas": self.config.es_fingerprints_replicas,
                    "refresh_interval": "30s",
                    "index": {
                        "max_result_window": 100000
                    }
                },
                "mappings": {
                    "properties": {
                        "song_id": {
                            "type": "keyword",
                            "doc_values": True
                        },
                        "hash_value": {
                            "type": "keyword",
                            "index": True
                        },
                        "time_offset": {
                            "type": "double",
                            "doc_values": True
                        },
                        "created_at": {"type": "date"}
                    }
                }
            }
            
            # インデックスを作成（存在しない場合のみ）
            if not self.client.indices.exists(index=self.songs_index):
                self.client.indices.create(index=self.songs_index, body=songs_mapping)
                self.logger.info(f"Created songs index (shards: {self.config.es_songs_shards}, replicas: {self.config.es_songs_replicas}): {self.songs_index}")
            
            if not self.client.indices.exists(index=self.fingerprints_index):
                self.client.indices.create(index=self.fingerprints_index, body=fingerprints_mapping)
                self.logger.info(f"Created fingerprints index (shards: {self.config.es_fingerprints_shards}, replicas: {self.config.es_fingerprints_replicas}): {self.fingerprints_index}")
            
            return True
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch index creation error: {e}")
            return False
    
    def add_song(self, song: Song) -> bool:
        """Elasticsearchに楽曲を追加"""
        try:
            song_doc = {
                "id": song.id,
                "title": song.title,
                "artist": song.artist,
                "file_path": song.file_path,
                "meta": song.meta if song.meta else None,
                "created_at": datetime.now().isoformat()
            }
            
            # タイムアウトを延長した操作
            response = self.client.index(
                index=self.songs_index,
                id=song.id,
                body=song_doc,
                refresh=False,  # リフレッシュを無効化してパフォーマンス向上
                timeout='60s'  # タイムアウト延長
            )
            
            # レスポンスの確認
            if response.get('result') in ['created', 'updated']:
                return True
            else:
                self.logger.warning(f"Song addition response has unexpected value: {response}")
                return False
                
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch song addition error: {e}")
            return False
    
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """Elasticsearchにフィンガープリントを追加"""
        try:
            # 既存フィンガープリントを削除
            delete_query = {
                "query": {
                    "term": {"song_id": song_id}
                }
            }
            self.client.delete_by_query(index=self.fingerprints_index, body=delete_query)
            
            # 新しいフィンガープリントを一括追加（従来型バルク）
            
            actions = []
            current_time = datetime.now().isoformat()
            
            for fp in fingerprints:
                action = {
                    "_index": self.fingerprints_index,
                    "_source": {
                        "song_id": song_id,
                        "hash_value": fp.hash_value,
                        "time_offset": float(fp.time_offset),
                        "created_at": current_time
                    }
                }
                actions.append(action)
            
            # バルクインデックス実行
            if actions:
                _, failed = bulk(
                    self.client, 
                    actions,
                    chunk_size=5000,
                    refresh=False  # 非同期リフレッシュでパフォーマンス向上
                )
                
                if failed:
                    self.logger.error(f"Bulk index failed: {len(failed)} items")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Elasticsearch fingerprint addition error: {e}")
            return False

    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """Elasticsearchでフィンガープリントを検索"""
        matches = {}

        if not query_fingerprints:
            return matches

        try:
            # 検索前にインデックスを明示的にリフレッシュ（最新データを確実に反映）
            try:
                self.client.indices.refresh(index=self.fingerprints_index)
            except ElasticsearchException:
                pass  # リフレッシュエラーは無視
            
            # ハッシュ値のリストを作成
            hash_values = [fp.hash_value for fp in query_fingerprints]
            hash_to_time = {fp.hash_value: float(fp.time_offset) for fp in query_fingerprints}
            
            # Elasticsearch専用高性能検索クエリ
            search_body = {
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "terms": {
                                    "hash_value": hash_values,
                                    "boost": 1.0
                                }
                            }
                        ]
                    }
                },
                "_source": ["song_id", "hash_value", "time_offset"],
                "size": 50000,  # 大量結果対応
                "sort": [
                    {"song_id": {"order": "asc"}},  # ソート最適化
                    {"time_offset": {"order": "asc"}}
                ],
                "track_total_hits": False,  # カウント無効化で高速化
                "timeout": "30s"  # タイムアウト設定
            }
            
            # バッチサイズによる分割検索（Elasticsearchの制限対応）
            batch_size = 10000  # terms クエリの最大サイズ制限対応
            
            for i in range(0, len(hash_values), batch_size):
                batch_hash_values = hash_values[i:i + batch_size]
                
                # バッチ用クエリを作成
                batch_search_body = search_body.copy()
                batch_search_body["query"]["bool"]["filter"][0]["terms"]["hash_value"] = batch_hash_values
                
                try:
                    # 検索実行
                    result = self.client.search(
                        index=self.fingerprints_index,
                        body=batch_search_body,
                        preference="_local",  # ローカルシャード優先
                        request_cache=True,  # リクエストキャッシュ有効化
                        allow_partial_search_results=False  # 部分結果無効化
                    )
                    
                    # 結果処理
                    for hit in result['hits']['hits']:
                        source = hit['_source']
                        hash_value = source['hash_value']
                        song_id = source['song_id']
                        db_time_offset = source['time_offset']
                        
                        if hash_value in hash_to_time:
                            query_time_offset = hash_to_time[hash_value]
                            
                            if song_id not in matches:
                                matches[song_id] = []
                            matches[song_id].append((float(query_time_offset), float(db_time_offset)))
                            
                except ElasticsearchException as batch_error:
                    self.logger.warning(f"Elasticsearch batch search error (batch {i//batch_size + 1}): {batch_error}")
                    continue
                        
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch fingerprint search error: {e}")
        
        return matches
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """Elasticsearchから楽曲情報を取得"""
        try:
            # 検索前にインデックスを明示的にリフレッシュ（最新データを確実に反映）
            try:
                self.client.indices.refresh(index=self.songs_index)
            except ElasticsearchException:
                pass  # リフレッシュエラーは無視
            
            result = self.client.get(index=self.songs_index, id=song_id)
            source = result['_source']
            meta = source.get('meta') if 'meta' in source else None
            return Song(
                id=source['id'],
                title=source['title'],
                artist=source['artist'],
                file_path=source['file_path'],
                meta=meta,
                created_at=source.get('created_at')
            )
        except ElasticsearchException as e:
            if "not_found" not in str(e).lower():
                self.logger.error(f"Elasticsearch song retrieval error: {e}")
        
        return None
    
    def list_songs(self) -> List[Song]:
        """Elasticsearchから全楽曲をリスト表示"""
        songs = []
        try:
            # 検索前にインデックスを明示的にリフレッシュ（最新データを確実に反映）
            try:
                self.client.indices.refresh(index=self.songs_index)
            except ElasticsearchException:
                pass  # リフレッシュエラーは無視
            
            result = self.client.search(
                index=self.songs_index,
                query={"match_all": {}},
                sort=[
                    {"title.keyword": {"order": "asc"}},
                    {"artist.keyword": {"order": "asc"}}
                ],
                size=10000
            )
            
            for hit in result['hits']['hits']:
                source = hit['_source']
                meta = source.get('meta') if 'meta' in source else None
                songs.append(Song(
                    id=source['id'],
                    title=source['title'],
                    artist=source['artist'],
                    file_path=source['file_path'],
                    meta=meta,
                    created_at=source.get('created_at')
                ))
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch song list retrieval error: {e}")
        
        return songs
    
    def get_database_stats(self) -> Dict[str, int]:
        """Elasticsearchデータベース統計を取得"""
        stats = {"songs": 0, "fingerprints": 0}
        
        try:
            # インデックスを明示的にリフレッシュ（最新データを確実に反映）
            try:
                self.client.indices.refresh(index=self.songs_index)
                self.client.indices.refresh(index=self.fingerprints_index)
            except ElasticsearchException:
                pass  # リフレッシュエラーは無視
            
            # 楽曲数を取得
            songs_count = self.client.count(index=self.songs_index)
            stats["songs"] = songs_count['count']
            
            # フィンガープリント数を取得
            fingerprints_count = self.client.count(index=self.fingerprints_index)
            stats["fingerprints"] = fingerprints_count['count']
            
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch statistics retrieval error: {e}")
        
        return stats
    
    def delete_song(self, song_id: str) -> bool:
        """Elasticsearchから楽曲を削除"""
        try:
            # 楽曲を削除
            self.client.delete(index=self.songs_index, id=song_id)
            
            # 関連するフィンガープリントを削除
            delete_query = {
                "query": {
                    "term": {"song_id": song_id}
                }
            }
            self.client.delete_by_query(index=self.fingerprints_index, body=delete_query)
            
            return True
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch song deletion error: {e}")
            return False

    def get_fingerprints_by_song(self, song_id: str) -> List[Fingerprint]:
        """指定した楽曲のフィンガープリントを取得"""
        fingerprints = []
        
        try:
            # 楽曲に関連するフィンガープリントを検索（最適化クエリ）
            search_query = {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"song_id": song_id}}
                        ]
                    }
                },
                "_source": ["hash_value", "time_offset"],
                "size": 50000,  # 大量のフィンガープリントに対応
                "sort": [{"time_offset": {"order": "asc"}}],  # 時間順ソート最適化
                "track_total_hits": False,  # カウント無効化で高速化
                "timeout": "30s"
            }
            
            # スクロール検索で大量データ対応
            response = self.client.search(
                index=self.fingerprints_index, 
                body=search_query,
                scroll='2m',  # スクロールタイムアウト
                preference="_local",  # ローカルシャード優先
                request_cache=True  # キャッシュ有効化
            )
            
            scroll_id = response['_scroll_id']
            
            # 初回結果を処理
            for hit in response['hits']['hits']:
                source = hit['_source']
                fp = Fingerprint(
                    hash_value=source['hash_value'],
                    time_offset=float(source['time_offset']),
                    song_id=song_id
                )
                fingerprints.append(fp)
            
            # スクロールで残りの結果を取得
            while len(response['hits']['hits']) > 0:
                try:
                    response = self.client.scroll(
                        scroll_id=scroll_id,
                        scroll='2m'
                    )
                    
                    if not response['hits']['hits']:
                        break
                        
                    for hit in response['hits']['hits']:
                        source = hit['_source']
                        fp = Fingerprint(
                            hash_value=source['hash_value'],
                            time_offset=float(source['time_offset']),
                            song_id=song_id
                        )
                        fingerprints.append(fp)
                        
                except ElasticsearchException as scroll_error:
                    self.logger.warning(f"Scroll search error: {scroll_error}")
                    break
            
            # スクロールクリーンアップ
            try:
                self.client.clear_scroll(scroll_id=scroll_id)
            except ElasticsearchException:
                pass  # クリーンアップエラーは無視
                
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch fingerprint retrieval error: {e}")
        
        return fingerprints
