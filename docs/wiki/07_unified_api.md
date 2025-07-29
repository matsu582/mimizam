# 統合API (Mimizam) リファレンス

mimizamの統合APIは、すべてのデータベースバックエンドで一貫したインターフェースを提供します。開発者は複雑な低レベル実装を意識することなく、音声指紋システムを簡単に利用できます。

## 🚀 Mimizamクラス概要

### 基本的な使用パターン

```python
from mimizam import create_mimizam_sqlite

# コンテキストマネージャーとして使用（推奨）
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲追加
    song_id = mimizam.add_song("song.wav", "Song Title", "Artist Name")
    
    # 音声検索
    results = mimizam.search_song("query.wav")
    
    # 音声識別
    identified = mimizam.identify_audio("query.wav")
```

### 手動リソース管理

```python
# 手動でリソース管理する場合
mimizam = create_mimizam_sqlite("my_music.db")
try:
    # 処理
    song_id = mimizam.add_song("song.wav", "Song Title", "Artist Name")
finally:
    mimizam.close()  # リソースの解放
```

## 🏭 ファクトリ関数

### SQLite
```python
from mimizam import create_mimizam_sqlite

# 基本使用
mimizam = create_mimizam_sqlite("database.db")

# メモリ内データベース（テスト用）
mimizam = create_mimizam_sqlite(":memory:")

# カスタム設定
mimizam = create_mimizam_sqlite(
    db_path="custom.db",
    enable_adaptive_params=True,
    debug=True
)
```

### MySQL
```python
from mimizam import create_mimizam_mysql

# 基本接続
mimizam = create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)

# 詳細設定
mimizam = create_mimizam_mysql(
    host="db.example.com",
    port=3306,
    database="fingerprints_production",
    username="app_user",
    password="secure_password",
    charset="utf8mb4",
    enable_adaptive_params=True,
    debug=False
)
```

### PostgreSQL
```python
from mimizam import create_mimizam_postgresql

# 基本接続
mimizam = create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)

# SSL接続
mimizam = create_mimizam_postgresql(
    host="secure-db.example.com",
    port=5432,
    database="fingerprints_production",
    username="app_user",
    password="secure_password",
    sslmode="require",
    enable_adaptive_params=True
)
```

### Elasticsearch
```python
from mimizam import create_mimizam_elasticsearch

# 基本接続
mimizam = create_mimizam_elasticsearch(
    host="localhost",
    port=9200,
    index_name="audio_fingerprints"
)

# 認証付き接続
mimizam = create_mimizam_elasticsearch(
    host="elasticsearch.example.com",
    port=9200,
    index_name="audio_fingerprints_prod",
    username="elastic",
    password="password",
    use_ssl=True,
    verify_certs=True
)

# カスタムシャード設定
mimizam = create_mimizam_elasticsearch(
    host="localhost",
    port=9200,
    index_name="audio_fingerprints",
    es_songs_shards=2,
    es_songs_replicas=1,
    es_fingerprints_shards=5,
    es_fingerprints_replicas=1
)
```

## 📝 主要メソッド

### 楽曲管理

#### add_song()
```python
def add_song(self, file_path: str, title: str, artist: str, 
             album: str = None, meta: dict = None) -> int:
    """
    楽曲をデータベースに追加
    
    Args:
        file_path: 音声ファイルのパス
        title: 楽曲タイトル
        artist: アーティスト名
        album: アルバム名（オプション）
        meta: 追加メタデータ（オプション）
    
    Returns:
        int: 楽曲ID
    
    Raises:
        AudioProcessingError: 音声処理に失敗した場合
        DatabaseError: データベース操作に失敗した場合
    """
```

**使用例:**
```python
# 基本的な楽曲追加
song_id = mimizam.add_song(
    "music/song.wav", 
    "My Favorite Song", 
    "Great Artist"
)

# 詳細情報付きで追加
song_id = mimizam.add_song(
    "music/album_track.wav",
    "Track Title",
    "Artist Name",
    album="Album Name",
    meta={
        "genre": "Pop",
        "year": 2023,
        "duration": 180.5,
        "bitrate": 320
    }
)

print(f"楽曲が追加されました (ID: {song_id})")
```

