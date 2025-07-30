# 基本的な使用例

mimizamの実践的な使用例を、初心者から上級者まで段階的に紹介します。実際のプロジェクトで使用できるサンプルコードを中心に説明します。

高レベルAPIの詳細については、[高レベルAPI](./07_high_level_api.md)を参照してください。データベース設定については、[データベースバックエンド](./09_database_backends.md)を参照してください。

## 🎯 この章で学べること

- 基本的な楽曲追加と識別
- 複数のデータベースバックエンドの使用
- エラーハンドリングとデバッグ
- バッチ処理と大規模データ管理
- パフォーマンス最適化の実践

## 🚀 基本的な使用例

### 1. 最初の楽曲識別

```python
from mimizam import create_mimizam_sqlite

def simple_identification():
    """最も基本的な楽曲識別の例"""
    with create_mimizam_sqlite("my_music.db") as mimizam:
        # 楽曲をデータベースに追加
        song_id = mimizam.add_song(
            file_path="reference_song.wav",
            title="My Favorite Song",
            artist="Great Artist"
        )
        print(f"楽曲追加完了: ID {song_id}")
        
        # 音声クリップから楽曲を識別
        result = mimizam.identify_audio("query_clip.wav")
        
        if result:
            song, confidence = result
            print(f"識別成功: {song.title} by {song.artist}")
            print(f"信頼度: {confidence:.2%}")
        else:
            print("楽曲を識別できませんでした")

if __name__ == "__main__":
    simple_identification()
```

### 2. 複数楽曲の管理

```python
import glob
from pathlib import Path

def build_music_library():
    """音楽ライブラリの構築"""
    with create_mimizam_sqlite("music_library.db") as mimizam:
        # 音楽フォルダから楽曲を一括追加
        music_files = glob.glob("music_collection/*.wav")
        
        for file_path in music_files:
            filename = Path(file_path).stem
            
            # ファイル名から情報を抽出
            if " - " in filename:
                artist, title = filename.split(" - ", 1)
            else:
                artist, title = "Unknown Artist", filename
            
            try:
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"✓ 追加: {title} by {artist}")
            except Exception as e:
                print(f"✗ エラー: {filename} - {e}")
        
        # ライブラリ統計を表示
        stats = mimizam.get_database_stats()
        print(f"\nライブラリ統計:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")

if __name__ == "__main__":
    build_music_library()
```

### 3. 基本的な音声検索

```python
def search_audio_clips():
    """音声クリップの検索"""
    with create_mimizam_sqlite("music_library.db") as mimizam:
        # 複数のクエリファイルをテスト
        query_files = [
            "test_clips/clip1.wav",
            "test_clips/clip2.wav", 
            "test_clips/clip3.wav"
        ]
        
        for query_file in query_files:
            print(f"\n検索中: {query_file}")
            
            # 複数の候補を検索
            results = mimizam.search_song(
                query_file, 
                min_confidence=0.1, 
                top_k=3
            )
            
            if results:
                print("検索結果:")
                for i, result in enumerate(results, 1):
                    song = result['song']
                    confidence = result['confidence']
                    print(f"  {i}. {song.title} by {song.artist} ({confidence:.1%})")
            else:
                print("  マッチする楽曲が見つかりませんでした")

if __name__ == "__main__":
    search_audio_clips()
```

## 🔧 高精度識別

### 4. 高精度設定での識別

```python
def high_precision_identification():
    """高精度設定での楽曲識別"""
    # 高精度パラメータでmimizamを作成
    with create_mimizam_sqlite(
        "precision_music.db",
        n_fft=4096,           # 大きなFFTサイズ
        hop_length=256,       # 小さなホップ長
        min_amplitude=-70,    # 厳しい振幅閾値
        peak_neighborhood_size=30,  # 大きな近傍サイズ
        enable_adaptive_params=True  # 適応パラメータ有効
    ) as mimizam:
        
        # 高品質音声ファイルを追加
        song_id = mimizam.add_song(
            "high_quality_song.wav",
            "High Quality Song",
            "Precision Artist"
        )
        
        # 短いクリップでも高精度識別
        result = mimizam.identify_audio("short_clip_5sec.wav")
        
        if result:
            song, confidence = result
            print(f"高精度識別: {song.title}")
            print(f"信頼度: {confidence:.3%}")
        else:
            print("高精度設定でも識別できませんでした")

if __name__ == "__main__":
    high_precision_identification()
```

### 5. 適応パラメータの活用

```python
def adaptive_parameter_example():
    """適応パラメータ機能の活用"""
    with create_mimizam_sqlite(
        "adaptive_music.db",
        enable_adaptive_params=True,
        debug=True  # デバッグ情報を表示
    ) as mimizam:
        
        # 異なる音質の楽曲を追加
        test_songs = [
            ("clean_studio_recording.wav", "Studio Song", "Clean Artist"),
            ("live_recording.wav", "Live Song", "Live Artist"),
            ("compressed_mp3.wav", "Compressed Song", "Digital Artist")
        ]
        
        for file_path, title, artist in test_songs:
            song_id = mimizam.add_song(file_path, title, artist)
            print(f"追加: {title} (ID: {song_id})")
        
        # 各楽曲タイプでの識別テスト
        query_files = [
            "clean_query.wav",
            "noisy_query.wav",
            "compressed_query.wav"
        ]
        
        for query_file in query_files:
            print(f"\n識別テスト: {query_file}")
            result = mimizam.identify_audio(query_file)
            
            if result:
                song, confidence = result
                print(f"結果: {song.title} ({confidence:.2%})")
            else:
                print("識別失敗")

if __name__ == "__main__":
    adaptive_parameter_example()
```

