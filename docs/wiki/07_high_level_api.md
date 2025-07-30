# 高レベルAPI

このページでは、mimizamシステムの高レベルAPIについて説明します。これらのAPIは、音声指紋生成と識別の複雑さを隠蔽し、開発者が簡単にmimizamの機能を利用できるように設計されています。

低レベルコンポーネントの詳細については、[低レベルコンポーネント](./08_low_level_components.md)を参照してください。データベース設定については、[データベースバックエンド](./09_database_backends.md)を参照してください。

## Mimizamクラス

`Mimizam`クラスは、mimizamシステムの主要なエントリーポイントです。楽曲の追加、検索、識別のための統一インターフェースを提供します。

### クラス初期化

```python
class Mimizam:
    def __init__(self, database: FingerprintDatabase):
        self.database = database
        self.fingerprinter = database.fingerprinter
        self.matcher = FingerprintMatcher(database)
```

### 主要メソッド

#### 楽曲管理

```python
def add_song(self, file_path: str, title: str, artist: str) -> int:
    """楽曲をデータベースに追加"""
    
def get_song_by_id(self, song_id: int) -> Optional[Song]:
    """IDによる楽曲取得"""
    
def search_songs_by_title(self, title: str) -> List[Song]:
    """タイトルによる楽曲検索"""
    
def search_songs_by_artist(self, artist: str) -> List[Song]:
    """アーティストによる楽曲検索"""
    
def delete_song(self, song_id: int) -> bool:
    """楽曲削除"""
```

#### 音声識別

```python
def identify_audio(self, audio_file_path: str, min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
    """音声ファイルから楽曲を識別"""
    
def search_song(self, audio_file_path: str, min_confidence: float = 0.2, top_k: int = 10) -> List[Dict[str, Any]]:
    """複数の候補楽曲を検索"""
```

#### データベース統計

```python
def get_database_stats(self) -> Dict[str, Any]:
    """データベース統計情報を取得"""
    
def get_performance_stats(self) -> Dict[str, Any]:
    """パフォーマンス統計情報を取得"""
```

## ファクトリ関数

mimizamは、異なるデータベースバックエンドでの迅速なセットアップのための便利なファクトリ関数を提供します。

### SQLiteファクトリ

```python
def create_mimizam_sqlite(
    db_path: str,
    n_fft: int = 2048,
    hop_length: int = 512,
    min_amplitude: float = -60,
    peak_neighborhood_size: int = 20,
    target_zone_size: int = 5,
    time_range: int = 200,
    enable_adaptive_params: bool = False,
    debug: bool = False
) -> Mimizam:
    """SQLiteバックエンドでMimizamインスタンスを作成"""
```

#### 使用例

```python
from mimizam import create_mimizam_sqlite

# 基本的な使用
with create_mimizam_sqlite("my_music.db") as mimizam:
    song_id = mimizam.add_song("song.wav", "My Song", "Artist")
    result = mimizam.identify_audio("query.wav")

# 高精度設定
with create_mimizam_sqlite(
    "precision_db.db",
    n_fft=4096,
    hop_length=256,
    min_amplitude=-70,
    enable_adaptive_params=True
) as mimizam:
    # 高精度処理
    pass
```

### MySQLファクトリ

```python
def create_mimizam_mysql(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 3306,
    **kwargs
) -> Mimizam:
    """MySQLバックエンドでMimizamインスタンスを作成"""
```

#### 使用例

```python
from mimizam import create_mimizam_mysql

# MySQL接続
with create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
) as mimizam:
    # 本番環境での使用
    pass
```

### PostgreSQLファクトリ

```python
def create_mimizam_postgresql(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 5432,
    **kwargs
) -> Mimizam:
    """PostgreSQLバックエンドでMimizamインスタンスを作成"""
```

#### 使用例

```python
from mimizam import create_mimizam_postgresql

# PostgreSQL接続
with create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
) as mimizam:
    # 高性能アプリケーション
    pass
```

### Elasticsearchファクトリ

```python
def create_mimizam_elasticsearch(
    host: str = "localhost",
    port: int = 9200,
    index_name: str = "mimizam",
    **kwargs
) -> Mimizam:
    """ElasticsearchバックエンドでMimizamインスタンスを作成"""
```

#### 使用例

```python
from mimizam import create_mimizam_elasticsearch

# Elasticsearch接続
with create_mimizam_elasticsearch(
    host="localhost",
    port=9200,
    index_name="music_fingerprints"
) as mimizam:
    # 分散検索システム
    pass
```

## コンテキストマネージャー

全てのMimizamインスタンスは、適切なリソース管理のためのコンテキストマネージャーとして使用できます。

### 基本的な使用

```python
with create_mimizam_sqlite("music.db") as mimizam:
    # データベース接続が自動的に管理される
    song_id = mimizam.add_song("song.wav", "Title", "Artist")
    result = mimizam.identify_audio("query.wav")
# ここで自動的にデータベース接続が閉じられる
```

### 手動リソース管理

