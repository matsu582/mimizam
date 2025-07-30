# 実例とチュートリアル

このドキュメントでは、mimizamシステムの実践的な使用例とチュートリアルを提供します。基本的な使用方法から高度な応用まで、段階的に学習できる構成になっています。

詳細な実装については、以下を参照してください：
- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
- [動画処理](./06_2_video_processing.md) - 動画からの音声抽出と指紋生成
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術

## 概要

実例とチュートリアルセクションでは、mimizamの実際の使用場面を想定した具体的なコード例と解説を提供します。初心者から上級者まで、それぞれのレベルに応じた学習コンテンツを用意しています。

## 学習パス

### 初心者向け
1. [基本的な使用例](./06_1_basic_usage_examples.md) - 最初に読むべき基本的な使い方
2. [インストールガイド](./02_getting_started.md) - 環境構築の詳細
3. [データベース設定](./05_database_backends.md) - データベースの選択と設定

### 中級者向け
1. [動画処理](./06_2_video_processing.md) - 動画ファイルからの音声抽出
2. [APIリファレンス](./04_api_reference.md) - 詳細なAPI仕様
3. [コアアーキテクチャ](./03_core_architecture.md) - システムの内部構造

### 上級者向け
1. [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化とチューニング
2. [低レベルコンポーネント](./04_2_low_level_components.md) - 内部実装の詳細
3. [カスタマイゼーション](./03_1_audio_fingerprinting_engine.md) - 独自の実装

## 主要な使用例

### 音楽ライブラリ管理

```python
from mimizam import create_mimizam_sqlite
import os

# データベース初期化
mimizam = create_mimizam_sqlite("music_library.db")

# 音楽フォルダから楽曲を一括登録
music_folder = "/path/to/music"
for root, dirs, files in os.walk(music_folder):
    for file in files:
        if file.endswith(('.mp3', '.wav', '.flac')):
            filepath = os.path.join(root, file)
            song_name = os.path.splitext(file)[0]
            
            try:
                song_id = mimizam.add_song(filepath, song_name=song_name)
                print(f"登録完了: {song_name} (ID: {song_id})")
            except Exception as e:
                print(f"登録エラー {file}: {e}")

print(f"総楽曲数: {mimizam.get_song_count()}")
```

### リアルタイム音声識別

```python
import pyaudio
import numpy as np
from mimizam import create_mimizam_sqlite

# 音声識別システム初期化
mimizam = create_mimizam_sqlite("music_library.db")

# 音声入力設定
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 22050
RECORD_SECONDS = 10

# PyAudio初期化
p = pyaudio.PyAudio()

stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

print("音声録音開始...")

# 音声データを録音
frames = []
for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("録音完了、識別中...")

# 音声データを変換
audio_data = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float32)
audio_data = audio_data / 32768.0  # 正規化

# 楽曲識別
matches = mimizam.identify_audio_data(audio_data, RATE)

# 結果表示
if matches:
    best_match = matches[0]
    print(f"識別結果: {best_match['song_name']}")
    print(f"信頼度: {best_match['confidence']:.3f}")
else:
    print("マッチする楽曲が見つかりませんでした")

# クリーンアップ
stream.stop_stream()
stream.close()
p.terminate()
```

## 関連ドキュメント

- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
- [動画処理](./06_2_video_processing.md) - 動画からの音声抽出と指紋生成
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術
- [高レベルAPI](./04_1_high_level_api.md) - 統合インターフェース
- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