#### get_song()
```python
def get_song(self, song_id: int) -> Song:
    """
    楽曲情報を取得
    
    Args:
        song_id: 楽曲ID
    
    Returns:
        Song: 楽曲オブジェクト
    
    Raises:
        DatabaseError: 楽曲が見つからない場合
    """
```

**使用例:**
```python
song = mimizam.get_song(1)
print(f"タイトル: {song.title}")
print(f"アーティスト: {song.artist}")
print(f"ファイルパス: {song.file_path}")
print(f"作成日時: {song.created_at}")
```

#### list_songs()
```python
def list_songs(self, limit: int = 100, offset: int = 0) -> List[Song]:
    """
    楽曲一覧を取得
    
    Args:
        limit: 取得件数の上限
        offset: 取得開始位置
    
    Returns:
        List[Song]: 楽曲リスト
    """
```

**使用例:**
```python
# 最初の10曲を取得
songs = mimizam.list_songs(limit=10)
for song in songs:
    print(f"{song.id}: {song.title} by {song.artist}")

# ページネーション
page_size = 20
page = 2
songs = mimizam.list_songs(limit=page_size, offset=(page-1)*page_size)
```

#### delete_song()
```python
def delete_song(self, song_id: int) -> bool:
    """
    楽曲を削除
    
    Args:
        song_id: 楽曲ID
    
    Returns:
        bool: 削除成功の場合True
    
    Raises:
        DatabaseError: 削除に失敗した場合
    """
```

**使用例:**
```python
# 楽曲削除
success = mimizam.delete_song(song_id=5)
if success:
    print("楽曲が削除されました")
else:
    print("削除に失敗しました")
```

### 音声検索・識別

#### search_song()
```python
def search_song(self, query_path: str, min_confidence: float = 0.1, 
                top_k: int = 10, scoring_method: str = 'hybrid') -> List[Dict]:
    """
    音声検索（複数結果）
    
    Args:
        query_path: クエリ音声ファイルのパス
        min_confidence: 最小信頼度閾値
        top_k: 返す結果の最大数
        scoring_method: スコアリング方式 ('hybrid', 'histogram', 'detailed')
    
    Returns:
        List[Dict]: 検索結果リスト
            [{'song': Song, 'confidence': float, 'time_alignment': float}, ...]
    
    Raises:
        AudioProcessingError: 音声処理に失敗した場合
        DatabaseError: データベース検索に失敗した場合
    """
```

**使用例:**
```python
# 基本的な音声検索
results = mimizam.search_song("query.wav")
for result in results:
    song = result['song']
    confidence = result['confidence']
    alignment = result['time_alignment']
    print(f"発見: {song.title} by {song.artist}")
    print(f"信頼度: {confidence:.2%}, 時間オフセット: {alignment:.1f}秒")

# 高精度検索
results = mimizam.search_song(
    "query.wav",
    min_confidence=0.5,      # 高い信頼度閾値
    top_k=5,                 # 上位5件
    scoring_method='detailed' # 詳細スコアリング
)

# 高速検索
results = mimizam.search_song(
    "query.wav",
    min_confidence=0.2,      # 低い信頼度閾値
    top_k=3,                 # 上位3件
    scoring_method='histogram' # 高速スコアリング
)
```

#### identify_audio()
```python
def identify_audio(self, query_path: str, min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
    """
    音声識別（最も可能性の高い楽曲）
    
    Args:
        query_path: クエリ音声ファイルのパス
        min_confidence: 最小信頼度閾値
    
    Returns:
        Optional[Tuple[Song, float]]: (楽曲, 信頼度) または None
    
    Raises:
        AudioProcessingError: 音声処理に失敗した場合
        DatabaseError: データベース検索に失敗した場合
    """
```

**使用例:**
```python
# 音声識別
identified = mimizam.identify_audio("unknown_song.wav")
if identified:
    song, confidence = identified
    print(f"識別結果: {song.title} by {song.artist}")
    print(f"信頼度: {confidence:.2%}")
else:
    print("楽曲を識別できませんでした")

# カスタム信頼度閾値
identified = mimizam.identify_audio("query.wav", min_confidence=0.6)
if identified:
    song, confidence = identified
    print(f"高信頼度で識別: {song.title} (信頼度: {confidence:.2%})")
```

