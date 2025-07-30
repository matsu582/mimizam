# Elasticsearchバックエンド

> 関連するソースファイル

Elasticsearchバックエンドは、大規模な分散環境での高速検索とリアルタイム分析に特化した検索エンジンです。水平スケーリングと高度な検索機能を提供します。

他のデータベースバックエンドについては、[データベースバックエンド概要](./05_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **高速検索**: 分散インデックスによる高速検索
- **水平スケーリング**: ノード追加による容易な拡張
- **リアルタイム**: 準リアルタイムでのデータ更新
- **全文検索**: 高度な全文検索機能
- **分析機能**: 集計とデータ分析機能
- **RESTful API**: HTTP APIによる操作

### 考慮事項

- **複雑な設定**: クラスター設定と管理が複雑
- **メモリ消費**: 大量のメモリを必要とする
- **データ整合性**: 結果整合性モデル
- **運用コスト**: 専門知識を持つ管理者が必要

## 基本的な使用方法

### ファクトリ関数

```python
from mimizam import create_mimizam_elasticsearch

# 単一ノード接続
mimizam = create_mimizam_elasticsearch(
    hosts="localhost:9200",
    index_name="music_fingerprints"
)

# 複数ノード接続
mimizam = create_mimizam_elasticsearch(
    hosts=[
        {"host": "es-node1.example.com", "port": 9200},
        {"host": "es-node2.example.com", "port": 9200},
        {"host": "es-node3.example.com", "port": 9200}
    ],
    index_name="music_fingerprints"
)

# 認証付き接続
mimizam = create_mimizam_elasticsearch(
    hosts="es.example.com:9200",
    index_name="music_fingerprints",
    http_auth=("username", "password"),
    use_ssl=True,
    verify_certs=True
)
```

## インデックス設定

### マッピング定義

```json
{
  "mappings": {
    "properties": {
      "song_id": {"type": "keyword"},
      "name": {
        "type": "text",
        "analyzer": "japanese",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "artist": {
        "type": "text",
        "analyzer": "japanese",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "album": {
        "type": "text",
        "analyzer": "japanese"
      },
      "duration": {"type": "float"},
      "file_path": {"type": "keyword"},
      "created_at": {"type": "date"}
    }
  }
}
```

### 指紋インデックス

```json
{
  "mappings": {
    "properties": {
      "song_id": {"type": "keyword"},
      "hash": {"type": "long"},
      "time_offset": {"type": "float"},
      "anchor_freq": {"type": "integer"},
      "target_freq": {"type": "integer"},
      "time_delta": {"type": "integer"}
    }
  }
}
```

## 検索機能

### 基本検索

```python
def search_songs_elasticsearch(client, query):
    """Elasticsearchで楽曲を検索"""
    search_body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["name^2", "artist", "album"],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        },
        "highlight": {
            "fields": {
                "name": {},
                "artist": {},
                "album": {}
            }
        }
    }
    
    response = client.search(
        index="music_songs",
        body=search_body,
        size=20
    )
    
    return response['hits']['hits']
```

### 指紋検索

```python
def search_fingerprints_elasticsearch(client, fingerprint_hashes):
    """指紋ハッシュで検索"""
    search_body = {
        "query": {
            "terms": {
                "hash": fingerprint_hashes
            }
        },
        "aggs": {
            "songs": {
                "terms": {
                    "field": "song_id",
                    "size": 100
                }
            }
        }
    }
    
    response = client.search(
        index="music_fingerprints",
        body=search_body,
        size=10000
    )
    
    return response
```

## パフォーマンス最適化

### インデックス設定

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "30s",
    "index": {
      "max_result_window": 50000,
      "mapping": {
        "total_fields": {
          "limit": 2000
        }
      }
    }
  }
}
```

### バルクインデックス

```python
def bulk_index_fingerprints(client, fingerprints, index_name):
    """指紋をバルクでインデックス"""
    from elasticsearch.helpers import bulk
    
    actions = []
    for fp in fingerprints:
        action = {
            "_index": index_name,
            "_source": {
                "song_id": fp["song_id"],
                "hash": fp["hash"],
                "time_offset": fp["time_offset"],
                "anchor_freq": fp.get("anchor_freq"),
                "target_freq": fp.get("target_freq"),
                "time_delta": fp.get("time_delta")
            }
        }
        actions.append(action)
    
    # バルクインデックス実行
    success, failed = bulk(client, actions, chunk_size=1000)
    
    return success, failed
