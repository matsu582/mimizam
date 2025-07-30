# データベース層

このページでは、mimizamシステムのデータベース抽象化層について説明します。この層は、指紋とメタデータの保存、検索、管理を統一インターフェースを通じて複数のデータベース技術で処理します。

基本的な音声指紋概念については、[音声指紋エンジン](./04_audio_fingerprinting_engine.md)を参照してください。データベース固有の設定詳細については、[データベースバックエンド](./09_database_backends.md)を参照してください。検索とマッチング機能については、[マッチング・識別システム](./06_matching_identification.md)を参照してください。

## データベース抽象化アーキテクチャ

mimizamは、共通インターフェースを通じて複数のストレージ技術をサポートする統一データベース抽象化層を提供します。この設計により、アプリケーションコードを変更することなく、異なるデータベースバックエンド間で切り替えることができます。

```
統一インターフェース層
├── FingerprintDatabase (抽象化とメタデータ管理)
├── DatabaseBackend (バックエンド固有の実装)
└── 具体的バックエンド (SQLite/MySQL/PostgreSQL/Elasticsearch)
```

## 対応データベースバックエンド

| バックエンド | ファクトリ関数 | 用途 | 主要機能 |
|-------------|---------------|------|----------|
| **SQLite** | `create_mimizam_sqlite()` | 開発、小規模デプロイ | ファイルベース、ゼロ設定、高速クエリ |
| **MySQL** | `create_mimizam_mysql()` | 本番Webアプリケーション | ACID準拠、レプリケーション、大規模対応 |
| **PostgreSQL** | `create_mimizam_postgresql()` | 高性能アプリケーション | 高度なインデックス、JSON対応、拡張性 |
| **Elasticsearch** | `create_mimizam_elasticsearch()` | 分散検索システム | 全文検索、水平スケーリング、分析機能 |

## データベーススキーマ

全バックエンドは、指紋と楽曲メタデータを保存するための一貫したスキーマを実装します：

### 楽曲テーブル (songs)

| カラム | 型 | 制約 | 説明 |
|--------|---|------|------|
| `id` | INTEGER/BIGINT | PRIMARY KEY | 楽曲の一意識別子 |
| `title` | TEXT/VARCHAR | NOT NULL | 楽曲タイトル |
| `artist` | TEXT/VARCHAR | NOT NULL | アーティスト名 |
| `duration` | FLOAT/DOUBLE | NULL可 | 楽曲の長さ（秒） |
| `file_path` | TEXT/VARCHAR | NULL可 | 元音声ファイルのパス |
| `created_at` | TIMESTAMP | DEFAULT NOW | 作成日時 |
| `updated_at` | TIMESTAMP | DEFAULT NOW | 更新日時 |

### 指紋テーブル (fingerprints)

| カラム | 型 | 制約 | 説明 |
|--------|---|------|------|
| `id` | INTEGER/BIGINT | PRIMARY KEY | 指紋の一意識別子 |
| `song_id` | INTEGER/BIGINT | FOREIGN KEY | 関連楽曲のID |
| `hash` | TEXT/VARCHAR(64) | INDEXED | SHA-256ハッシュ文字列 |
| `time_offset` | FLOAT/DOUBLE | NOT NULL | 楽曲内での時間オフセット（秒） |
| `created_at` | TIMESTAMP | DEFAULT NOW | 作成日時 |

### インデックス戦略

効率的な検索のため、以下のインデックスが作成されます：

```sql
-- ハッシュベースの高速検索
CREATE INDEX idx_fingerprints_hash ON fingerprints(hash);

-- 楽曲別指紋検索
CREATE INDEX idx_fingerprints_song_id ON fingerprints(song_id);

-- 時間ベースの検索
CREATE INDEX idx_fingerprints_time_offset ON fingerprints(time_offset);

-- 複合インデックス（高度なクエリ用）
CREATE INDEX idx_fingerprints_hash_song ON fingerprints(hash, song_id);
```

## FingerprintDatabase クラス

`FingerprintDatabase`クラスは、データベース操作の主要インターフェースを提供します。

### 楽曲管理操作

#### 楽曲追加

```python
def add_song(self, file_path: str, title: str, artist: str) -> int:
    """楽曲をデータベースに追加し、指紋を生成"""
    
def _store_song_metadata(self, title: str, artist: str, duration: float, file_path: str) -> int:
    """楽曲メタデータをデータベースに保存"""
    
def _store_fingerprints(self, song_id: int, fingerprints: List[Tuple[str, float]]) -> None:
    """指紋をデータベースに保存"""
```

#### 楽曲検索と管理

```python
def get_song_by_id(self, song_id: int) -> Optional[Song]:
    """IDによる楽曲取得"""
    
def search_songs_by_title(self, title: str) -> List[Song]:
    """タイトルによる楽曲検索"""
    
def search_songs_by_artist(self, artist: str) -> List[Song]:
    """アーティストによる楽曲検索"""
    
def delete_song(self, song_id: int) -> bool:
    """楽曲と関連指紋の削除"""
```

### データベース統計

