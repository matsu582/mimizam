# よくある質問（FAQ）

mimizamプロジェクトの使用、開発、トラブルシューティングに関してよく寄せられる質問とその回答をまとめました。初心者から上級者まで、様々なレベルの質問に対応しています。

## 🚀 基本的な使用方法

### Q1: mimizamとは何ですか？

**A:** mimizamは、Shazam風の音声指紋技術を実装したPythonライブラリです。音声ファイルから特徴的な「指紋」を生成し、高速な楽曲識別を可能にします。

主な特徴：
- 高速な楽曲識別（< 0.1秒）
- 複数のデータベースバックエンド対応（SQLite、MySQL、PostgreSQL、Elasticsearch）
- ノイズ耐性の高い識別アルゴリズム
- スケーラブルな設計（数百万曲対応）

### Q2: mimizamをインストールするにはどうすればよいですか？

**A:** 以下の方法でインストールできます：

```bash
# PyPIからインストール（推奨）
pip install mimizam

# 開発版をGitHubからインストール
pip install git+https://github.com/animalmatsuzawa/mimizam.git

# ローカル開発用
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam
pip install -e .
```

詳細は[インストールガイド](./02_installation.md)を参照してください。

### Q3: 最初の楽曲識別を行うにはどうすればよいですか？

**A:** 以下の簡単なコードで始められます：

```python
from mimizam import create_mimizam_sqlite

# データベース作成
mimizam = create_mimizam_sqlite("my_music.db")

# 楽曲追加
song_id = mimizam.add_song(
    file_path="my_song.wav",
    title="My Favorite Song",
    artist="Great Artist"
)

# 楽曲検索
results = mimizam.search_song("query_audio.wav")
print(f"検索結果: {results}")
```

詳細は[基本的な使用方法](./03_basic_usage.md)を参照してください。

### Q4: 対応している音声形式は何ですか？

**A:** mimizamは以下の音声形式に対応しています：

**対応形式:**
- WAV（推奨）
- MP3
- FLAC
- M4A/AAC
- OGG

**推奨設定:**
- サンプルレート: 22050 Hz（自動変換）
- チャンネル: モノラル（自動変換）
- ビット深度: 16bit以上

### Q5: どのくらいの長さの音声が必要ですか？

**A:** 識別精度は音声の長さに依存します：

- **最小長**: 3-5秒（基本的な識別可能）
- **推奨長**: 10-30秒（高精度識別）
- **最大長**: 制限なし（長いほど精度向上、処理時間は比例）

短い音声でも識別可能ですが、精度が低下する可能性があります。

## 🔧 技術的な質問

### Q6: Shazamアルゴリズムとは何ですか？

**A:** Shazamアルゴリズムは以下のステップで動作します：

1. **スペクトログラム生成**: 音声を時間-周波数表現に変換
2. **ピーク検出**: スペクトログラム上の局所最大値を特定
3. **コンステレーションマップ**: ピークの組み合わせから特徴点を生成
4. **ハッシュ生成**: 特徴点から固有のハッシュ値を計算
5. **高速検索**: ハッシュテーブルによる高速マッチング

詳細は[指紋生成詳細](./13_fingerprint_generation.md)を参照してください。

### Q7: なぜNumba最適化を使用するのですか？

**A:** Numba最適化により以下の利点があります：

- **処理速度向上**: 5-10倍の高速化
- **メモリ効率**: JITコンパイルによる最適化
- **透明性**: コード変更なしで高速化
- **自動最適化**: 実行時の動的最適化

```python
# Numba最適化の有効化
from mimizam import AudioFingerprinter

# 最適化あり（推奨）
fingerprinter = AudioFingerprinter(enable_numba_optimization=True)

# 最適化なし（デバッグ用）
fingerprinter = AudioFingerprinter(enable_numba_optimization=False)
```

### Q8: 複数のデータベースバックエンドを同時に使用できますか？

**A:** はい、mimizamは複数のバックエンドを同時に使用できます：

```python
from mimizam import create_mimizam_sqlite, create_mimizam_mysql

# 複数のmimizamインスタンス
sqlite_mimizam = create_mimizam_sqlite("local.db")
mysql_mimizam = create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)

# 用途に応じて使い分け
# 高速検索: SQLite
# 大規模データ: MySQL
```

### Q9: 楽曲の重複を検出するにはどうすればよいですか？

