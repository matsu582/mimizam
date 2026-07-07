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

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import traceback
from ..database_base import (
    DatabaseBackend, DatabaseConfig, Song, Video, Fingerprint,
    group_query_times as _group_query_times,
)
from ..exceptions import ConnectionError, QueryError, DatabaseError

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import TransportError, ApiError
    from elasticsearch.helpers import bulk, scan
    # elasticsearch 8.xではApiErrorとTransportErrorが別階層
    ElasticsearchException = (TransportError, ApiError)
    ELASTICSEARCH_AVAILABLE = True
except ImportError as e:
    Elasticsearch = None
    TransportError = Exception
    ApiError = Exception
    ElasticsearchException = (Exception,)
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
            
            # ES操作はインデックス作成等で時間がかかるため最低120秒を確保
            es_timeout = max(self.config.pool_timeout or 30, 120)
            es_config = {
                'hosts': hosts,
                'request_timeout': es_timeout,
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
            self.logger.error(f"Elasticsearch connection error: {e} | Context: {{'host': self.config.host, 'port': self.config.port}}")
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
                            "type": "long",
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
            
            # インデックスを作成（既存の場合は無視）
            self._create_index_if_missing(
                self.songs_index, songs_mapping,
            )
            self._create_index_if_missing(
                self.fingerprints_index, fingerprints_mapping,
            )
            
            return True
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch index creation error: {e}")
            return False

    def _create_index_if_missing(
        self, index_name: str, body: dict,
    ) -> None:
        """インデックスが存在しなければ作成する（既存なら無視）"""
        try:
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(
                    index=index_name, body=body,
                )
                self.logger.info(
                    f"Created index: {index_name}"
                )
        except Exception as e:
            if "resource_already_exists_exception" in str(e):
                self.logger.debug(
                    f"Index already exists: {index_name}"
                )
            else:
                raise

        # プライマリシャードがアクティブになるまで待機
        # （リソース制約環境でのunavailable_shards_exceptionを回避）
        try:
            self.client.cluster.health(
                index=index_name,
                wait_for_status="yellow",
                timeout="60s",
            )
        except Exception as e:
            self.logger.warning(
                f"Index shard health wait failed: {index_name}: {e}"
            )
    
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
                refresh=self.config.es_refresh_on_write,
                timeout='60s'  # タイムアウト延長
            )
            
            # レスポンスの確認
            if response.get('result') in ['created', 'updated']:
                return True
            raise DatabaseError(
                "Failed to add song (unexpected Elasticsearch response)",
                context={'song_id': song.id, 'result': response.get('result')},
            )
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch song addition error: {e} | Context: {{'song_id': song.id}}")
            raise DatabaseError(
                "Failed to add song", original_error=e,
                context={'song_id': song.id},
            ) from e
    
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
                    refresh=self.config.es_refresh_on_write,
                )
                
                if failed:
                    self.logger.error(f"Bulk index failed: {len(failed)} items")
                    raise DatabaseError(
                        "Failed to add fingerprints (bulk index failure)",
                        context={'song_id': song_id, 'failed': len(failed)},
                    )
            
            return True
        except DatabaseError:
            raise
        except Exception as e:
            self.logger.error(f"Elasticsearch fingerprint addition error: {e} | Context: {{'song_id': song_id, 'count': len(fingerprints)}}")
            raise DatabaseError(
                "Failed to add fingerprints", original_error=e,
                context={'song_id': song_id, 'count': len(fingerprints)},
            ) from e

    def _maybe_refresh_for_search(self, *indices: str) -> None:
        """検索時refreshが有効な場合のみ、指定インデックスをrefreshする

        書き込み時refresh(es_refresh_on_write)で追加データは即座に検索可能なため、
        検索・読み取り経路のrefreshは既定で行わない（本番レイテンシ改善）。
        音声・映像いずれのESホットパスもこのヘルパで方針を統一する。
        """
        if not self.config.es_refresh_on_search:
            return
        for index in indices:
            try:
                self.client.indices.refresh(index=index)
            except ElasticsearchException:
                pass  # リフレッシュエラーは無視

    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """Elasticsearchでフィンガープリントを検索"""
        matches = {}

        if not query_fingerprints:
            return matches

        try:
            self._maybe_refresh_for_search(self.fingerprints_index)
            
            # ハッシュ値のリストを作成
            # 同一ハッシュの多重度を保持するため hash -> query_time群 で集約
            hash_to_query_times = _group_query_times(query_fingerprints)
            hash_values = list(hash_to_query_times.keys())
            
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
                    
                    # 結果処理：DB返り行ごとに該当する全query_timeへ展開
                    for hit in result['hits']['hits']:
                        source = hit['_source']
                        hash_value = source['hash_value']
                        song_id = source['song_id']
                        db_time = float(source['time_offset'])
                        
                        query_times = hash_to_query_times.get(hash_value)
                        if query_times:
                            bucket = matches.setdefault(song_id, [])
                            for query_time_offset in query_times:
                                bucket.append((float(query_time_offset), db_time))
                            
                except ElasticsearchException as batch_error:
                    self.logger.warning(f"Elasticsearch batch search error (batch {i//batch_size + 1}): {batch_error}")
                    continue
                        
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch fingerprint search error: {e}")
        
        return matches
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """Elasticsearchから楽曲情報を取得"""
        try:
            self._maybe_refresh_for_search(self.songs_index)
            
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

    def get_songs(self, song_ids: List[str]) -> Dict[str, Optional[Song]]:
        """Elasticsearchから複数楽曲を _mget で一括取得する"""
        unique_ids = list(dict.fromkeys(song_ids))  # 重複排除・順序保持
        song_map: Dict[str, Optional[Song]] = {sid: None for sid in unique_ids}
        if not unique_ids:
            return song_map
        try:
            self._maybe_refresh_for_search(self.songs_index)

            result = self.client.mget(index=self.songs_index, ids=unique_ids)
            for doc in result.get('docs', []):
                if not doc.get('found'):
                    continue
                source = doc['_source']
                meta = source.get('meta') if 'meta' in source else None
                song_map[source['id']] = Song(
                    id=source['id'],
                    title=source['title'],
                    artist=source['artist'],
                    file_path=source['file_path'],
                    meta=meta,
                    created_at=source.get('created_at'),
                )
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch batch song retrieval error: {e}")
        return song_map

    def list_songs(self) -> List[Song]:
        """Elasticsearchから全楽曲をリスト表示"""
        songs = []
        try:
            self._maybe_refresh_for_search(self.songs_index)
            
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
            self._maybe_refresh_for_search(self.songs_index, self.fingerprints_index)
            
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
            self.logger.error(f"Elasticsearch song deletion error: {e} | Context: {{'song_id': song_id}}")
            raise DatabaseError(
                "Failed to delete song", original_error=e,
                context={'song_id': song_id},
            ) from e

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

    # ===== 映像指紋メソッド =====

    def _ensure_video_indices(self) -> None:
        """映像指紋用インデックスを作成（存在しない場合のみ）"""
        videos_idx = f"{self.songs_index.rsplit('_', 1)[0]}_videos"
        ffp_idx = f"{self.songs_index.rsplit('_', 1)[0]}_frame_fingerprints"
        fdesc_idx = f"{self.songs_index.rsplit('_', 1)[0]}_frame_descriptors"

        self._videos_index = videos_idx
        self._frame_fp_index = ffp_idx
        self._frame_desc_index = fdesc_idx

        videos_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {"properties": {
                "id": {"type": "keyword"},
                "title": {"type": "text", "fields": {
                    "keyword": {"type": "keyword"}
                }},
                "file_path": {"type": "keyword"},
                "duration": {"type": "double"},
                "frame_count": {"type": "integer"},
                "created_at": {"type": "date"},
            }},
        }
        ffp_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {"properties": {
                "video_id": {"type": "keyword"},
                "frame_index": {"type": "integer"},
                "timestamp": {"type": "double"},
                "fingerprint": {"type": "binary"},
                "embedding": {
                    "type": "dense_vector",
                    "index": True,
                    "similarity": "cosine",
                },
            }},
        }

        fdesc_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {"properties": {
                "video_id": {"type": "keyword"},
                "frame_index": {"type": "integer"},
                "timestamp": {"type": "double"},
                "descriptors": {"type": "binary"},
                "descriptor_count": {"type": "integer"},
            }},
        }

        try:
            self._create_index_if_missing(videos_idx, videos_body)
            self._create_index_if_missing(ffp_idx, ffp_body)
            self._create_index_if_missing(fdesc_idx, fdesc_body)

            # 既存フレームインデックスにもembeddingフィールドを追加
            try:
                self.client.indices.put_mapping(
                    index=ffp_idx,
                    body={"properties": {
                        "embedding": {
                            "type": "dense_vector",
                            "index": True,
                            "similarity": "cosine",
                        },
                    }},
                )
            except ElasticsearchException:
                pass
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch video index creation error: {e}"
            )

    def add_video(self, video: Video) -> bool:
        """Elasticsearchに映像メタデータを追加"""
        try:
            self._ensure_video_indices()
            doc = {
                "id": video.id,
                "title": video.title,
                "file_path": video.file_path,
                "duration": video.duration,
                "frame_count": video.frame_count,
                "created_at": datetime.now().isoformat(),
            }
            resp = self.client.index(
                index=self._videos_index, id=video.id,
                body=doc, refresh=self.config.es_refresh_on_write, timeout="60s",
            )
            if resp.get("result") in ("created", "updated"):
                return True
            raise DatabaseError(
                "Failed to add video (unexpected Elasticsearch response)",
                context={'video_id': video.id, 'result': resp.get('result')},
            )
        except ElasticsearchException as e:
            self.logger.error(f"Elasticsearch video addition error: {e}")
            raise DatabaseError(
                "Failed to add video", original_error=e,
                context={'video_id': video.id},
            ) from e

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> bool:
        """Elasticsearchにフレーム単位指紋を一括保存"""
        import base64
        import numpy as np
        try:
            self._ensure_video_indices()
            self.client.delete_by_query(
                index=self._frame_fp_index,
                body={"query": {"term": {"video_id": video_id}}},
            )
            actions = []
            for fidx, ts, fp_blob in frames:
                # L2正規化済みフレーム指紋をdense_vectorとして格納しANN検索に用いる
                embedding = np.frombuffer(
                    fp_blob, dtype=np.float32
                ).tolist()
                actions.append({
                    "_index": self._frame_fp_index,
                    "_source": {
                        "video_id": video_id,
                        "frame_index": fidx,
                        "timestamp": float(ts),
                        "fingerprint": base64.b64encode(fp_blob).decode(),
                        "embedding": embedding,
                    },
                })
            if actions:
                _, failed = bulk(self.client, actions, chunk_size=5000,
                                 refresh=self.config.es_refresh_on_write)
                if failed:
                    self.logger.error(
                        f"Bulk frame fingerprint index failed: "
                        f"{len(failed)} items"
                    )
                    raise DatabaseError(
                        "Failed to add frame fingerprints (bulk index failure)",
                        context={'video_id': video_id, 'failed': len(failed)},
                    )
            return True
        except DatabaseError:
            raise
        except Exception as e:
            self.logger.error(
                f"Elasticsearch frame fingerprint save error: {e}"
            )
            raise DatabaseError(
                "Failed to add frame fingerprints", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4,
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームのkNN近傍を引き、映像別に得票/類似度を集計

        dense_vector(cosine)へのkNN検索をmsearchでまとめて発行し、
        音声のhash投票と同型に video_id 別の votes / score_sum を返す。

        戻り値: {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        import numpy as np
        agg: Dict[str, Dict[str, float]] = {}
        if not query_fps:
            return agg
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._frame_fp_index)

            num_candidates = max(k_per_query * 5, 100)
            body: List[Dict[str, Any]] = []
            for q_blob in query_fps:
                q_vec = np.frombuffer(q_blob, dtype=np.float32).tolist()
                body.append({"index": self._frame_fp_index})
                body.append({
                    "knn": {
                        "field": "embedding",
                        "query_vector": q_vec,
                        "k": k_per_query,
                        "num_candidates": num_candidates,
                    },
                    "_source": ["video_id"],
                    "size": k_per_query,
                })

            resp = self.client.msearch(body=body)
            for res in resp.get("responses", []):
                hits = res.get("hits", {}).get("hits", [])
                for hit in hits:
                    # ES cosine: _score = (1 + cosine) / 2
                    sim = 2.0 * float(hit["_score"]) - 1.0
                    if sim < sim_threshold:
                        continue
                    vid_id = hit["_source"]["video_id"]
                    slot = agg.setdefault(
                        vid_id, {"votes": 0.0, "score_sum": 0.0}
                    )
                    slot["votes"] += 1.0
                    slot["score_sum"] += sim
            return agg
        except Exception as e:
            self.logger.error(f"ES frame kNN search error: {e}")
            return agg

    def _scan_sources(
        self, index: str, query: Dict[str, Any], page_size: int = 5000,
    ):
        """指定クエリに一致する全ドキュメントの _source を段階取得で列挙する

        固定 size での一括取得は上限（10000等）を超えるとヒットが黙って欠落する。
        scroll ベースの scan で全件を漏れなく走査し、大規模データでも取りこぼさない。
        """
        for hit in scan(
            self.client, index=index,
            query={"query": query}, size=page_size,
            preserve_order=False,
        ):
            yield hit["_source"]

    def get_frame_fingerprints(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes]]:
        """Elasticsearchから指定映像のフレーム指紋を取得"""
        import base64

        results: list = []
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._frame_fp_index)

            for src in self._scan_sources(
                self._frame_fp_index, {"term": {"video_id": video_id}}
            ):
                results.append((
                    int(src["frame_index"]),
                    float(src["timestamp"]),
                    base64.b64decode(src["fingerprint"]),
                ))
            results.sort(key=lambda r: r[0])
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch frame fingerprint retrieval error: {e}"
            )
        return results

    def get_frame_fingerprints_batch(
        self, video_ids: List[str],
    ) -> Dict[str, List[Tuple[int, float, bytes]]]:
        """Elasticsearchから複数映像のフレーム指紋をterms1クエリで一括取得"""
        import base64

        result: Dict[str, List[Tuple[int, float, bytes]]] = {
            vid: [] for vid in video_ids
        }
        if not video_ids:
            return result
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._frame_fp_index)

            for src in self._scan_sources(
                self._frame_fp_index,
                {"terms": {"video_id": list(video_ids)}},
            ):
                vid = src["video_id"]
                if vid not in result:
                    continue
                result[vid].append((
                    int(src["frame_index"]),
                    float(src["timestamp"]),
                    base64.b64decode(src["fingerprint"]),
                ))
            for vid in result:
                result[vid].sort(key=lambda r: r[0])
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch frame fingerprint batch retrieval error: {e}"
            )
        return result

    def get_video(self, video_id: str) -> Optional[Video]:
        """Elasticsearchから映像情報を取得"""
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._videos_index)
            result = self.client.get(
                index=self._videos_index, id=video_id
            )
            src = result["_source"]
            return Video(
                id=src["id"], title=src["title"],
                file_path=src["file_path"],
                duration=src.get("duration"),
                frame_count=src.get("frame_count"),
                created_at=src.get("created_at"),
            )
        except ElasticsearchException:
            return None

    def get_videos(
        self, video_ids: List[str]
    ) -> Dict[str, Optional[Video]]:
        """Elasticsearchから複数映像のメタデータをterms1クエリで一括取得（N+1回避）"""
        result: Dict[str, Optional[Video]] = {vid: None for vid in video_ids}
        if not video_ids:
            return result
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._videos_index)
            resp = self.client.search(
                index=self._videos_index,
                body={
                    "query": {"terms": {"id": list(video_ids)}},
                    "size": len(video_ids),
                },
            )
            for h in resp["hits"]["hits"]:
                src = h["_source"]
                result[src["id"]] = Video(
                    id=src["id"], title=src["title"],
                    file_path=src["file_path"],
                    duration=src.get("duration"),
                    frame_count=src.get("frame_count"),
                    created_at=src.get("created_at"),
                )
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch video batch retrieval error: {e}"
            )
        return result

    def list_videos(self) -> List[Video]:
        """Elasticsearchから全映像をリスト取得"""
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._videos_index)
            resp = self.client.search(
                index=self._videos_index,
                body={
                    "query": {"match_all": {}},
                    "size": 10000,
                    "sort": [{"title.keyword": {"order": "asc"}}],
                },
            )
            return [
                Video(
                    id=h["_source"]["id"],
                    title=h["_source"]["title"],
                    file_path=h["_source"]["file_path"],
                    duration=h["_source"].get("duration"),
                    frame_count=h["_source"].get("frame_count"),
                    created_at=h["_source"].get("created_at"),
                )
                for h in resp["hits"]["hits"]
            ]
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch video list retrieval error: {e}"
            )
            return []

    def delete_video(self, video_id: str) -> bool:
        """Elasticsearchから映像と関連指紋を削除"""
        try:
            self._ensure_video_indices()
            self.client.delete(
                index=self._videos_index, id=video_id
            )
            self.client.delete_by_query(
                index=self._frame_fp_index,
                body={"query": {"term": {"video_id": video_id}}},
            )
            self.client.delete_by_query(
                index=self._frame_desc_index,
                body={"query": {"term": {"video_id": video_id}}},
            )
            return True
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch video deletion error: {e}"
            )
            raise DatabaseError(
                "Failed to delete video", original_error=e,
                context={'video_id': video_id},
            ) from e

    def add_frame_descriptors(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes, int]],
    ) -> bool:
        """Elasticsearchにフレーム単位AKAZE記述子を一括保存（幾何検証・再生成用）"""
        import base64
        try:
            self._ensure_video_indices()
            self.client.delete_by_query(
                index=self._frame_desc_index,
                body={"query": {"term": {"video_id": video_id}}},
            )
            actions = []
            for fidx, ts, desc_blob, desc_count in frames:
                actions.append({
                    "_index": self._frame_desc_index,
                    "_source": {
                        "video_id": video_id,
                        "frame_index": int(fidx),
                        "timestamp": float(ts),
                        "descriptors": base64.b64encode(desc_blob).decode(),
                        "descriptor_count": int(desc_count),
                    },
                })
            if actions:
                _, failed = bulk(self.client, actions, chunk_size=1000,
                                 refresh=self.config.es_refresh_on_write)
                if failed:
                    self.logger.error(
                        f"Bulk frame descriptor index failed: "
                        f"{len(failed)} items"
                    )
                    raise DatabaseError(
                        "Failed to add frame descriptors (bulk index failure)",
                        context={'video_id': video_id, 'failed': len(failed)},
                    )
            return True
        except DatabaseError:
            raise
        except Exception as e:
            self.logger.error(
                f"Elasticsearch frame descriptor save error: {e}"
            )
            raise DatabaseError(
                "Failed to add frame descriptors", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def get_frame_descriptors(
        self, video_id: str,
        frame_indices: Optional[List[int]] = None,
    ) -> List[Tuple[int, float, bytes, int]]:
        """Elasticsearchから指定映像のフレーム記述子を取得

        frame_indices を渡すと、そのフレームインデックスの記述子だけを取得する。
        幾何検証はANN上位候補のDBフレームしか突き合わせないため、必要なフレームに
        限定して読み込むことで生記述子の無駄なI/Oを避ける。None なら全件取得。
        """
        import base64

        results: List[Tuple[int, float, bytes, int]] = []
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._frame_desc_index)
            must: List[Dict[str, Any]] = [{"term": {"video_id": video_id}}]
            if frame_indices is not None:
                if not frame_indices:
                    return []
                must.append({
                    "terms": {"frame_index": [int(f) for f in frame_indices]}
                })
            for src in self._scan_sources(
                self._frame_desc_index, {"bool": {"filter": must}}
            ):
                results.append((
                    int(src["frame_index"]),
                    float(src["timestamp"]),
                    base64.b64decode(src["descriptors"]),
                    int(src["descriptor_count"]),
                ))
            results.sort(key=lambda r: r[0])
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch frame descriptor retrieval error: {e}"
            )
        return results

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, bytes, int]]]:
        """Elasticsearchから全映像のフレーム記述子を取得"""
        import base64

        result: Dict[str, List[Tuple[int, float, bytes, int]]] = {}
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(self._frame_desc_index)
            for src in self._scan_sources(
                self._frame_desc_index, {"match_all": {}}
            ):
                result.setdefault(src["video_id"], []).append((
                    int(src["frame_index"]),
                    float(src["timestamp"]),
                    base64.b64decode(src["descriptors"]),
                    int(src["descriptor_count"]),
                ))
            for vid in result:
                result[vid].sort(key=lambda r: r[0])
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch all frame descriptor retrieval error: {e}"
            )
        return result

    def get_video_stats(self) -> Dict[str, int]:
        """Elasticsearchの映像指紋統計を取得"""
        stats = {
            "videos": 0,
            "frame_fingerprints": 0,
        }
        try:
            self._ensure_video_indices()
            self._maybe_refresh_for_search(
                self._videos_index, self._frame_fp_index
            )
            for idx_name, key in [
                (self._videos_index, "videos"),
                (self._frame_fp_index, "frame_fingerprints"),
            ]:
                try:
                    cnt = self.client.count(index=idx_name)
                    stats[key] = cnt["count"]
                except ElasticsearchException:
                    pass
        except ElasticsearchException as e:
            self.logger.error(
                f"Elasticsearch video statistics error: {e}"
            )
        return stats