### データベース管理

#### get_database_stats()
```python
def get_database_stats(self) -> Dict[str, Any]:
    """
    データベース統計情報を取得
    
    Returns:
        Dict[str, Any]: 統計情報
            {
                'song_count': int,
                'fingerprint_count': int,
                'database_size': int,  # バイト
                'avg_fingerprints_per_song': float
            }
    """
```

**使用例:**
```python
stats = mimizam.get_database_stats()
print(f"楽曲数: {stats['song_count']:,}")
print(f"指紋数: {stats['fingerprint_count']:,}")
print(f"データベースサイズ: {stats['database_size'] / 1024 / 1024:.1f} MB")
print(f"楽曲あたり平均指紋数: {stats['avg_fingerprints_per_song']:.1f}")
```

#### optimize_database()
```python
def optimize_database(self) -> bool:
    """
    データベースを最適化
    
    Returns:
        bool: 最適化成功の場合True
    """
```

**使用例:**
```python
# データベース最適化実行
success = mimizam.optimize_database()
if success:
    print("データベースの最適化が完了しました")
```

## 🔧 設定とカスタマイズ

### 音声処理設定

```python
# カスタム音声処理設定
mimizam = create_mimizam_sqlite(
    "custom.db",
    # 音声指紋設定
    n_fft=4096,              # FFTサイズ
    hop_length=256,          # ホップ長
    min_amplitude=-60,       # 最小振幅閾値
    peak_neighborhood_size=20, # ピーク近傍サイズ
    
    # ハッシュ生成設定
    target_zone_t=1.8,       # ターゲットゾーン時間
    target_zone_f=1000,      # ターゲットゾーン周波数
    max_time_delta=200,      # 最大時間差
    
    # 最適化設定
    enable_adaptive_params=True,  # 適応パラメータ
    use_numba_optimization=True,  # Numba最適化
    
    # デバッグ設定
    debug=True,              # デバッグモード
    verbose=True             # 詳細ログ
)
```

### マッチング設定

```python
# カスタムマッチング設定
mimizam = create_mimizam_sqlite(
    "matching.db",
    # スコアリング設定
    default_scoring_method='hybrid',  # デフォルトスコアリング方式
    min_confidence_threshold=0.2,     # デフォルト信頼度閾値
    
    # 時間・周波数許容範囲
    time_tolerance=0.1,      # 時間許容範囲（秒）
    freq_tolerance=50,       # 周波数許容範囲（Hz）
    
    # スケール変動対応
    time_scale_factors=[0.8, 0.9, 1.0, 1.1, 1.2],  # 時間スケール
    freq_scale_factors=[0.95, 1.0, 1.05],           # 周波数スケール
    
    # パフォーマンス設定
    max_matches_per_hash=100,  # ハッシュあたり最大マッチ数
    enable_parallel_matching=True  # 並列マッチング
)
```

## 🎯 実用的な使用例

### 1. 音楽ライブラリの構築

```python
import glob
from pathlib import Path

def build_music_library(music_dir: str, db_path: str):
    """音楽ライブラリを構築"""
    with create_mimizam_sqlite(db_path) as mimizam:
        audio_files = glob.glob(f"{music_dir}/**/*.wav", recursive=True)
        
        for i, file_path in enumerate(audio_files, 1):
            try:
                # ファイル名から情報を抽出
                path_obj = Path(file_path)
                title = path_obj.stem
                artist = path_obj.parent.name
                
                # 楽曲追加
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"[{i}/{len(audio_files)}] 追加完了: {title} (ID: {song_id})")
                
            except Exception as e:
                print(f"エラー: {file_path} - {e}")
        
        # 統計情報表示
        stats = mimizam.get_database_stats()
        print(f"\n構築完了:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")

# 使用例
build_music_library("./music_collection", "my_library.db")
```

### 2. バッチ音声識別

