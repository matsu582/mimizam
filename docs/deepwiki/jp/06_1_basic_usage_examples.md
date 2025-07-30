# 基本的な使用例

このドキュメントでは、mimizamシステムの基本的な使用方法を実践的なコード例とともに説明します。初心者でも理解しやすいよう、段階的に機能を紹介していきます。

他の実例については、以下を参照してください：
- [動画処理](./06_2_video_processing.md) - 動画からの音声抽出と指紋生成
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術

## 概要

基本的な使用例では、mimizamの核となる機能である楽曲の登録、音声識別、データベース管理について、実際に動作するコード例を提供します。

## 最初のステップ

### 1. 環境設定

```python
# 必要なライブラリのインポート
from mimizam import create_mimizam_sqlite
import os
import librosa
import numpy as np

# データベースファイルのパス
DB_PATH = "my_music_library.db"

# mimizamインスタンスの作成
mimizam = create_mimizam_sqlite(DB_PATH)

print(f"mimizamが初期化されました: {DB_PATH}")
print(f"現在の楽曲数: {mimizam.get_song_count()}")
```

### 2. 最初の楽曲登録

```python
def add_first_song():
    """最初の楽曲をデータベースに登録"""
    
    # 音声ファイルのパス
    audio_file = "path/to/your/song.wav"
    
    # ファイルの存在確認
    if not os.path.exists(audio_file):
        print(f"ファイルが見つかりません: {audio_file}")
        return None
    
    try:
        # 楽曲を登録
        song_id = mimizam.add_song(
            audio_file,
            song_name="My First Song",
            artist="Test Artist",
            album="Test Album"
        )
        
        print(f"楽曲登録完了!")
        print(f"  楽曲ID: {song_id}")
        print(f"  ファイル: {os.path.basename(audio_file)}")
        
        return song_id
        
    except Exception as e:
        print(f"楽曲登録エラー: {e}")
        return None

# 実行
song_id = add_first_song()
```

### 3. 楽曲情報の確認

```python
def show_song_info(song_id):
    """楽曲情報を表示"""
    
    try:
        song_info = mimizam.get_song_info(song_id)
        
        print(f"\n=== 楽曲情報 (ID: {song_id}) ===")
        print(f"楽曲名: {song_info['name']}")
        print(f"アーティスト: {song_info.get('artist', 'Unknown')}")
        print(f"アルバム: {song_info.get('album', 'Unknown')}")
        print(f"再生時間: {song_info.get('duration', 'Unknown')}秒")
        print(f"ファイルパス: {song_info.get('file_path', 'Unknown')}")
        print(f"登録日時: {song_info.get('created_at', 'Unknown')}")
        
    except Exception as e:
        print(f"楽曲情報取得エラー: {e}")

# 実行
if song_id:
    show_song_info(song_id)
```

## 複数楽曲の管理

### 4. フォルダから一括登録

```python
def add_songs_from_folder(folder_path):
    """フォルダ内の音声ファイルを一括登録"""
    
    if not os.path.exists(folder_path):
        print(f"フォルダが見つかりません: {folder_path}")
        return
    
    # サポートする音声ファイル形式
    supported_formats = ('.wav', '.mp3', '.flac', '.m4a')
    
    added_count = 0
    error_count = 0
    
    print(f"フォルダを処理中: {folder_path}")
    
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(supported_formats):
            filepath = os.path.join(folder_path, filename)
            
            # ファイル名から楽曲名を抽出
            song_name = os.path.splitext(filename)[0]
            
            try:
                song_id = mimizam.add_song(
                    filepath,
                    song_name=song_name
                )
                
                print(f"✓ 登録完了: {filename} (ID: {song_id})")
                added_count += 1
                
            except Exception as e:
                print(f"✗ 登録エラー: {filename} - {e}")
                error_count += 1
    
    print(f"\n処理結果:")
    print(f"  成功: {added_count}曲")
    print(f"  エラー: {error_count}曲")
    print(f"  総楽曲数: {mimizam.get_song_count()}")

# 使用例
music_folder = "path/to/your/music/folder"
add_songs_from_folder(music_folder)
```

### 5. 楽曲リストの表示

