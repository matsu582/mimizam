# 基本的な使用方法

mimizamの基本的な使用方法を段階的に説明します。初めてmimizamを使用する方でも理解できるよう、実践的な例を中心に解説します。

## 🎯 学習の流れ

1. **基本操作**: 楽曲の追加と検索
2. **データベース選択**: 用途に応じたバックエンド選択
3. **バッチ処理**: 複数ファイルの効率的な処理
4. **設定調整**: パフォーマンスの最適化
5. **トラブルシューティング**: よくある問題の解決

## 🚀 最初のステップ

### 1. 基本的な音声識別

```python
from mimizam import create_mimizam_sqlite

# SQLiteを使用した最もシンプルな例
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲をデータベースに追加
    song_id = mimizam.add_song("music/song.wav", "楽曲名", "アーティスト名")
    print(f"楽曲が追加されました (ID: {song_id})")
    
    # 音声を識別
    identified = mimizam.identify_audio("query/unknown.wav")
    if identified:
        song, confidence = identified
        print(f"識別結果: {song.title} (信頼度: {confidence:.2%})")
    else:
        print("楽曲を識別できませんでした")
```

### 2. 複数の候補を検索

```python
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 複数の候補を取得
    results = mimizam.search_song(
        "query/humming.wav",
        min_confidence=0.2,  # 信頼度閾値
        top_k=5              # 上位5件
    )
    
    print(f"{len(results)}件の候補が見つかりました:")
    for i, result in enumerate(results, 1):
        song = result['song']
        confidence = result['confidence']
        print(f"{i}. {song.title} by {song.artist} ({confidence:.2%})")
```

## 📁 楽曲ライブラリの構築

### 複数ファイルの一括追加

```python
import glob
from pathlib import Path

def build_music_library():
    """音楽ライブラリを構築"""
    with create_mimizam_sqlite("music_library.db") as mimizam:
        # 音楽フォルダから全てのWAVファイルを取得
        audio_files = glob.glob("music/**/*.wav", recursive=True)
        
        print(f"{len(audio_files)}個のファイルを処理中...")
        
        for file_path in audio_files:
            try:
                # ファイル名から情報を抽出
                path_obj = Path(file_path)
                title = path_obj.stem
                artist = path_obj.parent.name
                
                # 楽曲追加
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"✅ {title} by {artist} (ID: {song_id})")
                
            except Exception as e:
                print(f"❌ エラー: {file_path} - {e}")
        
        # 統計情報表示
        stats = mimizam.get_database_stats()
        print(f"\n📊 ライブラリ統計:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")

# 実行
build_music_library()
```

## 🎛️ 設定のカスタマイズ

### 高精度設定

```python
# 高精度な音声識別設定
with create_mimizam_sqlite(
    "precision.db",
    n_fft=4096,              # 高い周波数分解能
    hop_length=256,          # 細かい時間分解能
    min_amplitude=-70,       # 敏感な検出
    enable_adaptive_params=True,  # 適応パラメータ
    debug=True               # デバッグ情報
) as mimizam:
    # 高精度で楽曲追加
    song_id = mimizam.add_song("music/high_quality.wav", "高品質楽曲", "アーティスト")
    
    # 高精度で識別
    identified = mimizam.identify_audio("query/noisy.wav", min_confidence=0.6)
    if identified:
        song, confidence = identified
        print(f"高精度識別: {song.title} ({confidence:.2%})")
```

### 高速設定

```python
# 高速処理設定
with create_mimizam_sqlite(
    "fast.db",
    n_fft=1024,              # 小さなFFTサイズ
    hop_length=512,          # 大きなホップ長
    min_amplitude=-40,       # 高い閾値
    enable_adaptive_params=True
) as mimizam:
    # 高速で楽曲追加
    song_id = mimizam.add_song("music/song.wav", "楽曲", "アーティスト")
    
    # 高速で識別
    identified = mimizam.identify_audio("query/query.wav", min_confidence=0.2)
```

## 🗄️ 異なるデータベースの使用

### MySQL使用例

