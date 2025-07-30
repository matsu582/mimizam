# データベース層

このドキュメントでは、mimizamの統一データベース抽象化層について説明します。この層は、SQLite、MySQL、PostgreSQL、Elasticsearchなど複数のデータベースバックエンドに対する共通インターフェースを提供します。

他のコンポーネントについては、[音声指紋エンジン](./03_1_audio_fingerprinting_engine.md)および[マッチング・識別システム](./03_3_matching_identification.md)を参照してください。

## 概要

データベース層は、異なるデータベースシステム間での透明な切り替えを可能にする抽象化レイヤーです。この設計により、アプリケーションコードを変更することなく、開発環境ではSQLite、本番環境ではMySQLやPostgreSQLを使用できます。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│                    統合API層                               │
├─────────────────────────────────────────────────────────────┤
│           FingerprintDatabase（統合インターフェース）        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  データベース抽象化層                       │
├─────────────────────────────────────────────────────────────┤
│              DatabaseBackend（抽象基底クラス）              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 具体的なバックエンド実装                    │
├─────────────────────────────────────────────────────────────┤
│  SQLiteBackend │ MySQLBackend │ PostgreSQLBackend │ ESBackend │
└─────────────────────────────────────────────────────────────┘
```

## 主要コンポーネント

### DatabaseBackend抽象基底クラス

全てのデータベースバックエンドが実装する共通インターフェースです。

```python
from abc import ABC, abstractmethod

