# 概要とクイックスタート

## mimizamとは

**mimizam**は音声指紋（Audio Fingerprinting）と識別のためのShazam風アルゴリズムのPython実装です。音声からユニークな指紋を生成し、データベースと照合することで高精度な音楽識別を実現します。

## 🎯 主な用途

- **音楽識別アプリケーション**: Shazamのような楽曲識別機能の構築
- **音声検索システム**: 大規模音声ライブラリからの検索機能
- **重複音声検出**: 音声コンテンツの重複チェック
- **音声推薦システム**: 類似音声の発見と推薦
- **メディア管理**: 音声・動画ファイルの自動分類

## 🚀 主な機能

### 高精度音声指紋生成
- Shazamアルゴリズムベースの指紋生成
- スペクトログラム解析による特徴抽出
- アンカー・ターゲットペア方式のハッシュ生成

### 適応パラメータ最適化
- 音声特性に応じた自動パラメータ調整
- リアルタイムでの処理最適化
- ジャンル特性を考慮した調整

### マルチデータベース対応
- **SQLite**: 軽量、ファイルベース（開発・小規模用途）
- **MySQL**: 高性能、スケーラブル（本番環境）
- **PostgreSQL**: 堅牢、機能豊富（複雑なクエリ）
- **Elasticsearch**: 全文検索、分散処理（大規模検索）

### リアルタイム音声識別
- 短い音声クリップ（5-10秒）から楽曲特定
- ノイズ耐性と速度・ピッチ変動対応
- 部分音声からの識別

### 可視化機能
- スペクトログラムとピーク検出の可視化
- 指紋生成プロセスの視覚的確認
- デバッグ支援機能

## 🏗️ システムアーキテクチャ

mimizamは4つの主要レイヤーで構成されています：

### 1. 高レベルAPI層
```python
from mimizam import create_mimizam_sqlite, create_mimizam_mysql

# 統合されたインターフェース
mimizam = create_mimizam_sqlite("music.db")
```

### 2. 音声処理エンジン
```python
from mimizam import AudioFingerprinter, SpectrogramAnalyzer, HashGenerator

# コア音声処理コンポーネント
fingerprinter = AudioFingerprinter()
```

### 3. データベース・マッチング層
```python
from mimizam import FingerprintDatabase, FingerprintMatcher

# データベース管理とマッチング
database = FingerprintDatabase(config)
```

### 4. アプリケーション・ツール層
```bash
# CLI ツールとデモアプリケーション
python examples/video_search.py
python examples/mimizam_demo.py
```

## 🚀 クイックスタート

### 1. 基本的な音声識別

```python
from mimizam import create_mimizam_sqlite

# SQLiteを使用した簡単なセットアップ
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲をデータベースに追加
    song_id = mimizam.add_song("path/to/song.wav", "My Song", "Artist Name")
    print(f"楽曲が追加されました (ID: {song_id})")
    
    # 音声検索（複数結果）
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

### 2. バッチ処理

```python
import glob
from pathlib import Path

# 複数ファイルの一括登録
audio_files = glob.glob("music/*.wav")
with create_mimizam_sqlite("batch.db") as mimizam:
    for file_path in audio_files:
        title = Path(file_path).stem
        song_id = mimizam.add_song(file_path, title, "Unknown Artist")
        print(f"登録完了: {title} (ID: {song_id})")
```

### 3. 可視化

```python
from mimizam import AudioFingerprinter

# スペクトログラムとピーク検出の可視化
fingerprinter = AudioFingerprinter()
audio = fingerprinter.load_audio("song.wav")
fingerprinter.visualize_analysis(audio, title="song.wav")
```

## 📊 性能特性

### 処理速度
- **指紋生成**: 約1-2秒/分の音声（標準設定）
- **検索速度**: 1万曲データベースで約100-500ms
- **メモリ使用量**: 約50-100MB（標準的な楽曲データベース）

### 精度
- **識別精度**: 90%以上（10秒以上の音声、低ノイズ環境）
- **ノイズ耐性**: SNR 10dB以上で安定動作
- **速度変動**: 0.8x-1.2x の速度変化に対応

### スケーラビリティ
- **SQLite**: 1万曲程度まで
- **MySQL/PostgreSQL**: 10万曲以上
- **Elasticsearch**: 100万曲以上の大規模対応

## 🔧 カスタマイズ

### 高精度設定
```python
fingerprinter = AudioFingerprinter(
    n_fft=4096,           # より高い周波数解像度
    hop_length=256,       # より細かい時間解像度
    min_amplitude=-50     # より敏感な検出
)
```

### 高速設定
```python
fingerprinter = AudioFingerprinter(
    n_fft=1024,           # 高速処理
    hop_length=512,       # 粗い時間解像度
    enable_adaptive_params=True  # 適応最適化
)
```

## 📈 性能向上のヒント

1. **音声品質**: 高品質音声（44.1kHz以上）で最良結果
2. **サンプル長**: 10秒以上で識別精度向上
3. **適応パラメータ**: `enable_adaptive_params=True`で高速化
4. **データベース選択**: 小規模ならSQLite、大規模ならPostgreSQL
5. **インデックス最適化**: データベースインデックスの適切な設定

## 🔗 次のステップ

- [インストールガイド](./02_installation.md) - 詳細なセットアップ手順
- [基本的な使用方法](./03_basic_usage.md) - より詳細な使用例
- [データベース設定](./05_database_setup.md) - データベース選択と設定
- [実装例](./06_basic_examples.md) - 実践的なサンプルコード