```python
def list_all_songs():
    """データベース内の全楽曲を表示"""
    
    song_count = mimizam.get_song_count()
    
    if song_count == 0:
        print("データベースに楽曲が登録されていません")
        return
    
    print(f"\n=== 楽曲リスト (総数: {song_count}) ===")
    
    for song_id in range(1, song_count + 1):
        try:
            song_info = mimizam.get_song_info(song_id)
            
            print(f"{song_id:3d}. {song_info['name']}")
            if song_info.get('artist'):
                print(f"     アーティスト: {song_info['artist']}")
            
        except Exception as e:
            print(f"{song_id:3d}. [エラー: {e}]")

# 実行
list_all_songs()
```

## 音声識別

### 6. 基本的な音声識別

```python
def identify_audio_file(query_file):
    """音声ファイルを識別"""
    
    if not os.path.exists(query_file):
        print(f"ファイルが見つかりません: {query_file}")
        return
    
    print(f"音声識別中: {os.path.basename(query_file)}")
    
    try:
        # 音声識別を実行
        matches = mimizam.identify(query_file)
        
        if matches:
            print(f"\n=== 識別結果 ===")
            
            for i, match in enumerate(matches[:5], 1):  # 上位5件を表示
                print(f"{i}. {match['song_name']}")
                
                if match.get('artist'):
                    print(f"   アーティスト: {match['artist']}")
                
                print(f"   スコア: {match['score']:.3f}")
                print(f"   信頼度: {match['confidence']:.3f}")
                print(f"   マッチ数: {match['match_count']}")
                print()
        else:
            print("マッチする楽曲が見つかりませんでした")
            
    except Exception as e:
        print(f"音声識別エラー: {e}")

# 使用例
query_audio = "path/to/query/audio.wav"
identify_audio_file(query_audio)
```

### 7. 音声データからの識別

```python
def identify_from_audio_data():
    """音声データから直接識別"""
    
    # 音声ファイルを読み込み
    audio_file = "path/to/query/audio.wav"
    
    try:
        # librosで音声データを読み込み
        audio_data, sample_rate = librosa.load(audio_file, sr=22050)
        
        print(f"音声データ読み込み完了:")
        print(f"  サンプル数: {len(audio_data)}")
        print(f"  サンプリングレート: {sample_rate} Hz")
        print(f"  再生時間: {len(audio_data) / sample_rate:.2f}秒")
        
        # 音声識別を実行
        matches = mimizam.identify_audio_data(audio_data, sample_rate)
        
        if matches:
            best_match = matches[0]
            print(f"\n識別結果: {best_match['song_name']}")
            print(f"信頼度: {best_match['confidence']:.3f}")
        else:
            print("マッチする楽曲が見つかりませんでした")
            
    except Exception as e:
        print(f"エラー: {e}")

# 実行
identify_from_audio_data()
```

## 可視化と分析

### 8. スペクトログラム生成

```python
def generate_and_show_spectrogram(audio_file):
    """スペクトログラムを生成して表示"""
    
    try:
        # スペクトログラムを生成
        spectrogram = mimizam.generate_spectrogram(audio_file)
        
        print(f"スペクトログラム生成完了:")
        print(f"  形状: {spectrogram.shape}")
        print(f"  周波数ビン数: {spectrogram.shape[0]}")
        print(f"  時間フレーム数: {spectrogram.shape[1]}")
        
        # matplotlib が利用可能な場合は可視化
        try:
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(12, 6))
            plt.imshow(spectrogram, aspect='auto', origin='lower', cmap='viridis')
            plt.colorbar(label='振幅 (dB)')
            plt.title(f'スペクトログラム: {os.path.basename(audio_file)}')
            plt.xlabel('時間フレーム')
            plt.ylabel('周波数ビン')
            plt.show()
            
        except ImportError:
            print("matplotlib が利用できません。可視化をスキップします。")
            
    except Exception as e:
        print(f"スペクトログラム生成エラー: {e}")

# 使用例
audio_file = "path/to/your/audio.wav"
generate_and_show_spectrogram(audio_file)
```

### 9. ピーク検出