**A:** 以下の方法で重複検出が可能です：

```python
def detect_duplicates(mimizam, threshold=0.8):
    """楽曲重複検出"""
    
    songs = mimizam.list_songs()
    duplicates = []
    
    for i, song1 in enumerate(songs):
        for song2 in songs[i+1:]:
            # 楽曲間の類似度計算
            similarity = calculate_similarity(song1, song2)
            
            if similarity > threshold:
                duplicates.append({
                    'song1': song1,
                    'song2': song2,
                    'similarity': similarity
                })
    
    return duplicates
```

## 🔧 トラブルシューティング

### Q10: "No fingerprints generated"エラーが発生します

**A:** このエラーは以下の原因が考えられます：

**原因と対策:**

1. **音声レベルが低い**
   ```python
   # 音声レベルを確認
   import numpy as np
   rms = np.sqrt(np.mean(audio**2))
   print(f"RMS レベル: {rms}")
   
   # 閾値を下げる
   fingerprinter = AudioFingerprinter(min_amplitude=-70)
   ```

2. **音声が短すぎる**
   ```python
   # 音声長を確認
   duration = len(audio) / 22050
   print(f"音声長: {duration:.2f}秒")
   
   # 最低3秒以上を推奨
   ```

3. **無音または単調な音声**
   ```python
   # スペクトログラムを確認
   import matplotlib.pyplot as plt
   import librosa
   
   S = librosa.stft(audio)
   plt.figure(figsize=(10, 4))
   librosa.display.specshow(librosa.amplitude_to_db(np.abs(S)))
   plt.show()
   ```

### Q11: データベース接続エラーが発生します

**A:** データベース別の対処法：

**SQLite:**
```python
import os

# ファイルパスを確認
db_path = "my_music.db"
if not os.path.exists(os.path.dirname(db_path)):
    os.makedirs(os.path.dirname(db_path))

# 権限を確認
if os.path.exists(db_path):
    print(f"ファイル権限: {oct(os.stat(db_path).st_mode)[-3:]}")
```

**MySQL:**
```python
import mysql.connector

# 接続テスト
try:
    connection = mysql.connector.connect(
        host='localhost',
        database='test_db',
        user='username',
        password='password',
        connection_timeout=10
    )
    print("MySQL接続成功")
    connection.close()
except mysql.connector.Error as e:
    print(f"MySQL接続エラー: {e}")
```

### Q12: メモリ使用量が多すぎます

**A:** メモリ使用量を削減する方法：

```python
import gc

def process_large_dataset_efficiently(file_paths, batch_size=10):
    """大規模データセットの効率的処理"""
    
    from mimizam import create_mimizam_sqlite
    import librosa
    
    mimizam = create_mimizam_sqlite("large_dataset.db")
    
    for i in range(0, len(file_paths), batch_size):
        batch = file_paths[i:i+batch_size]
        
        # バッチ処理
        for file_path in batch:
            try:
                # ファイル名から情報を推測
                title = os.path.splitext(os.path.basename(file_path))[0]
                artist = "Unknown"
                
                # 楽曲を追加
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"処理完了: {title} (ID: {song_id})")
                
            except Exception as e:
                print(f"処理エラー {file_path}: {e}")
        
        # メモリクリーンアップ
        gc.collect()
        print(f"バッチ {i//batch_size + 1} 完了")
    
    mimizam.close()
```

## 🚀 パフォーマンス最適化

### Q13: 処理速度を向上させるにはどうすればよいですか？

**A:** 以下の最適化手法を試してください：

**1. Numba最適化の有効化**
```python
fingerprinter = AudioFingerprinter(enable_numba_optimization=True)
```

**2. パラメータ調整**
```python
# 高速化重視の設定
fast_fingerprinter = AudioFingerprinter(
    n_fft=1024,        # 小さなFFTサイズ
    hop_length=512,    # 大きなホップ長
    enable_numba_optimization=True
)
```

**3. 並列処理**
```python
from concurrent.futures import ThreadPoolExecutor
import os

def parallel_processing(file_paths, max_workers=None):
    """並列処理による高速化"""
    
    if max_workers is None:
        max_workers = os.cpu_count()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_file, path) 
            for path in file_paths
        ]
        
        results = [future.result() for future in futures]
    
    return results
```

