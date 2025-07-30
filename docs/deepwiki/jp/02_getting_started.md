# はじめに

このガイドでは、mimizamの基本的なインストール手順と初回セットアップについて説明します。

詳細な技術文書については、[コアアーキテクチャ](./03_core_architecture.md)を参照してください。完全なAPIドキュメントについては、[APIリファレンス](./04_api_reference.md)を参照してください。

## インストール

### 前提条件

mimizamを使用するには、以下のソフトウェアが必要です：

- **Python 3.8以上**
- **pip**（Pythonパッケージマネージャー）
- **音声処理ライブラリ**（自動インストール）

### 基本インストール

```bash
# リポジトリのクローン
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam

# 依存関係のインストール
pip install -r requirements.txt

# 開発モードでのインストール
pip install -e .
```

### 依存関係

mimizamは以下の主要ライブラリに依存しています：

- **librosa**: 音声処理とスペクトログラム生成
- **numpy**: 数値計算
- **scipy**: 信号処理
- **matplotlib**: 可視化（オプション）
- **データベースドライバー**: 使用するバックエンドに応じて

### データベース固有の依存関係

使用するデータベースバックエンドに応じて、追加のパッケージが必要です：

```bash
# MySQL使用時
pip install mysql-connector-python

# PostgreSQL使用時
pip install psycopg2-binary

# Elasticsearch使用時
pip install elasticsearch
```

## クイックスタート

### 1. 基本的な音声識別

```python
from mimizam import create_mimizam_sqlite

# SQLiteデータベースでmimizamインスタンスを作成
mimizam = create_mimizam_sqlite("my_music.db")

# 楽曲をデータベースに追加
mimizam.add_song("song1.wav", song_name="My Favorite Song")
mimizam.add_song("song2.mp3", song_name="Another Song")

# 音声クリップから楽曲を識別
matches = mimizam.identify("query_clip.wav")

if matches:
    best_match = matches[0]
    print(f"識別結果: {best_match['song_name']}")
    print(f"信頼度: {best_match['score']:.2f}")
else:
    print("マッチする楽曲が見つかりませんでした")
```

### 2. 複数データベースバックエンドの使用

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql
)

# SQLite（開発・テスト用）
sqlite_mimizam = create_mimizam_sqlite("test.db")

# MySQL（本番環境用）
mysql_mimizam = create_mimizam_mysql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_production"
)

# PostgreSQL（高機能用途）
postgres_mimizam = create_mimizam_postgresql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_advanced"
)
```

### 3. バッチ処理

```python
import os
from mimizam import create_mimizam_sqlite

mimizam = create_mimizam_sqlite("batch_music.db")

# ディレクトリ内の全音声ファイルを処理
music_dir = "path/to/music/files"
for filename in os.listdir(music_dir):
    if filename.endswith(('.wav', '.mp3', '.flac')):
        filepath = os.path.join(music_dir, filename)
        song_name = os.path.splitext(filename)[0]
        
        try:
            mimizam.add_song(filepath, song_name=song_name)
            print(f"追加完了: {song_name}")
        except Exception as e:
            print(f"エラー {filename}: {e}")

print(f"データベースに {mimizam.get_song_count()} 曲が登録されました")
```

### 4. 可視化機能

```python
from mimizam import create_mimizam_sqlite
import matplotlib.pyplot as plt

mimizam = create_mimizam_sqlite("visualization.db")

# スペクトログラムの生成と表示
spectrogram = mimizam.generate_spectrogram("sample.wav")
peaks = mimizam.detect_peaks("sample.wav")

# 可視化
plt.figure(figsize=(12, 8))
plt.subplot(2, 1, 1)
plt.imshow(spectrogram, aspect='auto', origin='lower')
plt.title('スペクトログラム')
plt.ylabel('周波数')

plt.subplot(2, 1, 2)
plt.scatter(peaks[:, 0], peaks[:, 1], alpha=0.6)
plt.title('検出されたピーク')
plt.xlabel('時間')
plt.ylabel('周波数')

plt.tight_layout()
plt.show()
```

## 設定オプション

### 基本パラメータ

```python
# カスタムパラメータでの初期化
mimizam = create_mimizam_sqlite(
    "custom.db",
    # ピーク検出パラメータ
    peak_threshold=0.15,        # ピーク検出の閾値
    min_peak_distance=12,       # ピーク間の最小距離
    
    # ハッシュ生成パラメータ
    target_zone_size=4,         # ターゲットゾーンのサイズ
    max_time_delta=200,         # 最大時間差
    
    # 音声処理パラメータ
    sample_rate=22050,          # サンプリングレート
    n_fft=2048,                 # FFTサイズ
    hop_length=512              # ホップ長
)
```

### データベース接続設定

```python
# MySQL詳細設定
mysql_mimizam = create_mimizam_mysql(
    host="db.example.com",
    port=3306,
    user="mimizam_user",
    password="secure_password",
    database="music_db",
    charset="utf8mb4",
    connection_timeout=30
)

# PostgreSQL詳細設定
postgres_mimizam = create_mimizam_postgresql(
    host="postgres.example.com",
    port=5432,
    user="mimizam_user",
    password="secure_password",
    database="music_db",
    sslmode="require"
)
```

## 基本的なワークフロー

### 1. データベース準備
```python
from mimizam import create_mimizam_sqlite

# データベースの作成（初回のみ）
mimizam = create_mimizam_sqlite("music_library.db")
```

### 2. 楽曲の登録
```python
# 単一楽曲の追加
mimizam.add_song("path/to/song.wav", song_name="楽曲名")

# メタデータ付きで追加
mimizam.add_song(
    "path/to/song.wav",
    song_name="楽曲名",
    artist="アーティスト名",
    album="アルバム名"
)
```

### 3. 音声識別
```python
# 音声ファイルから識別
matches = mimizam.identify("unknown_clip.wav")

# 音声データから直接識別
import librosa
audio_data, sr = librosa.load("clip.wav")
matches = mimizam.identify_audio_data(audio_data, sr)
```

### 4. 結果の処理
```python
for match in matches:
    print(f"楽曲: {match['song_name']}")
    print(f"スコア: {match['score']:.3f}")
    print(f"時間オフセット: {match['time_offset']:.1f}秒")
    print("---")
```

## トラブルシューティング

### よくある問題

1. **音声ファイルが読み込めない**
   - サポートされている形式（WAV、MP3、FLAC）を使用してください
   - ファイルパスが正しいことを確認してください

2. **データベース接続エラー**
   - データベースサーバーが起動していることを確認してください
   - 接続情報（ホスト、ユーザー、パスワード）が正しいことを確認してください

3. **識別精度が低い**
   - より長い音声クリップ（10秒以上）を使用してください
   - ピーク検出パラメータを調整してください

4. **処理が遅い**
   - SQLiteから他のデータベースバックエンドへの移行を検討してください
   - バッチ処理を使用してください

### ログ設定

```python
import logging

# デバッグ情報の有効化
logging.basicConfig(level=logging.DEBUG)

# mimizam固有のログ
logger = logging.getLogger('mimizam')
logger.setLevel(logging.INFO)
```

## 次のステップ

- [コアアーキテクチャ](./03_core_architecture.md) - システムの詳細な技術仕様
- [APIリファレンス](./04_api_reference.md) - 完全なAPI文書
- [データベースバックエンド](./05_database_backends.md) - データベース選択ガイド
- [基本的な使用例](./06_1_basic_usage_examples.md) - より詳細な実例
