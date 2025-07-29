# インストールガイド

## 📋 システム要件

### Python環境
- **Python**: 3.9以上（推奨: 3.10以上）
- **OS**: Windows、macOS、Linux対応
- **メモリ**: 最低2GB、推奨4GB以上
- **ストレージ**: 最低1GB（音声ファイルとデータベース用）

### 必須依存関係
- `numpy`: 数値計算
- `librosa`: 音声処理
- `scipy`: 科学計算
- `matplotlib`: 可視化
- `numba`: 高速化
- `hashlib`: ハッシュ生成（標準ライブラリ）

### オプション依存関係（データベース別）
- **MySQL**: `mysql-connector-python`
- **PostgreSQL**: `psycopg2-binary`
- **Elasticsearch**: `elasticsearch`
- **動画処理**: `ffmpeg`（システムレベル）

## 🚀 基本インストール

### 1. リポジトリのクローン

```bash
# GitHubからクローン
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam
```

### 2. 仮想環境の作成（推奨）

```bash
# Python仮想環境の作成
python -m venv mimizam_env

# 仮想環境の有効化
# Windows
mimizam_env\Scripts\activate
# macOS/Linux
source mimizam_env/bin/activate
```

### 3. 依存関係のインストール

```bash
# 基本依存関係のインストール
pip install -r requirements.txt

# パッケージのインストール（開発モード）
pip install -e .
```

## 🗄️ データベース別セットアップ

### SQLite（推奨・最も簡単）

```bash
# SQLiteは標準ライブラリに含まれているため追加インストール不要
# すぐに使用開始可能
```

```python
# 使用例
from mimizam import create_mimizam_sqlite

with create_mimizam_sqlite("my_music.db") as mimizam:
    print("SQLite準備完了！")
```

### MySQL

```bash
# MySQLクライアントのインストール
pip install mysql-connector-python

# MySQLサーバーのインストール（システム別）
# Ubuntu/Debian
sudo apt-get install mysql-server

# macOS (Homebrew)
brew install mysql

# Windows
# MySQL公式サイトからインストーラーをダウンロード
```

```sql
-- データベースとユーザーの作成
CREATE DATABASE fingerprints_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'fingerprint_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON fingerprints_db.* TO 'fingerprint_user'@'localhost';
FLUSH PRIVILEGES;
```

```python
# 使用例
from mimizam import create_mimizam_mysql

with create_mimizam_mysql(
    host="localhost",
    database="fingerprints_db",
    username="fingerprint_user",
    password="secure_password"
) as mimizam:
    print("MySQL準備完了！")
```

### PostgreSQL

```bash
# PostgreSQLクライアントのインストール
pip install psycopg2-binary

# PostgreSQLサーバーのインストール（システム別）
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS (Homebrew)
brew install postgresql

# Windows
# PostgreSQL公式サイトからインストーラーをダウンロード
```

```sql
-- データベースとユーザーの作成
CREATE DATABASE fingerprints_db;
CREATE USER fingerprint_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE fingerprints_db TO fingerprint_user;
```

```python
# 使用例
from mimizam import create_mimizam_postgresql

with create_mimizam_postgresql(
    host="localhost",
    database="fingerprints_db",
    username="fingerprint_user",
    password="secure_password"
) as mimizam:
    print("PostgreSQL準備完了！")
```

### Elasticsearch

```bash
# Elasticsearchクライアントのインストール
pip install elasticsearch

# Elasticsearchサーバーのインストール（システム別）
# Docker（推奨）
docker run -d --name elasticsearch \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  elasticsearch:8.8.0

# macOS (Homebrew)
brew install elasticsearch

# Ubuntu/Debian
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
sudo apt-get install apt-transport-https
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
sudo apt-get update && sudo apt-get install elasticsearch
```

```python
# 使用例
from mimizam import create_mimizam_elasticsearch

with create_mimizam_elasticsearch(
    host="localhost",
    port=9200,
    index_name="audio_fingerprints"
) as mimizam:
    print("Elasticsearch準備完了！")
```

## 🎥 動画処理のセットアップ

### FFmpegのインストール

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows
# https://ffmpeg.org/download.html からダウンロード
# または Chocolatey使用
choco install ffmpeg
```

### 動画処理の確認

```python
# 動画音声抽出のテスト
from mimizam.examples.video_fingerprinter import VideoAudioExtractor