```

## クラスター管理

### ノード監視

```python
def monitor_elasticsearch_cluster(client):
    """Elasticsearchクラスターを監視"""
    # クラスター健康状態
    health = client.cluster.health()
    
    # ノード情報
    nodes = client.nodes.info()
    
    # インデックス統計
    indices_stats = client.indices.stats()
    
    return {
        "cluster_health": health["status"],
        "active_nodes": health["number_of_nodes"],
        "active_shards": health["active_shards"],
        "indices_count": len(indices_stats["indices"]),
        "total_docs": sum(
            idx["total"]["docs"]["count"] 
            for idx in indices_stats["indices"].values()
        )
    }
```

### インデックス管理

```python
def manage_elasticsearch_indices(client):
    """インデックスを管理"""
    # 古いインデックスを削除（30日以上）
    import datetime
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30)
    
    indices = client.indices.get_alias("*")
    for index_name in indices:
        if index_name.startswith("music_fingerprints_"):
            try:
                # インデックス作成日を取得
                index_info = client.indices.get(index_name)
                creation_date = index_info[index_name]["settings"]["index"]["creation_date"]
                creation_datetime = datetime.datetime.fromtimestamp(int(creation_date) / 1000)
                
                if creation_datetime < cutoff_date:
                    client.indices.delete(index_name)
                    print(f"古いインデックスを削除: {index_name}")
                    
            except Exception as e:
                print(f"インデックス削除エラー {index_name}: {e}")
```

## バックアップと復元

### スナップショット設定

```python
def setup_elasticsearch_snapshots(client, repository_name, location):
    """スナップショットリポジトリを設定"""
    repository_body = {
        "type": "fs",
        "settings": {
            "location": location,
            "compress": True
        }
    }
    
    client.snapshot.create_repository(
        repository=repository_name,
        body=repository_body
    )
    
    print(f"スナップショットリポジトリを作成: {repository_name}")
```

### スナップショット作成

```python
def create_elasticsearch_snapshot(client, repository_name, snapshot_name):
    """スナップショットを作成"""
    snapshot_body = {
        "indices": "music_*",
        "ignore_unavailable": True,
        "include_global_state": False
    }
    
    response = client.snapshot.create(
        repository=repository_name,
        snapshot=snapshot_name,
        body=snapshot_body,
        wait_for_completion=False
    )
    
    return response
```

## セキュリティ設定

### 認証設定

```yaml
# elasticsearch.yml
xpack.security.enabled: true
xpack.security.transport.ssl.enabled: true
xpack.security.http.ssl.enabled: true

# ユーザー作成
elasticsearch-users useradd mimizam_user -p password -r mimizam_role
```

### ロール定義

```json
{
  "mimizam_role": {
    "cluster": ["monitor"],
    "indices": [
      {
        "names": ["music_*"],
        "privileges": ["read", "write", "create_index", "delete_index"]
      }
    ]
  }
}
```

## トラブルシューティング

### 接続問題

```python
def test_elasticsearch_connection(hosts):
    """Elasticsearch接続をテスト"""
    from elasticsearch import Elasticsearch
    
    try:
        client = Elasticsearch(hosts, timeout=30)
        
        # 接続テスト
        if client.ping():
            print("Elasticsearch接続成功")
            
            # クラスター情報を取得
            info = client.info()
            print(f"クラスター名: {info['cluster_name']}")
            print(f"バージョン: {info['version']['number']}")
            
            return True
        else:
            print("Elasticsearch接続失敗")
            return False
            
    except Exception as e:
        print(f"接続エラー: {e}")
        return False
```

### パフォーマンス問題

```python
def analyze_elasticsearch_performance(client):
    """Elasticsearchパフォーマンスを分析"""
    # ノード統計
    nodes_stats = client.nodes.stats()
    
    # インデックス統計
    indices_stats = client.indices.stats()
    
    # 実行中のタスク
    tasks = client.tasks.list()
    
    performance_data = {
        "heap_usage": {},
        "query_performance": {},
        "indexing_performance": {}
    }
    
    for node_id, node_stats in nodes_stats["nodes"].items():
        node_name = node_stats["name"]
        
        # ヒープ使用量
        heap_used = node_stats["jvm"]["mem"]["heap_used_percent"]
        performance_data["heap_usage"][node_name] = heap_used
        
        # クエリ統計
        search_stats = node_stats["indices"]["search"]
        performance_data["query_performance"][node_name] = {
            "query_total": search_stats["query_total"],
            "query_time_in_millis": search_stats["query_time_in_millis"],
            "avg_query_time": search_stats["query_time_in_millis"] / max(search_stats["query_total"], 1)
        }
    
    return performance_data
```

## 関連ドキュメント

- [データベースバックエンド概要](./05_database_backends.md) - 全バックエンドの比較
- [SQLiteバックエンド](./05_1_sqlite_backend.md) - 軽量ファイルベースDB
- [MySQLバックエンド](./05_2_mysql_backend.md) - 本番環境向けRDBMS
- [PostgreSQLバックエンド](./05_3_postgresql_backend.md) - 高機能RDBMS