## 🗄️ データベースバックエンド比較

### 6. 異なるデータベースバックエンドの比較

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql
)
import time

def compare_database_backends():
    """異なるデータベースバックエンドの性能比較"""
    
    # テストデータ
    test_songs = [
        ("song1.wav", "Song 1", "Artist 1"),
        ("song2.wav", "Song 2", "Artist 2"),
        ("song3.wav", "Song 3", "Artist 3")
    ]
    
    # SQLiteテスト
    print("SQLiteバックエンドテスト:")
    start_time = time.time()
    with create_mimizam_sqlite("test_sqlite.db") as mimizam:
        for file_path, title, artist in test_songs:
            mimizam.add_song(file_path, title, artist)
        
        result = mimizam.identify_audio("query.wav")
    sqlite_time = time.time() - start_time
    print(f"SQLite処理時間: {sqlite_time:.2f}秒")
    
    # MySQLテスト（設定が利用可能な場合）
    try:
        print("\nMySQLバックエンドテスト:")
        start_time = time.time()
        with create_mimizam_mysql(
            host="localhost",
            database="test_music",
            username="test_user",
            password="test_password"
        ) as mimizam:
            for file_path, title, artist in test_songs:
                mimizam.add_song(file_path, title, artist)
            
            result = mimizam.identify_audio("query.wav")
        mysql_time = time.time() - start_time
        print(f"MySQL処理時間: {mysql_time:.2f}秒")
        
    except Exception as e:
        print(f"MySQL接続エラー: {e}")
    
    # PostgreSQLテスト（設定が利用可能な場合）
    try:
        print("\nPostgreSQLバックエンドテスト:")
        start_time = time.time()
        with create_mimizam_postgresql(
            host="localhost",
            database="test_music",
            username="test_user",
            password="test_password"
        ) as mimizam:
            for file_path, title, artist in test_songs:
                mimizam.add_song(file_path, title, artist)
            
            result = mimizam.identify_audio("query.wav")
        postgresql_time = time.time() - start_time
        print(f"PostgreSQL処理時間: {postgresql_time:.2f}秒")
        
    except Exception as e:
        print(f"PostgreSQL接続エラー: {e}")

if __name__ == "__main__":
    compare_database_backends()
```

## 🛡️ エラーハンドリング

### 7. 堅牢なエラーハンドリング

```python
from mimizam import (
    create_mimizam_sqlite,
    AudioProcessingError,
    FingerprintGenerationError,
    DatabaseError
)
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def robust_audio_processing():
    """堅牢なエラーハンドリングを含む音声処理"""
    
    try:
        with create_mimizam_sqlite("robust_music.db") as mimizam:
            
            # 楽曲追加時のエラーハンドリング
            song_files = [
                "valid_song.wav",
                "corrupted_file.wav",  # 破損ファイル
                "unsupported_format.mp3",  # 未対応形式
                "missing_file.wav"  # 存在しないファイル
            ]
            
            successful_additions = 0
            
            for file_path in song_files:
                try:
                    song_id = mimizam.add_song(
                        file_path,
                        f"Song from {file_path}",
                        "Test Artist"
                    )
                    logger.info(f"✓ 楽曲追加成功: {file_path} (ID: {song_id})")
                    successful_additions += 1
                    
                except AudioProcessingError as e:
                    logger.error(f"✗ 音声処理エラー: {file_path} - {e}")
                    
                except FingerprintGenerationError as e:
                    logger.error(f"✗ 指紋生成エラー: {file_path} - {e}")
                    
                except FileNotFoundError as e:
                    logger.error(f"✗ ファイル未発見: {file_path}")
                    
                except Exception as e:
                    logger.error(f"✗ 予期しないエラー: {file_path} - {e}")
            
            print(f"\n楽曲追加結果: {successful_additions}/{len(song_files)} 成功")
            
            # 識別時のエラーハンドリング
            query_files = [
                "valid_query.wav",
                "too_short_query.wav",  # 短すぎるクエリ
                "silent_query.wav"      # 無音クエリ
            ]
            
            for query_file in query_files:
                try:
                    result = mimizam.identify_audio(query_file)
                    
                    if result:
                        song, confidence = result
                        logger.info(f"✓ 識別成功: {query_file} -> {song.title} ({confidence:.2%})")
                    else:
                        logger.info(f"○ 識別結果なし: {query_file}")
                        
                except AudioProcessingError as e:
                    logger.error(f"✗ クエリ処理エラー: {query_file} - {e}")
                    
                except Exception as e:
                    logger.error(f"✗ 識別エラー: {query_file} - {e}")
    
    except DatabaseError as e:
        logger.error(f"データベースエラー: {e}")
        
    except Exception as e:
        logger.error(f"システムエラー: {e}")