```python
mimizam = create_mimizam_sqlite("music.db")
try:
    # 操作を実行
    song_id = mimizam.add_song("song.wav", "Title", "Artist")
finally:
    mimizam.close()  # 手動でリソースを解放
```

## 設定オプション

### 音声処理設定

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|----------|------|
| `n_fft` | int | 2048 | FFTウィンドウサイズ |
| `hop_length` | int | 512 | ホップ長（サンプル数） |
| `min_amplitude` | float | -60 | 最小振幅閾値 (dB) |
| `peak_neighborhood_size` | int | 20 | ピーク検出の近傍サイズ |
| `target_zone_size` | int | 5 | ターゲットゾーンサイズ |
| `time_range` | int | 200 | 時間範囲（フレーム数） |

### 適応処理設定

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|----------|------|
| `enable_adaptive_params` | bool | False | 適応パラメータ調整を有効化 |
| `adaptive_threshold_factor` | float | 1.5 | 適応閾値調整係数 |
| `adaptive_sensitivity` | float | 0.8 | 適応感度調整 |

### デバッグ設定

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|----------|------|
| `debug` | bool | False | デバッグモードを有効化 |
| `verbose` | bool | False | 詳細ログ出力を有効化 |
| `log_level` | str | "INFO" | ログレベル設定 |

## 実用的な使用パターン

### 基本的な楽曲識別

```python
from mimizam import create_mimizam_sqlite

def simple_identification():
    with create_mimizam_sqlite("music.db") as mimizam:
        # 楽曲追加
        song_id = mimizam.add_song("reference.wav", "Song Title", "Artist Name")
        
        # 音声識別
        result = mimizam.identify_audio("query.wav")
        
        if result:
            song, confidence = result
            print(f"識別結果: {song.title} by {song.artist} ({confidence:.2%})")
        else:
            print("楽曲を識別できませんでした")
```

### バッチ処理

```python
import glob
from pathlib import Path

def batch_processing():
    with create_mimizam_sqlite("library.db") as mimizam:
        # 音楽ライブラリの構築
        music_files = glob.glob("music/*.wav")
        
        for file_path in music_files:
            filename = Path(file_path).stem
            # ファイル名から情報を抽出
            if " - " in filename:
                artist, title = filename.split(" - ", 1)
            else:
                artist, title = "Unknown", filename
            
            try:
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"追加: {title} by {artist}")
            except Exception as e:
                print(f"エラー: {file_path} - {e}")
        
        # 統計表示
        stats = mimizam.get_database_stats()
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")
```

### 複数候補検索

```python
def multi_candidate_search():
    with create_mimizam_sqlite("library.db") as mimizam:
        # 複数の候補を検索
        results = mimizam.search_song("query.wav", min_confidence=0.1, top_k=5)
        
        if results:
            print("検索結果:")
            for i, result in enumerate(results, 1):
                song = result['song']
                confidence = result['confidence']
                time_alignment = result['time_alignment']
                
                print(f"{i}. {song.title} by {song.artist}")
                print(f"   信頼度: {confidence:.2%}")
                print(f"   時間オフセット: {time_alignment:.1f}秒")
        else:
            print("マッチする楽曲が見つかりませんでした")
```

### エラーハンドリング

```python
from mimizam import (
    create_mimizam_sqlite,
    AudioProcessingError,
    FingerprintGenerationError,
    DatabaseError
)

def robust_processing():
    try:
        with create_mimizam_sqlite("music.db") as mimizam:
            song_id = mimizam.add_song("song.wav", "Title", "Artist")
            result = mimizam.identify_audio("query.wav")
            
    except AudioProcessingError as e:
        print(f"音声処理エラー: {e}")
    except FingerprintGenerationError as e:
        print(f"指紋生成エラー: {e}")
    except DatabaseError as e:
        print(f"データベースエラー: {e}")
    except Exception as e:
        print(f"予期しないエラー: {e}")
```

## パフォーマンス設定

### 高速処理設定

```python
# 高速処理用設定
fast_mimizam = create_mimizam_sqlite(
    "fast_db.db",
    n_fft=1024,           # 小さなFFTサイズ
    hop_length=512,       # 大きなホップ長
    min_amplitude=-50,    # 緩い閾値
    enable_adaptive_params=True  # 適応最適化
)
```

### 高精度設定

```python
# 高精度処理用設定
precision_mimizam = create_mimizam_sqlite(
    "precision_db.db",
    n_fft=4096,           # 大きなFFTサイズ
    hop_length=256,       # 小さなホップ長
    min_amplitude=-70,    # 厳しい閾値
    peak_neighborhood_size=30,  # 大きな近傍サイズ
    debug=True            # デバッグ有効
)
```

## 関連ドキュメント

- [基本的な使用方法](./02_installation.md) - インストールとセットアップ
- [低レベルコンポーネント](./08_low_level_components.md) - 詳細なカスタマイゼーション
- [データベースバックエンド](./09_database_backends.md) - データベース設定
- [基本的な使用例](./14_basic_usage_examples.md) - 実践的なサンプルコード
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