extractor = VideoAudioExtractor()
audio_path = extractor.extract_audio("test_video.mp4")
print(f"音声抽出完了: {audio_path}")
```

## ✅ インストール確認

### 1. 基本機能テスト

```python
# 基本インポートテスト
try:
    from mimizam import create_mimizam_sqlite, AudioFingerprinter
    print("✅ 基本インポート成功")
except ImportError as e:
    print(f"❌ インポートエラー: {e}")

# SQLite動作テスト
try:
    with create_mimizam_sqlite(":memory:") as mimizam:
        print("✅ SQLite動作確認成功")
except Exception as e:
    print(f"❌ SQLite動作エラー: {e}")
```

### 2. 音声処理テスト

```python
# 音声処理テスト
try:
    import librosa
    import numpy as np
    
    # テスト音声生成
    sr = 22050
    duration = 5
    t = np.linspace(0, duration, sr * duration)
    audio = np.sin(2 * np.pi * 440 * t)  # 440Hz正弦波
    
    fingerprinter = AudioFingerprinter()
    fingerprints = fingerprinter.fingerprint_audio(audio, sr)
    print(f"✅ 音声処理成功: {len(fingerprints)}個の指紋生成")
except Exception as e:
    print(f"❌ 音声処理エラー: {e}")
```

### 3. 全体テスト実行

```bash
# テストスイート実行
python run_tests.py

# 特定テストの実行
python -m unittest tests.test_audio_fingerprinting -v
python -m unittest tests.test_mimizam_integration -v
```

### 4. デモ実行

```bash
# デモ用音声ファイル生成
python scripts/create_demo_audio.py

# Mimizamデモ実行
python examples/mimizam_demo.py

# 低レベルAPIデモ実行
python examples/lowlevelapi_demo.py
```

## 🔧 トラブルシューティング

### よくある問題と解決方法

#### 1. librosaインストールエラー

```bash
# 問題: librosaのインストールに失敗
# 解決方法: システム依存関係のインストール

# Ubuntu/Debian
sudo apt-get install libsndfile1-dev

# macOS
brew install libsndfile

# Windows
# conda使用を推奨
conda install librosa
```

#### 2. numbaコンパイルエラー

```bash
# 問題: numbaのJITコンパイルに失敗
# 解決方法: numbaの再インストール

pip uninstall numba
pip install numba
```

#### 3. データベース接続エラー

```python
# MySQL接続テスト
import mysql.connector
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="fingerprint_user",
        password="secure_password",
        database="fingerprints_db"
    )
    print("✅ MySQL接続成功")
    conn.close()
except Exception as e:
    print(f"❌ MySQL接続エラー: {e}")
```

#### 4. メモリ不足エラー

```python
# 大きな音声ファイル処理時のメモリ最適化
fingerprinter = AudioFingerprinter(
    n_fft=1024,        # FFTサイズを小さく
    hop_length=512,    # ホップ長を大きく
    enable_adaptive_params=True  # 適応最適化
)
```

## 📊 パフォーマンス最適化

### 1. 依存関係の最適化

```bash
# Intel MKL最適化（Intel CPU用）
pip install mkl

# OpenBLAS最適化（AMD CPU用）
pip install openblas
```

### 2. numba最適化設定

```python
# numba設定の最適化
import os
os.environ['NUMBA_NUM_THREADS'] = '4'  # CPUコア数に応じて調整
os.environ['NUMBA_CACHE_DIR'] = '/tmp/numba_cache'
```

### 3. メモリ設定

```python
# メモリ使用量の制限
import resource
resource.setrlimit(resource.RLIMIT_AS, (2*1024*1024*1024, -1))  # 2GB制限
```

## 🔗 次のステップ

- [基本的な使用方法](./03_basic_usage.md) - 基本的な使用パターン
- [データベース設定](./05_database_setup.md) - データベース詳細設定
- [実装例](./06_basic_examples.md) - 実践的なサンプルコード
- [FAQ](./07_faq.md) - よくある質問とトラブルシューティング

## 📞 サポート

インストールに関する問題がある場合：

1. [GitHub Issues](https://github.com/animalmatsuzawa/mimizam/issues) で問題を報告
2. 基本的な動作確認を実行
3. [FAQ](./07_faq.md) で既知の問題を確認