if __name__ == "__main__":
    robust_audio_processing()
```

## 📊 バッチ処理と統計

### 8. 大規模バッチ処理

```python
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def batch_processing_example():
    """大規模音楽コレクションのバッチ処理"""
    
    def process_song_batch(song_batch, batch_id):
        """楽曲バッチの処理"""
        with create_mimizam_sqlite(f"batch_{batch_id}.db") as mimizam:
            results = []
            
            for file_path, title, artist in song_batch:
                try:
                    start_time = time.time()
                    song_id = mimizam.add_song(file_path, title, artist)
                    processing_time = time.time() - start_time
                    
                    results.append({
                        'file_path': file_path,
                        'song_id': song_id,
                        'processing_time': processing_time,
                        'status': 'success'
                    })
                    
                except Exception as e:
                    results.append({
                        'file_path': file_path,
                        'error': str(e),
                        'status': 'error'
                    })
            
            return results
    
    # 大量の楽曲ファイルを準備
    all_songs = []
    music_dir = "large_music_collection"
    
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            if file.endswith('.wav'):
                file_path = os.path.join(root, file)
                filename = os.path.splitext(file)[0]
                
                if " - " in filename:
                    artist, title = filename.split(" - ", 1)
                else:
                    artist, title = "Unknown", filename
                
                all_songs.append((file_path, title, artist))
    
    print(f"処理対象楽曲数: {len(all_songs)}")
    
    # バッチに分割
    batch_size = 100
    batches = [all_songs[i:i + batch_size] for i in range(0, len(all_songs), batch_size)]
    
    # 並列処理
    all_results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_batch = {
            executor.submit(process_song_batch, batch, i): i 
            for i, batch in enumerate(batches)
        }
        
        for future in as_completed(future_to_batch):
            batch_id = future_to_batch[future]
            try:
                batch_results = future.result()
                all_results.extend(batch_results)
                print(f"バッチ {batch_id} 完了: {len(batch_results)} 楽曲処理")
                
            except Exception as e:
                print(f"バッチ {batch_id} エラー: {e}")
    
    # 結果統計
    successful = [r for r in all_results if r['status'] == 'success']
    failed = [r for r in all_results if r['status'] == 'error']
    
    print(f"\n処理結果:")
    print(f"成功: {len(successful)} 楽曲")
    print(f"失敗: {len(failed)} 楽曲")
    
    if successful:
        avg_time = sum(r['processing_time'] for r in successful) / len(successful)
        print(f"平均処理時間: {avg_time:.2f}秒/楽曲")

if __name__ == "__main__":
    batch_processing_example()
```

### 9. パフォーマンス監視

```python
def performance_monitoring_example():
    """パフォーマンス監視の例"""
    
    with create_mimizam_sqlite("performance_test.db", debug=True) as mimizam:
        
        # テスト楽曲追加
        test_files = [f"test_song_{i}.wav" for i in range(10)]
        
        print("楽曲追加パフォーマンス:")
        for file_path in test_files:
            start_time = time.time()
            
            try:
                song_id = mimizam.add_song(
                    file_path,
                    f"Test Song {file_path}",
                    "Performance Artist"
                )
                
                add_time = time.time() - start_time
                print(f"{file_path}: {add_time:.3f}秒")
                
            except Exception as e:
                print(f"{file_path}: エラー - {e}")
        
        # データベース統計
        stats = mimizam.get_database_stats()
        print(f"\nデータベース統計:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")
        
        # パフォーマンス統計（利用可能な場合）
        if hasattr(mimizam, 'get_performance_stats'):
            perf_stats = mimizam.get_performance_stats()
            print(f"\nパフォーマンス統計:")
            for metric, value in perf_stats.items():
                print(f"{metric}: {value}")
        
        # 識別パフォーマンステスト
        print(f"\n識別パフォーマンス:")
        query_files = ["query1.wav", "query2.wav", "query3.wav"]
        
        for query_file in query_files:
            start_time = time.time()
            
            try:
                result = mimizam.identify_audio(query_file)
                identify_time = time.time() - start_time
                
                if result:
                    song, confidence = result
                    print(f"{query_file}: {identify_time:.3f}秒 -> {song.title} ({confidence:.1%})")
                else:
                    print(f"{query_file}: {identify_time:.3f}秒 -> 識別失敗")
                    
            except Exception as e:
                print(f"{query_file}: エラー - {e}")

if __name__ == "__main__":
    performance_monitoring_example()
```

## 🔗 関連ドキュメント

- [高レベルAPI](./07_high_level_api.md) - Mimizamクラスの詳細
- [データベースバックエンド](./09_database_backends.md) - データベース選択ガイド
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
- [動画処理](./15_video_processing.md) - 動画からの音声抽出
- [よくある質問（FAQ）](./19_faq.md) - トラブルシューティング