### Q14: 大規模データベースでの検索が遅いです

**A:** データベース最適化の方法：

**インデックス最適化:**
```python
# SQLiteの場合
def optimize_sqlite_database(db_path):
    """SQLiteデータベース最適化"""
    
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # インデックス作成
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fingerprints_hash 
        ON fingerprints(hash)
    """)
    
    # VACUUM実行
    cursor.execute("VACUUM")
    
    # ANALYZE実行
    cursor.execute("ANALYZE")
    
    conn.close()
```

**キャッシュ活用:**
```python
from functools import lru_cache

class CachedMimizam:
    """キャッシュ機能付きmimizam"""
    
    def __init__(self, mimizam):
        self.mimizam = mimizam
    
    @lru_cache(maxsize=1000)
    def cached_search(self, audio_hash):
        """キャッシュ付き検索"""
        return self.mimizam.search_fingerprints(audio_hash)
```

## 🔄 データ管理

### Q15: データベースをバックアップするにはどうすればよいですか？

**A:** バックエンド別のバックアップ方法：

**SQLite:**
```python
import shutil
import datetime

def backup_sqlite(db_path):
    """SQLiteバックアップ"""
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    shutil.copy2(db_path, backup_path)
    print(f"バックアップ作成: {backup_path}")
    
    return backup_path
```

**MySQL:**
```python
import subprocess

def backup_mysql(host, database, username, password, output_file):
    """MySQLバックアップ"""
    
    cmd = [
        'mysqldump',
        f'--host={host}',
        f'--user={username}',
        f'--password={password}',
        database
    ]
    
    with open(output_file, 'w') as f:
        subprocess.run(cmd, stdout=f, check=True)
    
    print(f"MySQLバックアップ作成: {output_file}")
```

### Q16: データベース間でデータを移行するにはどうすればよいですか？

**A:** 移行ツールを使用してください：

```python
from mimizam.scripts.migrate_database import DatabaseMigrator
from mimizam import DatabaseConfig

# 移行ツール初期化
migrator = DatabaseMigrator()

# 移行元設定
source_config = DatabaseConfig(
    backend='sqlite',
    file_path='source.db'
)

# 移行先設定
target_config = DatabaseConfig(
    backend='mysql',
    host='localhost',
    database='target_db',
    username='user',
    password='password'
)

# 移行実行
migrator.migrate(source_config, target_config)
```

詳細は[データベース移行ツール](./19_migration_tools.md)を参照してください。

## 🎵 音声処理

### Q17: 対応していない音声形式を処理するにはどうすればよいですか？

**A:** FFmpegを使用して変換してください：

```python
import subprocess
import tempfile
import os

def convert_audio_format(input_path, output_format='wav'):
    """音声形式変換"""
    
    # 一時ファイル作成
    with tempfile.NamedTemporaryFile(suffix=f'.{output_format}', delete=False) as temp_file:
        output_path = temp_file.name
    
    # FFmpegで変換
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ar', '22050',      # サンプルレート
        '-ac', '1',          # モノラル
        '-y',                # 上書き
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"変換エラー: {e}")
        os.unlink(output_path)
        return None

# 使用例
converted_path = convert_audio_format('input.m4a', 'wav')
if converted_path:
    # mimizamで処理
    song_id = mimizam.add_song(converted_path, "Song Title", "Artist")
    os.unlink(converted_path)  # 一時ファイル削除
```

### Q18: 音声の品質が低い場合の対処法は？

**A:** 以下の前処理を試してください：

```python
import librosa
import numpy as np
from scipy import signal

def enhance_audio_quality(audio, sr=22050):
    """音声品質向上"""
    
    # 1. ノイズ除去（簡易版）
    # スペクトラルサブトラクション
    S = librosa.stft(audio)
    magnitude = np.abs(S)
    phase = np.angle(S)
    
    # ノイズ推定（最初の0.5秒）
    noise_frame_count = int(0.5 * sr / 512)
    noise_spectrum = np.mean(magnitude[:, :noise_frame_count], axis=1, keepdims=True)
    
    # スペクトラルサブトラクション
    alpha = 2.0  # サブトラクション係数
    enhanced_magnitude = magnitude - alpha * noise_spectrum
    enhanced_magnitude = np.maximum(enhanced_magnitude, 0.1 * magnitude)
    
    # 音声復元
    enhanced_S = enhanced_magnitude * np.exp(1j * phase)
    enhanced_audio = librosa.istft(enhanced_S)
    
    # 2. 正規化
    enhanced_audio = enhanced_audio / np.max(np.abs(enhanced_audio)) * 0.8
    
    return enhanced_audio

# 使用例
enhanced_audio = enhance_audio_quality(original_audio)
fingerprints = fingerprinter.fingerprint_audio(enhanced_audio)
```

