# 基本的な使用例

mimizamの実践的な使用例を、初心者から上級者まで段階的に紹介します。実際のプロジェクトで使用できるサンプルコードを中心に説明します。

## 🎯 この章で学べること

- すぐに使える実用的なコード例
- 一般的な使用パターンの実装方法
- エラーハンドリングとベストプラクティス
- 性能を考慮した実装のコツ

## 🚀 初心者向け例

### 1. 最初の音声指紋システム

```python
from mimizam import create_mimizam_sqlite

# 最もシンプルな使用例
def simple_music_identification():
    # SQLiteデータベースを作成
    with create_mimizam_sqlite("my_first_music_db.db") as mimizam:
        # 楽曲をデータベースに追加
        print("楽曲を追加中...")
        song_id = mimizam.add_song(
            "music/favorite_song.wav", 
            "My Favorite Song", 
            "Great Artist"
        )
        print(f"楽曲が追加されました (ID: {song_id})")
        
        # 音声を識別
        print("音声を識別中...")
        identified = mimizam.identify_audio("query/unknown_song.wav")
        
        if identified:
            song, confidence = identified
            print(f"🎵 識別成功!")
            print(f"楽曲: {song.title}")
            print(f"アーティスト: {song.artist}")
            print(f"信頼度: {confidence:.2%}")
        else:
            print("❓ 楽曲を識別できませんでした")

# 実行
simple_music_identification()
```

### 2. 複数楽曲の管理

```python
import glob
from pathlib import Path

def build_small_library():
    """小規模音楽ライブラリの構築"""
    with create_mimizam_sqlite("small_library.db") as mimizam:
        # 音楽フォルダから楽曲を追加
        music_files = glob.glob("music/*.wav")
        
        print(f"{len(music_files)}個の音楽ファイルを処理中...")
        
        for file_path in music_files:
            try:
                # ファイル名から楽曲情報を抽出
                filename = Path(file_path).stem
                # "Artist - Title.wav" 形式を想定
                if " - " in filename:
                    artist, title = filename.split(" - ", 1)
                else:
                    artist = "Unknown Artist"
                    title = filename
                
                # 楽曲追加
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"✅ 追加: {title} by {artist} (ID: {song_id})")
                
            except Exception as e:
                print(f"❌ エラー: {file_path} - {e}")
        
        # データベース統計を表示
        stats = mimizam.get_database_stats()
        print(f"\n📊 ライブラリ統計:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")
        print(f"楽曲あたり平均指紋数: {stats['avg_fingerprints_per_song']:.1f}")

# 実行
build_small_library()
```

### 3. 音声検索の基本

```python
def basic_audio_search():
    """基本的な音声検索"""
    with create_mimizam_sqlite("small_library.db") as mimizam:
        query_file = "queries/humming.wav"
        
        print(f"🔍 音声検索中: {query_file}")
        
        # 複数の候補を検索
        results = mimizam.search_song(
            query_file,
            min_confidence=0.2,  # 低い閾値で幅広く検索
            top_k=5              # 上位5件を取得
        )
        
        if results:
            print(f"🎯 {len(results)}件の候補が見つかりました:")
            for i, result in enumerate(results, 1):
                song = result['song']
                confidence = result['confidence']
                time_alignment = result['time_alignment']
                
                print(f"{i}. {song.title} by {song.artist}")
                print(f"   信頼度: {confidence:.2%}")
                print(f"   時間オフセット: {time_alignment:.1f}秒")
                print()
        else:
            print("❓ マッチする楽曲が見つかりませんでした")

# 実行
basic_audio_search()
```

## 🎯 中級者向け例

### 4. カスタム設定での高精度識別

```python
def high_precision_identification():
    """高精度設定での音声識別"""
    # 高精度設定でMimizamを作成
    with create_mimizam_sqlite(
        "precision_db.db",
        # 高精度音声処理設定
        n_fft=4096,              # 高い周波数分解能
        hop_length=256,          # 細かい時間分解能
        min_amplitude=-70,       # 敏感な検出
        peak_neighborhood_size=30, # 大きな近傍サイズ
        
        # 高精度マッチング設定
        time_tolerance=0.05,     # 厳密な時間許容範囲
        freq_tolerance=25,       # 厳密な周波数許容範囲
        
        # デバッグ有効
        debug=True
    ) as mimizam:
        # 楽曲追加
        song_id = mimizam.add_song("music/reference_song.wav", "Reference Song", "Artist")
        print(f"参照楽曲追加 (ID: {song_id})")
        
        # 高精度識別
        query_file = "queries/noisy_sample.wav"
        identified = mimizam.identify_audio(query_file, min_confidence=0.6)
        
        if identified:
            song, confidence = identified
            print(f"🎯 高精度識別成功!")
            print(f"楽曲: {song.title}")
            print(f"信頼度: {confidence:.2%}")
        else:
            print("❓ 高精度設定でも識別できませんでした")

# 実行
high_precision_identification()
```

### 5. 複数データベースバックエンドの比較

