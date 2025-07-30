# よくある質問（FAQ）（レガシー）

**注意**: このファイルは古いFAQです。最新のよくある質問については、[よくある質問（FAQ）](./19_faq.md)を参照してください。

mimizamプロジェクトの使用、開発、トラブルシューティングに関してよく寄せられる質問とその回答をまとめました。初心者から上級者まで、様々なレベルの質問に対応しています。

## 🎯 この章で解決できること

- インストールや設定の問題
- 基本的な使用方法の疑問
- パフォーマンスに関する課題
- エラーメッセージの対処法
- 実装時のベストプラクティス

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
# GitHubからインストール
pip install git+https://github.com/animalmatsuzawa/mimizam.git

# ローカル開発用
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam
pip install -e .
```

詳細は[インストールガイド](./02_installation.md)を参照してください。

### Q3: 最初の楽曲識別を行うにはどうすればよいですか？

**A:** 以下のコードで始められます：

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
- WAV
- MP3
- FLAC
- M4A/AAC
- OGG

**設定:**
- サンプルレート: 22050 Hz（自動変換）
- チャンネル: モノラル（自動変換）
- ビット深度: 16bit以上

### Q5: どのくらいの長さの音声が必要ですか？

**A:** 識別精度は音声の長さに依存します：

- **最小長**: 3-5秒（基本的な識別可能）
- **標準長**: 10-30秒（高精度識別）
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

詳細は[システムアーキテクチャ](./04_architecture.md)を参照してください。

### Q7: Numba機能について教えてください

**A:** mimizamにはNumba JIT機能が実装されていますが、現在はデフォルトで無効化されています：

**現在の状況:**
- ベンチマーク結果で処理速度の優位性が確認されていない
- ピークオーバーフロー問題により最大ピーク数が制限される
- `SpectrogramAnalyzer`ではデフォルトで`enable_numba_optimization=False`に設定

```python
from mimizam import AudioFingerprinter

# デフォルト設定（Numba機能は無効）
fingerprinter = AudioFingerprinter()

# 実験的に有効化する場合
fingerprinter = AudioFingerprinter(enable_numba_optimization=True)
```

**注意:** 現在のバージョンでは、Numba機能を有効にしても性能向上は期待できません。

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
   
   # 最低3秒以上
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

## 🚀 パフォーマンス設定

### Q13: 処理速度を向上させるにはどうすればよいですか？

**A:** 以下の設定手法を試してください：

**1. パラメータ調整による高速化**
```python
# 高速化重視の設定（精度とのトレードオフ）
fast_fingerprinter = AudioFingerprinter(
    n_fft=1024,        # 小さなFFTサイズ
    hop_length=512,    # 大きなホップ長
    min_amplitude=-40  # 閾値を上げて処理量削減
)
```

**2. データベース設定の調整**
```python
# SQLiteの場合、WALモードで高速化
mimizam = create_mimizam_sqlite("music.db")

# 大規模データの場合はMySQLやPostgreSQLを検討
mimizam = create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)
```

**注意:** Numba機能は現在無効化されており、有効にしても性能向上は期待できません（Q7参照）。

### Q14: 大規模データベースでの検索が遅いです

**A:** データベース設定の方法：

**インデックス設定:**
```python
# SQLiteの場合
def optimize_sqlite_database(db_path):
    """SQLiteデータベース設定"""
    
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

**データベース設定:**
```python
# SQLiteの場合、適切なデータベース設定を使用
mimizam = create_mimizam_sqlite("optimized_music.db")

# 大量データの場合はMySQLを検討
mimizam = create_mimizam_mysql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)
```

## 🔄 データ管理



## 🎵 音声処理

### Q15: 対応していない音声形式を処理するにはどうすればよいですか？

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


## 🔍 デバッグ

### Q16: デバッグ情報を出力するにはどうすればよいですか？

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


## 🔗 関連ドキュメント

- [基本的な使用方法](./03_basic_usage.md) - 基本操作
- [インストールガイド](./02_installation.md) - セットアップ
- [データベース設定](./05_database_setup.md) - データベース構成
- [基本的な使用例](./06_basic_examples.md) - 実践的なサンプルコード

mimizamを効果的に活用するため、これらのFAQを参考にしてください。さらに詳しい情報が必要な場合は、関連ドキュメントを参照するか、GitHubのIssueで質問してください。