class DatabaseBackend(ABC):
    """データベースバックエンドの抽象基底クラス"""
    
    @abstractmethod
    def connect(self):
        """データベースに接続"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """データベース接続を切断"""
        pass
    
    @abstractmethod
    def create_tables(self):
        """必要なテーブルを作成"""
        pass
    
    @abstractmethod
    def insert_song(self, song_name, **metadata):
        """楽曲情報を挿入"""
        pass
    
    @abstractmethod
    def insert_fingerprints(self, song_id, fingerprints):
        """指紋を挿入"""
        pass
    
    @abstractmethod
    def search_fingerprints(self, fingerprints):
        """指紋を検索"""
        pass
    
    @abstractmethod
    def get_song_info(self, song_id):
        """楽曲情報を取得"""
        pass
    
    @abstractmethod
    def get_song_count(self):
        """楽曲数を取得"""
        pass
    
    @abstractmethod
    def delete_song(self, song_id):
        """楽曲を削除"""
        pass
```

### FingerprintDatabaseクラス

データベースバックエンドを統合する高レベルインターフェースです。

```python
class FingerprintDatabase:
    """指紋データベースの統合インターフェース"""
    
    def __init__(self, backend):
        self.backend = backend
        self.backend.connect()
        self.backend.create_tables()
    
    def store_song(self, song_name, fingerprints, **metadata):
        """楽曲と指紋をデータベースに保存"""
        try:
            # 楽曲情報を挿入
            song_id = self.backend.insert_song(song_name, **metadata)
            
            # 指紋を挿入
            self.backend.insert_fingerprints(song_id, fingerprints)
            
            return song_id
        except Exception as e:
            raise DatabaseError(f"楽曲保存エラー: {e}")
    
    def search_matches(self, query_fingerprints):
        """指紋を検索してマッチを取得"""
        try:
            return self.backend.search_fingerprints(query_fingerprints)
        except Exception as e:
            raise DatabaseError(f"検索エラー: {e}")
    
    def get_song_info(self, song_id):
        """楽曲情報を取得"""
        return self.backend.get_song_info(song_id)
    
    def get_statistics(self):
        """データベース統計を取得"""
        return {
            'song_count': self.backend.get_song_count(),
            'backend_type': type(self.backend).__name__
        }
```

## データベーススキーマ

### 楽曲テーブル（songs）

```sql
CREATE TABLE songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    artist VARCHAR(255),
    album VARCHAR(255),
    duration FLOAT,
    file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 指紋テーブル（fingerprints）

```sql
CREATE TABLE fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    hash BIGINT NOT NULL,
    time_offset FLOAT NOT NULL,
    anchor_freq INTEGER,
    target_freq INTEGER,
    time_delta INTEGER,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE INDEX idx_fingerprints_hash ON fingerprints(hash);
CREATE INDEX idx_fingerprints_song_id ON fingerprints(song_id);
```

## 具体的なバックエンド実装

### SQLiteBackend

軽量なファイルベースデータベースバックエンドです。

```python
import sqlite3
import os

class SQLiteBackend(DatabaseBackend):
    """SQLiteデータベースバックエンド"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """SQLiteデータベースに接続"""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            return True
        except sqlite3.Error as e:
            raise DatabaseError(f"SQLite接続エラー: {e}")
    
    def disconnect(self):
        """接続を切断"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def create_tables(self):
        """テーブルを作成"""
        cursor = self.connection.cursor()
        
        # songsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                artist TEXT,
                album TEXT,
                duration REAL,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # fingerprintsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                hash INTEGER NOT NULL,
                time_offset REAL NOT NULL,
                anchor_freq INTEGER,
                target_freq INTEGER,
                time_delta INTEGER,
                FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
            )
        ''')
        
        # インデックス作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_hash ON fingerprints(hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_song_id ON fingerprints(song_id)')
        
        self.connection.commit()
    
    def insert_song(self, song_name, **metadata):
        """楽曲を挿入"""
        cursor = self.connection.cursor()
        
        cursor.execute('''
            INSERT INTO songs (name, artist, album, duration, file_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            song_name,
            metadata.get('artist'),
            metadata.get('album'),
            metadata.get('duration'),
            metadata.get('file_path')
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def insert_fingerprints(self, song_id, fingerprints):
        """指紋を挿入"""
        cursor = self.connection.cursor()
        
        fingerprint_data = [
            (song_id, fp['hash'], fp['time_offset'], 
             fp.get('anchor_freq'), fp.get('target_freq'), fp.get('time_delta'))
            for fp in fingerprints
        ]
        
        cursor.executemany('''
            INSERT INTO fingerprints (song_id, hash, time_offset, anchor_freq, target_freq, time_delta)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', fingerprint_data)
        
        self.connection.commit()
    
    def search_fingerprints(self, fingerprints):
        """指紋を検索"""
        cursor = self.connection.cursor()
        
        # ハッシュ値のリストを作成
        hash_values = [fp['hash'] for fp in fingerprints]
        placeholders = ','.join(['?'] * len(hash_values))
        
        cursor.execute(f'''
            SELECT song_id, hash, time_offset
            FROM fingerprints
            WHERE hash IN ({placeholders})
        ''', hash_values)
        
        results = cursor.fetchall()
        
        # 結果をグループ化
        matches = {}
        for row in results:
            song_id = row['song_id']
            if song_id not in matches:
                matches[song_id] = []
            
            matches[song_id].append({
                'hash': row['hash'],
                'db_time': row['time_offset']
            })
        
        return matches
```

### MySQLBackend

本番環境向けの高性能データベースバックエンドです。

```python
import mysql.connector
from mysql.connector import Error

class MySQLBackend(DatabaseBackend):
    """MySQLデータベースバックエンド"""
    
    def __init__(self, host, user, password, database, port=3306, **kwargs):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'port': port,
            'charset': kwargs.get('charset', 'utf8mb4'),
            'autocommit': True
        }
        self.connection = None
    
    def connect(self):
        """MySQLデータベースに接続"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            return True
        except Error as e:
            raise DatabaseError(f"MySQL接続エラー: {e}")
    
    def create_tables(self):
        """テーブルを作成"""
        cursor = self.connection.cursor()
        
        # songsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                duration FLOAT,
                file_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_songs_name (name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        
        # fingerprintsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                song_id INT NOT NULL,
                hash BIGINT NOT NULL,
                time_offset FLOAT NOT NULL,
                anchor_freq INT,
                target_freq INT,
                time_delta INT,
                FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
                INDEX idx_fingerprints_hash (hash),
                INDEX idx_fingerprints_song_id (song_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        
        cursor.close()
```

### PostgreSQLBackend

高機能なオープンソースデータベースバックエンドです。

```python
import psycopg2
from psycopg2.extras import RealDictCursor

class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQLデータベースバックエンド"""
    
    def __init__(self, host, user, password, database, port=5432, **kwargs):
        self.connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        self.connection = None
    
    def connect(self):
        """PostgreSQLデータベースに接続"""
        try:
            self.connection = psycopg2.connect(
                self.connection_string,
                cursor_factory=RealDictCursor
            )
            self.connection.autocommit = True
            return True
        except psycopg2.Error as e:
            raise DatabaseError(f"PostgreSQL接続エラー: {e}")
    
    def create_tables(self):
        """テーブルを作成"""
        cursor = self.connection.cursor()
        
        # songsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                duration REAL,
                file_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # fingerprintsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id BIGSERIAL PRIMARY KEY,
                song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                hash BIGINT NOT NULL,
                time_offset REAL NOT NULL,
                anchor_freq INTEGER,
                target_freq INTEGER,
                time_delta INTEGER
            )
        ''')
        
        # インデックス作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_hash ON fingerprints(hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_song_id ON fingerprints(song_id)')
        
        cursor.close()
```

### ElasticsearchBackend

分散検索エンジンバックエンドです。

```python
from elasticsearch import Elasticsearch

class ElasticsearchBackend(DatabaseBackend):
    """Elasticsearchデータベースバックエンド"""
    
    def __init__(self, hosts, index_name="mimizam", **kwargs):
        self.hosts = hosts if isinstance(hosts, list) else [hosts]
        self.index_name = index_name
        self.client = None
    
    def connect(self):
        """Elasticsearchクラスターに接続"""
        try:
            self.client = Elasticsearch(self.hosts)
            return self.client.ping()
        except Exception as e:
            raise DatabaseError(f"Elasticsearch接続エラー: {e}")
    
    def create_tables(self):
        """インデックスとマッピングを作成"""
        # songsインデックス
        songs_mapping = {
            "mappings": {
                "properties": {
                    "name": {"type": "text", "analyzer": "standard"},
                    "artist": {"type": "text", "analyzer": "standard"},
                    "album": {"type": "text", "analyzer": "standard"},
                    "duration": {"type": "float"},
                    "file_path": {"type": "keyword"},
                    "created_at": {"type": "date"}
                }
            }
        }
        
        if not self.client.indices.exists(index=f"{self.index_name}_songs"):
            self.client.indices.create(index=f"{self.index_name}_songs", body=songs_mapping)
        
        # fingerprintsインデックス
        fingerprints_mapping = {
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
        
        if not self.client.indices.exists(index=f"{self.index_name}_fingerprints"):
            self.client.indices.create(index=f"{self.index_name}_fingerprints", body=fingerprints_mapping)
```

## ファクトリ関数

各バックエンドに対応した便利な作成関数を提供します。

```python
def create_database_backend(backend_type, **config):
    """データベースバックエンドを作成"""
    
    if backend_type == 'sqlite':
        return SQLiteBackend(config['db_path'])
    
    elif backend_type == 'mysql':
        return MySQLBackend(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            port=config.get('port', 3306)
        )
    
    elif backend_type == 'postgresql':
        return PostgreSQLBackend(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            port=config.get('port', 5432)
        )
    
    elif backend_type == 'elasticsearch':
        return ElasticsearchBackend(
            hosts=config['hosts'],
            index_name=config.get('index_name', 'mimizam')
        )
    
    else:
        raise ValueError(f"サポートされていないバックエンド: {backend_type}")
```

## エラーハンドリング

```python
class DatabaseError(Exception):
    """データベース関連エラー"""
    pass

class ConnectionError(DatabaseError):
    """接続エラー"""
    pass

class SchemaError(DatabaseError):
    """スキーマエラー"""
    pass

class QueryError(DatabaseError):
    """クエリエラー"""
    pass
```

## パフォーマンス最適化

### 接続プール

```python
class ConnectionPool:
    """データベース接続プール"""
    
    def __init__(self, backend_factory, pool_size=5):
        self.backend_factory = backend_factory
        self.pool_size = pool_size
        self.pool = []
        self.in_use = set()
    
    def get_connection(self):
        """接続を取得"""
        if self.pool:
            connection = self.pool.pop()
        else:
            connection = self.backend_factory()
            connection.connect()
        
        self.in_use.add(connection)
        return connection
    
    def return_connection(self, connection):
        """接続を返却"""
        if connection in self.in_use:
            self.in_use.remove(connection)
            if len(self.pool) < self.pool_size:
                self.pool.append(connection)
            else:
                connection.disconnect()
```

### バッチ処理

```python
def batch_insert_fingerprints(self, song_id, fingerprints, batch_size=1000):
    """バッチ処理による指紋挿入"""
    for i in range(0, len(fingerprints), batch_size):
        batch = fingerprints[i:i + batch_size]
        self.backend.insert_fingerprints(song_id, batch)
```

データベース層は、mimizamシステムの柔軟性と拡張性を支える重要なコンポーネントです。統一されたインターフェースにより、異なるデータベースシステム間での透明な切り替えが可能になります。