```python
from mimizam import create_mimizam_mysql

# MySQL接続（事前にデータベースとユーザーを作成）
with create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="music_user",
    password="password"
) as mimizam:
    # 同じAPIで使用可能
    song_id = mimizam.add_song("music/song.wav", "楽曲", "アーティスト")
    results = mimizam.search_song("query/query.wav")
```

### PostgreSQL使用例

```python
from mimizam import create_mimizam_postgresql

# PostgreSQL接続
with create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="music_user",
    password="password"
) as mimizam:
    # 高性能データベースで同じAPI
    song_id = mimizam.add_song("music/song.wav", "楽曲", "アーティスト")
    results = mimizam.search_song("query/query.wav")
```

## 🎵 メタデータの活用

### 詳細な楽曲情報の保存

```python
with create_mimizam_sqlite("metadata.db") as mimizam:
    # メタデータ付きで楽曲追加
    song_id = mimizam.add_song(
        file_path="music/song.wav",
        title="素晴らしい楽曲",
        artist="有名アーティスト",
        album="ベストアルバム",
        meta={
            "genre": "ポップス",
            "year": 2023,
            "duration": 180.5,
            "bitrate": 320,
            "language": "日本語"
        }
    )
    
    # 楽曲情報の取得
    song = mimizam.get_song(song_id)
    print(f"ジャンル: {song.meta['genre']}")
    print(f"年: {song.meta['year']}")
    print(f"長さ: {song.meta['duration']}秒")
```

## 🔍 検索オプション

### スコアリング方式の選択

```python
with create_mimizam_sqlite("scoring.db") as mimizam:
    # 楽曲追加
    song_id = mimizam.add_song("music/song.wav", "テスト楽曲", "テストアーティスト")
    
    # 異なるスコアリング方式で検索
    query_file = "query/test.wav"
    
    # 高速検索（histogram方式）
    fast_results = mimizam.search_song(
        query_file,
        scoring_method='histogram',
        min_confidence=0.2
    )
    print(f"高速検索: {len(fast_results)}件")
    
    # バランス検索（hybrid方式、デフォルト）
    balanced_results = mimizam.search_song(
        query_file,
        scoring_method='hybrid',
        min_confidence=0.3
    )
    print(f"バランス検索: {len(balanced_results)}件")
    
    # 高精度検索（detailed方式）
    precise_results = mimizam.search_song(
        query_file,
        scoring_method='detailed',
        min_confidence=0.5
    )
    print(f"高精度検索: {len(precise_results)}件")
```

## 📊 データベース管理

### 統計情報の確認

```python
with create_mimizam_sqlite("stats.db") as mimizam:
    # 楽曲を追加
    for i in range(5):
        mimizam.add_song(f"music/song{i}.wav", f"楽曲{i}", "アーティスト")
    
    # 統計情報取得
    stats = mimizam.get_database_stats()
    print(f"📊 データベース統計:")
    print(f"楽曲数: {stats['song_count']}")
    print(f"指紋数: {stats['fingerprint_count']:,}")
    print(f"データベースサイズ: {stats['database_size'] / 1024 / 1024:.1f} MB")
    print(f"楽曲あたり平均指紋数: {stats['avg_fingerprints_per_song']:.1f}")
```

### 楽曲一覧の取得

```python
with create_mimizam_sqlite("list.db") as mimizam:
    # 楽曲追加
    mimizam.add_song("music/song1.wav", "楽曲1", "アーティストA")
    mimizam.add_song("music/song2.wav", "楽曲2", "アーティストB")
    
    # 楽曲一覧取得
    songs = mimizam.list_songs(limit=10)
    print("📋 楽曲一覧:")
    for song in songs:
        print(f"ID {song.id}: {song.title} by {song.artist}")
```

## 🚨 エラーハンドリング

### 基本的なエラー処理