```python
import time
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql
)

def compare_database_backends():
    """異なるデータベースバックエンドの性能比較"""
    test_song = "music/test_song.wav"
    query_song = "queries/test_query.wav"
    
    backends = [
        ("SQLite", lambda: create_mimizam_sqlite("test_sqlite.db")),
        ("MySQL", lambda: create_mimizam_mysql(
            host="localhost", database="test_db", 
            username="user", password="password"
        )),
        ("PostgreSQL", lambda: create_mimizam_postgresql(
            host="localhost", database="test_db",
            username="user", password="password"
        ))
    ]
    
    results = {}
    
    for backend_name, backend_factory in backends:
        try:
            print(f"\n🔍 {backend_name}バックエンドをテスト中...")
            
            with backend_factory() as mimizam:
                # 楽曲追加時間を測定
                start_time = time.time()
                song_id = mimizam.add_song(test_song, "Test Song", "Test Artist")
                add_time = time.time() - start_time
                
                # 検索時間を測定
                start_time = time.time()
                search_results = mimizam.search_song(query_song, top_k=5)
                search_time = time.time() - start_time
                
                # 統計情報取得
                stats = mimizam.get_database_stats()
                
                results[backend_name] = {
                    'add_time': add_time,
                    'search_time': search_time,
                    'song_count': stats['song_count'],
                    'fingerprint_count': stats['fingerprint_count'],
                    'results_found': len(search_results)
                }
                
                print(f"✅ {backend_name}: 追加 {add_time:.3f}s, 検索 {search_time:.3f}s")
                
        except Exception as e:
            print(f"❌ {backend_name}エラー: {e}")
            results[backend_name] = {'error': str(e)}
    
    # 結果比較表示
    print(f"\n📊 性能比較結果:")
    print(f"{'バックエンド':<12} {'追加時間':<8} {'検索時間':<8} {'結果数':<6}")
    print("-" * 40)
    
    for backend_name, result in results.items():
        if 'error' not in result:
            print(f"{backend_name:<12} {result['add_time']:<8.3f} {result['search_time']:<8.3f} {result['results_found']:<6}")
        else:
            print(f"{backend_name:<12} エラー: {result['error']}")

# 実行（適切なデータベース設定が必要）
# compare_database_backends()
```

### 6. エラーハンドリングの実装

```python
from mimizam import (
    create_mimizam_sqlite,
    AudioProcessingError,
    FingerprintGenerationError,
    DatabaseError,
    ValidationError
)
import logging

def robust_audio_processing():
    """堅牢な音声処理の実装"""
    # ログ設定
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    with create_mimizam_sqlite("robust_db.db") as mimizam:
        test_files = [
            "music/good_quality.wav",      # 正常なファイル
            "music/short_clip.wav",        # 短すぎるファイル
            "music/corrupted.wav",         # 破損ファイル
            "music/nonexistent.wav",       # 存在しないファイル
            "music/silent.wav"             # 無音ファイル
        ]
        
        success_count = 0
        error_count = 0
        
        for file_path in test_files:
            try:
                logger.info(f"処理中: {file_path}")
                
                # 楽曲追加を試行
                song_id = mimizam.add_song(
                    file_path, 
                    f"Test Song {len(test_files)}", 
                    "Test Artist"
                )
                
                logger.info(f"✅ 成功: {file_path} (ID: {song_id})")
                success_count += 1
                
            except AudioProcessingError as e:
                logger.error(f"❌ 音声処理エラー: {file_path} - {e}")
                error_count += 1
                # 音声ファイルの品質や形式に問題
                
            except FingerprintGenerationError as e:
                logger.error(f"❌ 指紋生成エラー: {file_path} - {e}")
                error_count += 1
                # 音声が短すぎるか、特徴が不足
                
            except DatabaseError as e:
                logger.error(f"❌ データベースエラー: {file_path} - {e}")
                error_count += 1
                # データベース操作に問題
                
            except ValidationError as e:
                logger.error(f"❌ 検証エラー: {file_path} - {e}")
                error_count += 1
                # 入力パラメータに問題
                
            except FileNotFoundError as e:
                logger.error(f"❌ ファイル未発見: {file_path}")
                error_count += 1
                # ファイルが存在しない
                
            except Exception as e:
                logger.error(f"❌ 予期しないエラー: {file_path} - {e}")
                error_count += 1
        
        # 結果サマリー
        total_files = len(test_files)
        logger.info(f"\n📊 処理結果:")
        logger.info(f"成功: {success_count}/{total_files}")
        logger.info(f"エラー: {error_count}/{total_files}")
        logger.info(f"成功率: {success_count/total_files:.1%}")

# 実行
robust_audio_processing()
```

## 🔗 関連ドキュメント

- [基本的な使用方法](./03_basic_usage.md) - 基本操作パターン
- [データベース設定](./05_database_setup.md) - バックエンド設定
- [システムアーキテクチャ](./04_architecture.md) - 全体構成の理解
- [FAQ](./07_faq.md) - よくある質問とトラブルシューティング

## 💡 ベストプラクティス

### 1. パフォーマンス最適化
- 適応パラメータ（`enable_adaptive_params=True`）を使用
- 適切なデータベースバックエンドを選択
- 音声品質を事前に評価

### 2. エラーハンドリング
- 包括的な例外処理を実装
- ログ出力で問題を追跡
- 失敗時の代替処理を準備

### 3. リソース管理
- コンテキストマネージャーを使用
- 大きなファイルはチャンク処理
- メモリ使用量を監視

### 4. 品質保証
- 音声品質を事前評価
- 複数の設定でテスト
- 結果の妥当性を検証