```python
def batch_identify(query_dir: str, db_path: str, output_file: str):
    """複数音声ファイルの一括識別"""
    import csv
    
    with create_mimizam_sqlite(db_path) as mimizam:
        query_files = glob.glob(f"{query_dir}/*.wav")
        results = []
        
        for query_file in query_files:
            try:
                identified = mimizam.identify_audio(query_file, min_confidence=0.3)
                if identified:
                    song, confidence = identified
                    results.append({
                        'query_file': query_file,
                        'identified_title': song.title,
                        'identified_artist': song.artist,
                        'confidence': confidence,
                        'status': 'success'
                    })
                else:
                    results.append({
                        'query_file': query_file,
                        'identified_title': '',
                        'identified_artist': '',
                        'confidence': 0.0,
                        'status': 'not_found'
                    })
            except Exception as e:
                results.append({
                    'query_file': query_file,
                    'identified_title': '',
                    'identified_artist': '',
                    'confidence': 0.0,
                    'status': f'error: {e}'
                })
        
        # CSV出力
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        
        print(f"識別結果を {output_file} に保存しました")

# 使用例
batch_identify("./queries", "my_library.db", "identification_results.csv")
```

### 3. リアルタイム音声監視

```python
import time
import threading
from queue import Queue

def monitor_audio_files(db_path: str, audio_files: list):
    """音声ファイルの監視と識別"""
    
    mimizam = create_mimizam_sqlite(db_path)
    
    for audio_path in audio_files:
        try:
            # 音声識別を実行
            results = mimizam.search_song(audio_path)
            
            if results:
                best_match = results[0]
                song = best_match['song']
                confidence = best_match['confidence']
                print(f"🎵 識別: {song['title']} by {song['artist']} (信頼度: {confidence:.2%})")
            else:
                print(f"❓ 未識別: {audio_path}")
                
        except Exception as e:
            print(f"❌ エラー: {audio_path} - {e}")
    
    mimizam.close()

# 使用例
audio_files = ["live_audio_1.wav", "live_audio_2.wav", "query_audio.wav"]
monitor_audio_files("my_library.db", audio_files)
```

## 🚨 エラーハンドリング

### 例外の種類

```python
from mimizam import (
    MimizamError,           # 基底例外
    DatabaseError,          # データベース関連エラー
    ConnectionError,        # 接続エラー
    QueryError,             # クエリエラー
    AudioProcessingError,   # 音声処理エラー
    FingerprintGenerationError,  # 指紋生成エラー
    ConfigurationError,     # 設定エラー
    ValidationError         # 検証エラー
)
```

### 包括的エラーハンドリング

```python
def safe_audio_processing(mimizam, audio_path: str):
    """安全な音声処理"""
    try:
        # 楽曲追加
        song_id = mimizam.add_song(audio_path, "Unknown", "Unknown")
        print(f"楽曲追加成功 (ID: {song_id})")
        
        # 音声識別
        identified = mimizam.identify_audio(audio_path)
        if identified:
            song, confidence = identified
            print(f"識別成功: {song.title} (信頼度: {confidence:.2%})")
        
    except AudioProcessingError as e:
        print(f"音声処理エラー: {e}")
        # 音声ファイルの形式や品質に問題がある可能性
        
    except FingerprintGenerationError as e:
        print(f"指紋生成エラー: {e}")
        # 音声が短すぎるか、無音の可能性
        
    except DatabaseError as e:
        print(f"データベースエラー: {e}")
        # データベース接続や操作に問題がある可能性
        
    except ValidationError as e:
        print(f"検証エラー: {e}")
        # 入力パラメータに問題がある可能性
        
    except MimizamError as e:
        print(f"Mimizamエラー: {e}")
        # その他のシステムエラー
        
    except Exception as e:
        print(f"予期しないエラー: {e}")
        # システム外のエラー
```

## 🔗 関連ドキュメント

- [低レベルAPI](./08_lowlevel_api.md) - 詳細な制御が必要な場合
- [データ構造](./09_data_structures.md) - Song、Fingerprint、Peakオブジェクト
- [データベース設定](./10_database_setup.md) - バックエンド詳細設定
- [実装例](./16_basic_examples.md) - 実践的なサンプルコード
- [トラブルシューティング](./21_debugging.md) - 問題解決ガイド