```python
def get_database_stats(self) -> Dict[str, Any]:
    """データベース統計情報を取得"""
    return {
        'song_count': self._count_songs(),
        'fingerprint_count': self._count_fingerprints(),
        'avg_fingerprints_per_song': self._avg_fingerprints_per_song(),
        'database_size': self._get_database_size(),
        'oldest_song': self._get_oldest_song_date(),
        'newest_song': self._get_newest_song_date()
    }
```

### データベース操作フロー

#### 楽曲追加処理

```python
def add_song(self, file_path: str, title: str, artist: str) -> int:
    """完全な楽曲追加フロー"""
    try:
        # 1. 音声ファイル読み込みと検証
        audio, sr = self._load_and_validate_audio(file_path)
        
        # 2. 指紋生成
        fingerprints = self.fingerprinter.generate_fingerprints(file_path)
        
        # 3. メタデータ保存
        song_id = self._store_song_metadata(title, artist, len(audio)/sr, file_path)
        
        # 4. 指紋保存
        self._store_fingerprints(song_id, fingerprints)
        
        # 5. インデックス更新
        self._update_search_indices(song_id)
        
        return song_id
        
    except Exception as e:
        self._rollback_transaction()
        raise DatabaseError(f"楽曲追加失敗: {e}")
```

## DatabaseBackend インターフェース

各データベースバックエンドは、共通の`DatabaseBackend`インターフェースを実装します：

### 基本操作

```python
class DatabaseBackend:
    def connect(self) -> None:
        """データベース接続を確立"""
        
    def disconnect(self) -> None:
        """データベース接続を切断"""
        
    def execute_query(self, query: str, params: Tuple = ()) -> Any:
        """SQLクエリを実行"""
        
    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """バッチクエリを実行"""
```

### トランザクション管理

```python
def begin_transaction(self) -> None:
    """トランザクション開始"""
    
def commit_transaction(self) -> None:
    """トランザクションコミット"""
    
def rollback_transaction(self) -> None:
    """トランザクションロールバック"""
    
@contextmanager
def transaction(self):
    """トランザクションコンテキストマネージャー"""
    self.begin_transaction()
    try:
        yield
        self.commit_transaction()
    except Exception:
        self.rollback_transaction()
        raise
```

### バックエンド固有の最適化

各バックエンドは、そのデータベース技術に特化した最適化を実装します：

#### SQLite最適化

```python
def _optimize_sqlite(self):
    """SQLite固有の最適化設定"""
    self.execute_query("PRAGMA journal_mode=WAL")
    self.execute_query("PRAGMA synchronous=NORMAL") 
    self.execute_query("PRAGMA cache_size=10000")
    self.execute_query("PRAGMA temp_store=MEMORY")
```

#### MySQL最適化

```python
def _optimize_mysql(self):
    """MySQL固有の最適化設定"""
    self.execute_query("SET SESSION innodb_buffer_pool_size=128M")
    self.execute_query("SET SESSION query_cache_type=ON")
    self.execute_query("SET SESSION bulk_insert_buffer_size=8M")
```

#### PostgreSQL最適化

```python
def _optimize_postgresql(self):
    """PostgreSQL固有の最適化設定"""
    self.execute_query("SET work_mem='64MB'")
    self.execute_query("SET maintenance_work_mem='256MB'")
    self.execute_query("SET effective_cache_size='1GB'")
```

## データベース統合

### コアシステムとの統合

データベース層は、mimizamのコアシステムとシームレスに統合されます：

```python
class Mimizam:
    def __init__(self, database: FingerprintDatabase):
        self.database = database
        self.fingerprinter = database.fingerprinter
        self.matcher = FingerprintMatcher(database)
    
    def add_song(self, file_path: str, title: str, artist: str) -> int:
        """高レベルAPI経由での楽曲追加"""
        return self.database.add_song(file_path, title, artist)
```

### API統合

```python
# ファクトリ関数による簡単なセットアップ
def create_mimizam_sqlite(db_path: str, **kwargs) -> Mimizam:
    """SQLiteバックエンドでMimizamインスタンスを作成"""
    backend = SQLiteBackend(db_path)
    database = FingerprintDatabase(backend, **kwargs)
    return Mimizam(database)
```

### パフォーマンス統合

データベース層は、システム全体のパフォーマンス監視と統合されます：

```python
def _track_database_performance(self, operation: str):
    """データベース操作のパフォーマンス追跡"""
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        self.performance_monitor.record_operation(operation, duration)
```

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [マッチング・識別システム](./06_matching_identification.md) - 検索とスコアリング
- [データベースバックエンド](./09_database_backends.md) - 個別バックエンドの詳細
- [SQLiteバックエンド](./10_sqlite_backend.md) - SQLite固有の設定
- [MySQLバックエンド](./11_mysql_backend.md) - MySQL固有の設定
- [PostgreSQLバックエンド](./12_postgresql_backend.md) - PostgreSQL固有の設定
- [Elasticsearchバックエンド](./13_elasticsearch_backend.md) - Elasticsearch固有の設定
