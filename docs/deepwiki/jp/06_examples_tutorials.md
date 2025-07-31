# 実例とチュートリアル

> 関連するソースファイル

このページでは、mimizam音声指紋システムの様々な音声処理タスクに対する実践的な例とチュートリアルを提供します。例では基本的な使用パターン、動画処理ワークフロー、実際のコードを使用したパフォーマンス最適化技術をカバーしています。

詳細なAPIドキュメントについては、[高レベルAPI](./04_1_high_level_api.md)と[低レベルコンポーネント](./04_2_low_level_components.md)を参照してください。データベース設定の詳細については、[データベースバックエンド](./05_database_backends.md)を参照してください。

## 基本的な使用例

mimizamを始める最も簡単な方法は、高レベルファクトリ関数と**Mimizam**クラスを使用することです。基本的なワークフローには、データベースインスタンスの作成、楽曲の追加、マッチの検索という3つの主要な操作が含まれます。

### データベースの作成と使用

#### 基本的なデータベース操作ワークフロー

コアパターンには、データベース作成、楽曲追加、音声検索・識別という3つの主要な操作が含まれます。

**Sources:** `examples/mimizam_demo.py` 25-91

### 基本的なコードパターン

| 操作 | メソッド | 入力 | 出力 |
|------|---------|------|------|
| 楽曲追加 | `add_song()` | 音声パス、楽曲名、メタデータ | 楽曲ID |
| 音声識別 | `identify_audio()` | 音声パス、信頼度 | 最適マッチまたはNone |
| 楽曲情報取得 | `get_song_info()` | 楽曲ID | 楽曲詳細辞書 |
| 楽曲削除 | `delete_song()` | 楽曲ID | 削除成功フラグ |

### 複数データベースバックエンド設定

#### SQLiteバックエンド（開発・テスト用）

```python
from mimizam import create_mimizam_sqlite

# 基本設定
mimizam = create_mimizam_sqlite("music_database.db")

# カスタムパラメータ
mimizam = create_mimizam_sqlite(
    "music_database.db",
    sample_rate=22050,
    peak_threshold=0.15,
    target_zone_size=5
)
```

#### MySQLバックエンド（本番環境用）

```python
from mimizam import create_mimizam_mysql

mimizam = create_mimizam_mysql(
    host="localhost",
    user="mimizam_user", 
    password="secure_password",
    database="music_db",
    peak_threshold=0.12,
    min_peak_distance=8
)
```

#### PostgreSQLバックエンド（高性能用途）

```python
from mimizam import create_mimizam_postgresql

mimizam = create_mimizam_postgresql(
    host="postgres.example.com",
    user="mimizam_user",
    password="secure_password", 
    database="music_db",
    port=5432,
    sslmode="require"
)
```

#### Elasticsearchバックエンド（大規模検索用）

```python
from mimizam import create_mimizam_elasticsearch

# 単一ノード
mimizam = create_mimizam_elasticsearch(
    hosts="localhost:9200",
    index_name="music_fingerprints"
)

# 複数ノードクラスター
mimizam = create_mimizam_elasticsearch(
    hosts=[
        {"host": "es1.example.com", "port": 9200},
        {"host": "es2.example.com", "port": 9200}
    ],
    index_name="music_fingerprints"
)
```

## 動画処理

### 動画音声抽出ワークフロー

動画ファイルから音声を抽出し、音声指紋を生成するための包括的なワークフローです。

```python
import subprocess
import tempfile
import os
from mimizam import create_mimizam_sqlite

def extract_audio_from_video(video_path, output_path=None):
    """動画から音声を抽出"""
    if output_path is None:
        output_path = tempfile.mktemp(suffix='.wav')
    
    # FFmpegを使用して音声抽出
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn', '-acodec', 'pcm_s16le',
        '-ar', '22050', '-ac', '1',
        output_path, '-y'
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path

def process_video_library(video_dir, database_path):
    """動画ライブラリを処理"""
    mimizam = create_mimizam_sqlite(database_path)
    
    for filename in os.listdir(video_dir):
        if filename.endswith(('.mp4', '.avi', '.mkv', '.mov')):
            video_path = os.path.join(video_dir, filename)
            song_name = os.path.splitext(filename)[0]
            
            try:
                # 音声抽出
                audio_path = extract_audio_from_video(video_path)
                
                # 指紋生成と保存
                song_id = mimizam.add_song(audio_path, song_name=song_name)
                print(f"処理完了: {song_name} (ID: {song_id})")
                
                # 一時ファイル削除
                os.unlink(audio_path)
                
            except Exception as e:
                print(f"処理エラー {filename}: {e}")

# 使用例
process_video_library("/path/to/videos", "video_music.db")
```