```python
def detect_and_show_peaks(audio_file):
    """ピークを検出して表示"""
    
    try:
        # ピークを検出
        peaks = mimizam.detect_peaks(audio_file)
        
        print(f"ピーク検出完了:")
        print(f"  検出されたピーク数: {len(peaks)}")
        
        if peaks:
            print(f"  最初の10個のピーク:")
            for i, (time, freq) in enumerate(peaks[:10]):
                print(f"    {i+1:2d}. 時間: {time:4d}, 周波数: {freq:4d}")
        
        # matplotlib が利用可能な場合は可視化
        try:
            import matplotlib.pyplot as plt
            
            # スペクトログラムも生成
            spectrogram = mimizam.generate_spectrogram(audio_file)
            
            plt.figure(figsize=(12, 6))
            plt.imshow(spectrogram, aspect='auto', origin='lower', cmap='viridis', alpha=0.7)
            
            # ピークを赤い点で表示
            if peaks:
                peak_times = [p[0] for p in peaks]
                peak_freqs = [p[1] for p in peaks]
                plt.scatter(peak_times, peak_freqs, c='red', s=10, alpha=0.8)
            
            plt.colorbar(label='振幅 (dB)')
            plt.title(f'スペクトログラムとピーク: {os.path.basename(audio_file)}')
            plt.xlabel('時間フレーム')
            plt.ylabel('周波数ビン')
            plt.show()
            
        except ImportError:
            print("matplotlib が利用できません。可視化をスキップします。")
            
    except Exception as e:
        print(f"ピーク検出エラー: {e}")

# 使用例
audio_file = "path/to/your/audio.wav"
detect_and_show_peaks(audio_file)
```

## データベース管理

### 10. データベース統計

```python
def show_database_statistics():
    """データベースの統計情報を表示"""
    
    try:
        song_count = mimizam.get_song_count()
        
        print(f"\n=== データベース統計 ===")
        print(f"総楽曲数: {song_count}")
        
        if song_count > 0:
            # データベースファイルサイズ（SQLiteの場合）
            if os.path.exists(DB_PATH):
                file_size = os.path.getsize(DB_PATH)
                print(f"データベースサイズ: {file_size / 1024 / 1024:.2f} MB")
            
            # 楽曲あたりの平均ファイルサイズ
            total_file_size = 0
            valid_files = 0
            
            for song_id in range(1, min(song_count + 1, 100)):  # 最初の100曲をサンプル
                try:
                    song_info = mimizam.get_song_info(song_id)
                    file_path = song_info.get('file_path')
                    
                    if file_path and os.path.exists(file_path):
                        total_file_size += os.path.getsize(file_path)
                        valid_files += 1
                        
                except:
                    continue
            
            if valid_files > 0:
                avg_file_size = total_file_size / valid_files
                print(f"平均ファイルサイズ: {avg_file_size / 1024 / 1024:.2f} MB")
                print(f"サンプル数: {valid_files}曲")
        
    except Exception as e:
        print(f"統計取得エラー: {e}")

# 実行
show_database_statistics()
```

### 11. 楽曲削除

```python
def delete_song_by_id(song_id):
    """指定されたIDの楽曲を削除"""
    
    try:
        # 削除前に楽曲情報を表示
        song_info = mimizam.get_song_info(song_id)
        print(f"削除対象楽曲:")
        print(f"  ID: {song_id}")
        print(f"  楽曲名: {song_info['name']}")
        print(f"  アーティスト: {song_info.get('artist', 'Unknown')}")
        
        # 確認
        response = input("本当に削除しますか？ (y/N): ")
        
        if response.lower() == 'y':
            success = mimizam.delete_song(song_id)
            
            if success:
                print("楽曲を削除しました")
                print(f"現在の楽曲数: {mimizam.get_song_count()}")
            else:
                print("楽曲の削除に失敗しました")
        else:
            print("削除をキャンセルしました")
            
    except Exception as e:
        print(f"削除エラー: {e}")

# 使用例（注意: 実際に削除されます）
# delete_song_by_id(1)
```

## 実用的な使用例

### 12. 音楽識別システム

