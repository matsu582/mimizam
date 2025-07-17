# mimizam

**mimizam**は音声指紋（Audio Fingerprinting）と識別のためのShazam風アルゴリズムのPython実装です。音声からユニークな指紋を生成し、データベースと照合することで高精度な音楽識別を実現します。

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-yellowgreen.svg)]()

## 主な機能

- **高精度音声指紋生成**: Shazamアルゴリズムベースの指紋生成
- **適応パラメータ最適化**: 音声特性に応じた自動パラメータ調整
- **マルチデータベース対応**: SQLite、MySQL、PostgreSQL、Elasticsearch
- **リアルタイム音声識別**: 短い音声クリップから楽曲を特定
- **可視化機能**: スペクトログラムとピーク検出の可視化

## クイックスタート

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam

# 依存関係をインストール
pip install -r requirements.txt

# パッケージをインストール（開発モード）
pip install -e .
```

### 基本的な使用方法

```python
from mimizam import create_mimizam_sqlite

# SQLiteを使用した簡単なセットアップ
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲をデータベースに追加
    song_id = mimizam.add_song("path/to/song.wav", "My Song", "Artist Name")
    print(f"楽曲が追加されました (ID: {song_id})")
    
    # 音声検索
    results = mimizam.search_song("path/to/query.wav", min_confidence=0.3)
    for result in results:
        song = result['song']
        confidence = result['confidence']
        print(f"発見: {song.title} by {song.artist} (信頼度: {confidence:.2%})")
    
    # 音声識別（最も可能性の高い楽曲）
    identified = mimizam.identify_audio("path/to/query.wav")
    if identified:
        song, confidence = identified
        print(f"識別結果: {song.title} (信頼度: {confidence:.2%})")
```

### デモの実行

```bash
# デモ用音声ファイルを生成
python scripts/create_demo_audio.py

# Mimizamデモを実行
python examples/mimizam_demo.py

```

## アーキテクチャ

### コア技術

1. **スペクトログラム生成**: 短時間フーリエ変換（STFT）による時間-周波数解析
2. **適応ピーク検出**: 音声特性に応じた動的閾値によるスペクトルピーク抽出
3. **ハッシュベース指紋**: アンカー・ターゲットピークペアからSHA-256ハッシュ生成
4. **インテリジェントマッチング**: 時間アライメントと信頼度スコアリング

## データベースバックエンド

mimizamは複数のデータベースに対応：

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch
)

# SQLite（簡単・高速・推奨）
mimizam = create_mimizam_sqlite("fingerprints.db")

# MySQL（拡張性）
mimizam = create_mimizam_mysql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# PostgreSQL（高性能）
mimizam = create_mimizam_postgresql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# Elasticsearch（分散検索）
mimizam = create_mimizam_elasticsearch(
    host="localhost", index_name="music_index"
)
```

## プロジェクト構造

```
mimizam/
├── src/
│   ├── mimizam.py                    # 統合高レベルAPI
│   ├── audio_fingerprinter.py        # 音声指紋生成
│   ├── fingerprint_database.py       # データベース管理
│   ├── database_backends.py          # 統一バックエンド
│   ├── adaptive_parameters.py        # 適応パラメータ調整
│   ├── parallel_processing.py        # 並列処理サポート
│   └── backends/                     # 個別バックエンド実装
├── examples/
│   ├── mimizam_demo.py               # APIデモ
│   ├── video_search.py.py  　　　　　　# 動画音声検索
│   └── video_fingerprinter.py        # 動画音声処理
├── test_media/                       # デモ用音声ファイル
├── tests/                           # テストスイート
├── docs/                            # ドキュメント
└── scripts/                         # ユーティリティ
```

## 使用例

### 音声検索
```python
# 短い音声クリップから楽曲を識別
results = mimizam.search_song("humming.wav", top_k=3)
```

### カスタム音声読み込み

```python
import numpy as np

# 独自の音声データから指紋生成
audio_data = np.array([...])  # 音声サンプル
fingerprints = fingerprinter.fingerprint_audio(audio_data, sr=22050)
```

### 音声登録

```python
import glob
from pathlib import Path

# ファイルの登録処理
audio_files = glob.glob("music/*.wav")
with create_mimizam_sqlite("batch.db") as mimizam:
    for file_path in audio_files:
        title = Path(file_path).stem
        mimizam.add_song(file_path, title, "Unknown Artist")
```

### 可視化

```python
# スペクトログラムとピーク検出の可視化
audio = fingerprinter.load_audio("song.wav")
fingerprinter.visualize_analysis(audio, title="song.wav")
```

### カスタム設定

```python
# 高精度設定
fingerprinter = AudioFingerprinter(
    n_fft=4096,           # より高い周波数解像度
    hop_length=256,       # より細かい時間解像度
    min_amplitude=-50     # より敏感な検出
)
```

## 性能向上のヒント

1. **音声品質**: 高品質音声（44.1kHz以上）で最良結果
2. **サンプル長**: 10秒以上で識別精度向上
3. **適応パラメータ**: enable_adaptive_params=Trueで高速化
4. **データベース選択**: 小規模ならSQLite、大規模ならPostgreSQL

## テスト

```bash
# 全テスト実行
python run_tests.py

```

## ドキュメント

詳細なドキュメントは`docs/`ディレクトリに含まれています：

- [データベースセットアップ](docs/DATABASE_SETUP.md)
- [指紋生成詳細](docs/fingerprint_generation_details.md)
- [指紋スコアリング詳細](docs/fingerprint_scoring_details.md)

## ライセンス

mimizamは[MITライセンス](LICENSE)の下で公開されています。

## 謝辞

- [Avery Li-Chun Wang](https://www.ee.columbia.edu/~dpwe/papers/Wang03-shazam.pdf)によるオリジナルShazamアルゴリズム
- 音声処理ライブラリ[librosa](https://librosa.org/)
- 各種オープンソース音声指紋実装からのインスピレーション
  - [dejavu GitHub](https://github.com/worldveil/dejavu)
  - [audfprint GitHub](https://github.com/dpwe/audfprint)

## 参考文献

- Wang, A. L. C. (2003). "An Industrial Strength Audio Search Algorithm"
- Ellis, D. P. W. (2009). "Robust Landmark-Based Audio Fingerprinting"
- Cano, P. et al. (2005). "A Review of Audio Fingerprinting"

---

**注意**: この実装は個人の趣味で作成されました。商用システムと同等の性能を保証するものではありません。