### バッチ動画処理

```python
import concurrent.futures
from pathlib import Path

def process_video_batch(video_paths, database_path, max_workers=4):
    """並列動画処理"""
    mimizam = create_mimizam_sqlite(database_path)
    
    def process_single_video(video_path):
        try:
            audio_path = extract_audio_from_video(str(video_path))
            song_id = mimizam.add_song(audio_path, song_name=video_path.stem)
            os.unlink(audio_path)
            return f"成功: {video_path.name}"
        except Exception as e:
            return f"エラー {video_path.name}: {e}"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_video, video_paths))
    
    return results
```

## パフォーマンス最適化

### 適応的パラメータ設定

```python
from mimizam import create_mimizam_sqlite

# 高精度設定（処理時間増加）
mimizam_high_precision = create_mimizam_sqlite(
    "music_db.db",
    peak_threshold=0.1,        # より低い閾値でより多くのピークを検出
    min_peak_distance=5,       # より密なピーク検出
    target_zone_size=8,        # より大きなターゲットゾーン
    n_fft=4096                 # より高い周波数解像度
)

# 高速設定（精度若干低下）
mimizam_fast = create_mimizam_sqlite(
    "music_db.db", 
    peak_threshold=0.2,        # より高い閾値で処理を高速化
    min_peak_distance=15,      # より粗いピーク検出
    target_zone_size=3,        # より小さなターゲットゾーン
    n_fft=1024                 # より低い周波数解像度
)
```

### バッチ処理最適化

```python
import time
from pathlib import Path

def optimized_batch_processing(music_dir, database_path):
    """最適化されたバッチ処理"""
    mimizam = create_mimizam_sqlite(database_path)
    
    # 処理統計
    start_time = time.time()
    processed_count = 0
    error_count = 0
    
    music_files = list(Path(music_dir).glob('**/*.{mp3,wav,flac,m4a}'))
    total_files = len(music_files)
    
    print(f"処理開始: {total_files}ファイル")
    
    for i, music_file in enumerate(music_files):
        try:
            # 進捗表示
            if i % 10 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total_files - i) / rate if rate > 0 else 0
                print(f"進捗: {i}/{total_files} ({rate:.1f}ファイル/秒, ETA: {eta:.0f}秒)")
            
            # 楽曲処理
            song_id = mimizam.add_song(
                str(music_file),
                song_name=music_file.stem,
                artist=music_file.parent.name  # フォルダ名をアーティストとして使用
            )
            processed_count += 1
            
        except Exception as e:
            print(f"エラー {music_file.name}: {e}")
            error_count += 1
    
    # 最終統計
    total_time = time.time() - start_time
    print(f"\n処理完了:")
    print(f"  処理済み: {processed_count}ファイル")
    print(f"  エラー: {error_count}ファイル") 
    print(f"  総時間: {total_time:.1f}秒")
    print(f"  平均速度: {processed_count/total_time:.1f}ファイル/秒")

# 使用例
optimized_batch_processing("/path/to/music", "optimized_music.db")
```

### パフォーマンス監視

```python
import psutil
import time
from mimizam import create_mimizam_sqlite

def monitor_performance(func, *args, **kwargs):
    """パフォーマンス監視デコレータ"""
    # 開始時のリソース使用量
    process = psutil.Process()
    start_memory = process.memory_info().rss / 1024 / 1024  # MB
    start_cpu = process.cpu_percent()
    start_time = time.time()
    
    # 関数実行
    result = func(*args, **kwargs)
    
    # 終了時のリソース使用量
    end_time = time.time()
    end_memory = process.memory_info().rss / 1024 / 1024  # MB
    end_cpu = process.cpu_percent()
    
    # 統計表示
    print(f"\nパフォーマンス統計:")
    print(f"  実行時間: {end_time - start_time:.2f}秒")
    print(f"  メモリ使用量: {start_memory:.1f}MB → {end_memory:.1f}MB")
    print(f"  メモリ増加: {end_memory - start_memory:.1f}MB")
    print(f"  CPU使用率: {end_cpu:.1f}%")
    
    return result

# 使用例
@monitor_performance
def add_large_song_collection():
    mimizam = create_mimizam_sqlite("performance_test.db")
    # 大量の楽曲を追加...
    return mimizam

result = add_large_song_collection()
```

## 関連ドキュメント

- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
- [動画処理](./06_2_video_processing.md) - 動画からの音声抽出と指紋生成
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術
- [高レベルAPI](./04_1_high_level_api.md) - 統合インターフェース
- [データベースバックエンド](./05_database_backends.md) - データベース設定と比較