```python
from mimizam import (
    create_mimizam_sqlite,
    AudioProcessingError,
    DatabaseError
)

def safe_audio_processing():
    """安全な音声処理"""
    try:
        with create_mimizam_sqlite("safe.db") as mimizam:
            # 楽曲追加を試行
            song_id = mimizam.add_song(
                "music/test.wav", 
                "テスト楽曲", 
                "テストアーティスト"
            )
            print(f"✅ 楽曲追加成功 (ID: {song_id})")
            
            # 音声識別を試行
            identified = mimizam.identify_audio("query/test.wav")
            if identified:
                song, confidence = identified
                print(f"✅ 識別成功: {song.title} ({confidence:.2%})")
            else:
                print("❓ 楽曲を識別できませんでした")
                
    except AudioProcessingError as e:
        print(f"❌ 音声処理エラー: {e}")
        # 音声ファイルの品質や形式に問題がある可能性
        
    except DatabaseError as e:
        print(f"❌ データベースエラー: {e}")
        # データベース接続や操作に問題がある可能性
        
    except FileNotFoundError as e:
        print(f"❌ ファイルが見つかりません: {e}")
        
    except Exception as e:
        print(f"❌ 予期しないエラー: {e}")

# 実行
safe_audio_processing()
```

## 🎯 実用的な使用パターン

### 音楽識別アプリケーション

```python
def music_identification_app():
    """音楽識別アプリケーションの例"""
    with create_mimizam_sqlite("music_app.db") as mimizam:
        while True:
            print("\n🎵 音楽識別アプリ")
            print("1. 楽曲を追加")
            print("2. 音声を識別")
            print("3. 楽曲一覧")
            print("4. 終了")
            
            choice = input("選択してください (1-4): ")
            
            if choice == '1':
                file_path = input("音声ファイルのパス: ")
                title = input("楽曲タイトル: ")
                artist = input("アーティスト名: ")
                
                try:
                    song_id = mimizam.add_song(file_path, title, artist)
                    print(f"✅ 楽曲が追加されました (ID: {song_id})")
                except Exception as e:
                    print(f"❌ エラー: {e}")
            
            elif choice == '2':
                query_path = input("識別したい音声ファイルのパス: ")
                
                try:
                    identified = mimizam.identify_audio(query_path)
                    if identified:
                        song, confidence = identified
                        print(f"🎯 識別結果: {song.title} by {song.artist}")
                        print(f"信頼度: {confidence:.2%}")
                    else:
                        print("❓ 楽曲を識別できませんでした")
                except Exception as e:
                    print(f"❌ エラー: {e}")
            
            elif choice == '3':
                songs = mimizam.list_songs(limit=20)
                print(f"\n📋 楽曲一覧 ({len(songs)}件):")
                for song in songs:
                    print(f"  {song.id}: {song.title} by {song.artist}")
            
            elif choice == '4':
                print("👋 アプリケーションを終了します")
                break
            
            else:
                print("❌ 無効な選択です")

# 実行（インタラクティブ環境で）
# music_identification_app()
```

## 💡 ベストプラクティス

### 1. リソース管理
```python
# ✅ 推奨: コンテキストマネージャーを使用
with create_mimizam_sqlite("music.db") as mimizam:
    # 処理
    pass  # 自動的にリソースが解放される

# ❌ 非推奨: 手動管理
mimizam = create_mimizam_sqlite("music.db")
# 処理
mimizam.close()  # 忘れやすい
```

### 2. エラーハンドリング
```python
# ✅ 推奨: 適切な例外処理
try:
    song_id = mimizam.add_song("music/song.wav", "楽曲", "アーティスト")
except AudioProcessingError:
    print("音声処理に失敗しました")
except DatabaseError:
    print("データベース操作に失敗しました")
```

### 3. 設定の選択
```python
# 用途に応じた設定選択
if need_high_accuracy:
    # 高精度設定
    config = {'n_fft': 4096, 'min_amplitude': -70}
elif need_high_speed:
    # 高速設定
    config = {'n_fft': 1024, 'min_amplitude': -40}
else:
    # デフォルト設定
    config = {}

with create_mimizam_sqlite("music.db", **config) as mimizam:
    # 処理
    pass
```

## 🔗 次のステップ

基本的な使用方法を理解したら、以下のドキュメントで詳細を学習してください：

- [データベース設定](./05_database_setup.md) - 各データベースの詳細設定
- [実装例](./06_basic_examples.md) - より実践的な例
- [FAQ](./07_faq.md) - よくある質問とトラブルシューティング