## 🔍 デバッグ

### Q19: デバッグ情報を出力するにはどうすればよいですか？

**A:** ログ設定を調整してください：

```python
import logging

# ログ設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mimizam_debug.log'),
        logging.StreamHandler()
    ]
)

# mimizamのログレベル設定
logger = logging.getLogger('mimizam')
logger.setLevel(logging.DEBUG)

# 詳細な処理情報が出力される
fingerprints = fingerprinter.fingerprint_audio(audio)
```

### Q20: 処理が途中で止まってしまいます

**A:** 以下の診断を行ってください：

```python
import signal
import time

class TimeoutHandler:
    """タイムアウトハンドラー"""
    
    def __init__(self, timeout_seconds=30):
        self.timeout_seconds = timeout_seconds
    
    def __enter__(self):
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.timeout_seconds)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.alarm(0)
    
    def _timeout_handler(self, signum, frame):
        raise TimeoutError(f"処理がタイムアウトしました ({self.timeout_seconds}秒)")

# 使用例
try:
    with TimeoutHandler(timeout_seconds=60):
        fingerprints = fingerprinter.fingerprint_audio(audio)
        print(f"指紋生成完了: {len(fingerprints)}個")
except TimeoutError as e:
    print(f"タイムアウトエラー: {e}")
    # 音声を短く分割して再試行
    chunk_size = len(audio) // 4
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
        chunk_fingerprints = fingerprinter.fingerprint_audio(chunk)
        print(f"チャンク {i//chunk_size + 1}: {len(chunk_fingerprints)}個")
```

## 📊 統計・分析

### Q21: データベースの統計情報を取得するにはどうすればよいですか？

**A:** 統計情報取得の方法：

```python
def get_database_statistics(mimizam):
    """データベース統計情報取得"""
    
    stats = {
        'songs': {},
        'fingerprints': {},
        'performance': {}
    }
    
    # 楽曲統計
    songs = mimizam.list_songs()
    stats['songs'] = {
        'total_count': len(songs),
        'artists': len(set(song.artist for song in songs)),
        'avg_title_length': np.mean([len(song.title) for song in songs])
    }
    
    # 指紋統計（サンプリング）
    sample_songs = songs[:min(100, len(songs))]
    fingerprint_counts = []
    
    for song in sample_songs:
        # 楽曲の指紋数を取得（実装依存）
        count = get_fingerprint_count_for_song(mimizam, song.id)
        fingerprint_counts.append(count)
    
    stats['fingerprints'] = {
        'avg_per_song': np.mean(fingerprint_counts),
        'std_per_song': np.std(fingerprint_counts),
        'estimated_total': np.mean(fingerprint_counts) * len(songs)
    }
    
    return stats

# 使用例
stats = get_database_statistics(mimizam)
print(f"楽曲数: {stats['songs']['total_count']}")
print(f"アーティスト数: {stats['songs']['artists']}")
print(f"平均指紋数/曲: {stats['fingerprints']['avg_per_song']:.1f}")
```

## 🔗 関連ドキュメント

- [基本的な使用方法](./03_basic_usage.md) - 基本操作
- [インストールガイド](./02_installation.md) - セットアップ
- [データベース設定](./10_database_setup.md) - データベース構成
- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決
- [高度な使用例](./17_advanced_examples.md) - 応用技術

## 💡 よくある質問のベストプラクティス

### 1. 問題の特定
- エラーメッセージの詳細な記録
- 再現手順の明確化
- 環境情報の収集

### 2. 段階的な解決
- 簡単な解決策から試行
- 一つずつ変更を適用
- 結果の確認と記録

### 3. 予防的対策
- 定期的なバックアップ
- 監視とログの活用
- ドキュメントの参照

mimizamを効果的に活用するため、これらのFAQを参考にしてください。さらに詳しい情報が必要な場合は、関連ドキュメントを参照するか、GitHubのIssueで質問してください。