```python
class SimpleMusicIdentifier:
    """シンプルな音楽識別システム"""
    
    def __init__(self, db_path):
        self.mimizam = create_mimizam_sqlite(db_path)
        self.db_path = db_path
    
    def setup_library(self, music_folders):
        """音楽ライブラリを設定"""
        print("=== 音楽ライブラリ設定 ===")
        
        total_added = 0
        
        for folder in music_folders:
            if os.path.exists(folder):
                print(f"処理中: {folder}")
                added = self._add_folder(folder)
                total_added += added
            else:
                print(f"フォルダが見つかりません: {folder}")
        
        print(f"設定完了: {total_added}曲を追加")
        print(f"総楽曲数: {self.mimizam.get_song_count()}")
    
    def _add_folder(self, folder):
        """フォルダ内の楽曲を追加"""
        added_count = 0
        
        for filename in os.listdir(folder):
            if filename.lower().endswith(('.wav', '.mp3', '.flac')):
                filepath = os.path.join(folder, filename)
                song_name = os.path.splitext(filename)[0]
                
                try:
                    self.mimizam.add_song(filepath, song_name=song_name)
                    added_count += 1
                    print(f"  ✓ {filename}")
                except Exception as e:
                    print(f"  ✗ {filename}: {e}")
        
        return added_count
    
    def identify_file(self, audio_file):
        """音声ファイルを識別"""
        print(f"識別中: {os.path.basename(audio_file)}")
        
        try:
            matches = self.mimizam.identify(audio_file)
            
            if matches:
                best_match = matches[0]
                print(f"結果: {best_match['song_name']}")
                print(f"信頼度: {best_match['confidence']:.3f}")
                return best_match
            else:
                print("マッチする楽曲が見つかりませんでした")
                return None
                
        except Exception as e:
            print(f"識別エラー: {e}")
            return None
    
    def get_stats(self):
        """統計情報を取得"""
        return {
            'song_count': self.mimizam.get_song_count(),
            'db_size_mb': os.path.getsize(self.db_path) / 1024 / 1024 if os.path.exists(self.db_path) else 0
        }

# 使用例
identifier = SimpleMusicIdentifier("music_identifier.db")

# ライブラリ設定
music_folders = [
    "path/to/music/folder1",
    "path/to/music/folder2"
]
identifier.setup_library(music_folders)

# 音声識別
test_file = "path/to/test/audio.wav"
result = identifier.identify_file(test_file)

# 統計表示
stats = identifier.get_stats()
print(f"統計: {stats}")
```

## トラブルシューティング

### 13. 一般的な問題の対処

```python
def troubleshoot_common_issues():
    """一般的な問題をチェック"""
    
    print("=== トラブルシューティング ===")
    
    # 1. データベースファイルの確認
    if os.path.exists(DB_PATH):
        file_size = os.path.getsize(DB_PATH)
        print(f"✓ データベースファイル存在: {DB_PATH} ({file_size} bytes)")
    else:
        print(f"✗ データベースファイルが見つかりません: {DB_PATH}")
    
    # 2. mimizamインスタンスの確認
    try:
        song_count = mimizam.get_song_count()
        print(f"✓ mimizam接続正常: {song_count}曲登録済み")
    except Exception as e:
        print(f"✗ mimizam接続エラー: {e}")
    
    # 3. 依存ライブラリの確認
    required_libs = ['librosa', 'numpy', 'scipy']
    
    for lib in required_libs:
        try:
            __import__(lib)
            print(f"✓ {lib} 利用可能")
        except ImportError:
            print(f"✗ {lib} が見つかりません")
    
    # 4. 音声ファイル形式の確認
    test_file = "path/to/test/audio.wav"  # テスト用ファイルパス
    
    if os.path.exists(test_file):
        try:
            audio_data, sr = librosa.load(test_file, sr=22050)
            print(f"✓ 音声ファイル読み込み正常: {len(audio_data)}サンプル")
        except Exception as e:
            print(f"✗ 音声ファイル読み込みエラー: {e}")
    else:
        print(f"- テスト音声ファイルが見つかりません: {test_file}")

# 実行
troubleshoot_common_issues()
```

## まとめ

この基本的な使用例では、mimizamの主要機能を実践的なコード例とともに紹介しました。これらの例を参考に、独自の音楽識別システムを構築できます。

### 次のステップ

- [動画処理](./06_2_video_processing.md) - 動画ファイルからの音声抽出
- [パフォーマンス最適化](./06_3_performance_optimization.md) - システムの高速化
- [高レベルAPI](./04_1_high_level_api.md) - より詳細なAPI仕様
- [データベースバックエンド](./05_database_backends.md) - 本番環境での設定

## 関連ドキュメント

- [概要](./01_overview.md) - mimizamシステムの概要
- [インストールガイド](./02_getting_started.md) - 環境構築の詳細
- [コアアーキテクチャ](./03_core_architecture.md) - システムの内部構造
- [APIリファレンス](./04_api_reference.md) - 完全なAPI仕様
