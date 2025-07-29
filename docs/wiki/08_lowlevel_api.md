# 低レベルAPI

mimizamの低レベルAPIを使用することで、音声指紋生成とデータベース操作の詳細な制御が可能になります。統合されたMimizamクラスでは提供されない高度な機能やカスタマイズが必要な場合に使用します。

## 🎯 低レベルAPIの概要

低レベルAPIは以下の主要コンポーネントで構成されています：

- **AudioFingerprinter**: 音声指紋生成の直接制御
- **FingerprintDatabase**: データベース操作の詳細制御
- **SpectrogramAnalyzer**: スペクトログラム解析の詳細設定
- **HashGenerator**: ハッシュ生成アルゴリズムの直接操作

## 🔧 AudioFingerprinter 詳細API

### 基本的な初期化と設定

```python
from mimizam import AudioFingerprinter, Peak
import numpy as np

# 詳細パラメータでの初期化
fingerprinter = AudioFingerprinter(
    n_fft=2048,                    # FFTウィンドウサイズ
    hop_length=512,                # ホップ長
    sr=22050,                      # サンプルレート
    min_amplitude=-60,             # 最小振幅閾値（dB）
    peak_neighborhood_size=10,     # ピーク検出近傍サイズ
    enable_adaptive_params=True,   # 適応パラメータ調整
    audible_only=False,           # 可聴域制限
    enable_numba_optimization=True # Numba最適化
)

print(f"設定されたパラメータ:")
print(f"- FFTサイズ: {fingerprinter.spectrogram_analyzer.n_fft}")
print(f"- ホップ長: {fingerprinter.spectrogram_analyzer.hop_length}")
print(f"- サンプルレート: {fingerprinter.spectrogram_analyzer.sr}")
```

### 段階的な音声処理

```python
import librosa

# 1. 音声ファイルの読み込み
audio_path = "path/to/audio.wav"
audio, sr = librosa.load(audio_path, sr=fingerprinter.spectrogram_analyzer.sr)

# 2. スペクトログラム生成
spectrogram_analyzer = fingerprinter.spectrogram_analyzer
magnitude, phase = spectrogram_analyzer.compute_spectrogram(audio)

print(f"スペクトログラム形状: {magnitude.shape}")
print(f"時間軸: {magnitude.shape[1]} フレーム")
print(f"周波数軸: {magnitude.shape[0]} ビン")

# 3. ピーク検出
peaks = spectrogram_analyzer.find_peaks(magnitude)
print(f"検出されたピーク数: {len(peaks)}")

# ピーク詳細の表示
for i, peak in enumerate(peaks[:5]):  # 最初の5個を表示
    print(f"ピーク {i+1}: 時間={peak.time:.3f}s, 周波数={peak.frequency:.1f}Hz, 振幅={peak.amplitude:.1f}dB")

# 4. ハッシュ生成
hash_generator = fingerprinter.hash_generator
fingerprints = hash_generator.generate_hashes(peaks)

print(f"生成された指紋数: {len(fingerprints)}")
```

### カスタムピーク検出

```python
def detect_custom_peaks(magnitude: np.ndarray, sr: int, hop_length: int, 
                       min_amplitude: float = -50, neighborhood_size: int = 15) -> List[Peak]:
    """カスタムピーク検出アルゴリズム"""
    from mimizam import Peak
    import numpy as np
    
    peaks = []
    
    # 動的閾値の計算
    local_mean = np.mean(magnitude, axis=0)
    dynamic_threshold = np.percentile(local_mean, 75)  # 75パーセンタイル
    
    for t_idx in range(magnitude.shape[1]):
        for f_idx in range(magnitude.shape[0]):
            amplitude = magnitude[f_idx, t_idx]
            
            if amplitude > max(min_amplitude, dynamic_threshold):
                # 近傍での局所最大値チェック
                if is_local_maximum(magnitude, f_idx, t_idx, neighborhood_size):
                    time = t_idx * hop_length / sr
                    frequency = f_idx * sr / (2 * magnitude.shape[0])
                    
                    peak = Peak(
                        time=np.float64(time),
                        frequency=np.float64(frequency),
                        amplitude=np.float64(amplitude)
                    )
                    peaks.append(peak)
    
    return peaks

def is_local_maximum(magnitude: np.ndarray, f_idx: int, t_idx: int, neighborhood_size: int) -> bool:
    """局所最大値判定"""
    center_value = magnitude[f_idx, t_idx]
    
    # 近傍領域の定義
    f_start = max(0, f_idx - neighborhood_size // 2)
    f_end = min(magnitude.shape[0], f_idx + neighborhood_size // 2 + 1)
    t_start = max(0, t_idx - neighborhood_size // 2)
    t_end = min(magnitude.shape[1], t_idx + neighborhood_size // 2 + 1)
    
    # 近傍での最大値チェック
    neighborhood = magnitude[f_start:f_end, t_start:t_end]
    return center_value >= np.max(neighborhood)

# カスタム検出器の使用
custom_peaks = detect_custom_peaks(magnitude, sr, hop_length, min_amplitude=-55, neighborhood_size=20)

print(f"カスタム検出器によるピーク数: {len(custom_peaks)}")
```

### 高度なハッシュ生成

```python
from mimizam.database_base import Fingerprint
import hashlib

def generate_robust_hashes(peaks: List[Peak], target_zone_size: int = 5, 
                          freq_tolerance: int = 50) -> List[Fingerprint]:
    """ロバストなハッシュ生成"""
    from mimizam import HashGenerator
    import hashlib
    
    # 実際のHashGeneratorを使用
    hash_generator = HashGenerator()
    fingerprints = hash_generator.generate_fingerprints(peaks)
    
    # 追加のロバスト性向上処理
    robust_fingerprints = []
    sorted_peaks = sorted(peaks, key=lambda p: p.time)
    
    for i, anchor in enumerate(sorted_peaks):
        # ターゲットゾーン内のピークを検索
        targets = find_target_peaks_in_zone(anchor, sorted_peaks[i+1:], target_zone_size)
        
        for target in targets:
            # 基本的なハッシュ生成
            hash_value = generate_frequency_hash(anchor, target)
            if hash_value:
                fingerprint = Fingerprint(
                            hash_value=hash_value,
                            time_offset=anchor.time
                        )
                        fingerprints.append(fingerprint)
        
        return fingerprints
    
    def _find_target_peaks(self, anchor: Peak, candidates: List[Peak]) -> List[Peak]:
        """ターゲットピークの検索"""
        targets = []
        
        for candidate in candidates:
            time_diff = candidate.time - anchor.time
            freq_diff = abs(candidate.frequency - anchor.frequency)
            
            # ターゲットゾーン内かチェック
            if (0.1 <= time_diff <= 2.0 and 
                freq_diff <= self.freq_tolerance and
                len(targets) < self.target_zone_size):
                targets.append(candidate)
        
        return targets
    
    def _generate_frequency_hash(self, anchor: Peak, target: Peak) -> str:
        """周波数ベースハッシュ"""
        freq_diff = int(target.frequency - anchor.frequency)
        time_diff = int((target.time - anchor.time) * 1000)  # ミリ秒
        
        hash_input = f"freq:{anchor.frequency:.0f}:{freq_diff}:{time_diff}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def _generate_time_delta_hash(self, anchor: Peak, target: Peak) -> str:
        """時間差ベースハッシュ"""
        time_ratio = target.time / (anchor.time + 1e-10)
        freq_ratio = target.frequency / (anchor.frequency + 1e-10)
        
        hash_input = f"ratio:{time_ratio:.3f}:{freq_ratio:.3f}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def _generate_amplitude_hash(self, anchor: Peak, target: Peak) -> str:
        """振幅ベースハッシュ"""
        amp_diff = target.amplitude - anchor.amplitude
        time_diff = target.time - anchor.time
        
        hash_input = f"amp:{amp_diff:.1f}:{time_diff:.3f}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

# 高度なハッシュ生成の使用
advanced_fingerprints = generate_robust_hashes(peaks, target_zone_size=8, freq_tolerance=75)

print(f"高度なハッシュ生成による指紋数: {len(advanced_fingerprints)}")
```

## 🗄️ FingerprintDatabase 詳細API

### 直接データベース操作

```python
from mimizam import FingerprintDatabase, DatabaseConfig, Song
from datetime import datetime

# データベース設定
config = DatabaseConfig(
    backend='sqlite',
    file_path='advanced_music.db'
)

# データベースインスタンスの作成
db = FingerprintDatabase(config)

# 手動接続管理
if db.connect():
    print("データベース接続成功")
    
    # テーブル作成
    if db.create_tables():
        print("テーブル作成成功")
    
    # 楽曲の手動追加
    song = Song(
        id="song_001",
        title="Test Song",
        artist="Test Artist",
        file_path="/path/to/song.wav",
        created_at=datetime.now(),
        meta={
            "genre": "Rock",
            "duration": 180.5,
            "bitrate": 320
        }
    )
    
    if db.add_song(song):
        print(f"楽曲追加成功: {song.title}")
    
    # 指紋の手動追加
    if db.add_fingerprints(song.id, advanced_fingerprints):
        print(f"指紋追加成功: {len(advanced_fingerprints)}個")
    
    # データベース統計
    stats = db.get_database_stats()
    print(f"データベース統計: {stats}")
    
    db.disconnect()
```

### カスタムマッチングアルゴリズム

```python
from collections import defaultdict
from typing import Dict, List, Tuple

def find_custom_matches(db: FingerprintDatabase, 
                       query_fingerprints: List[Fingerprint],
                       min_matches: int = 5, time_tolerance: float = 2.0) -> List[Dict]:
    """カスタムマッチング実行"""
    from mimizam import FingerprintMatcher
    import numpy as np
    
    # 実際のFingerprintMatcherを使用
    matcher = FingerprintMatcher()
    raw_matches = db.search_fingerprints(query_fingerprints)
    
    # 各楽曲の時間オフセット分析
    song_matches = {}
    for song_id, matches in raw_matches.items():
        time_diffs = [db_time - query_time for query_time, db_time in matches]
        
        # 時間差のクラスタリング
        clusters = cluster_time_differences(time_diffs, min_matches, time_tolerance)
        
        # 最大クラスターを選択
        if clusters:
            best_cluster = max(clusters, key=len)
            if len(best_cluster) >= min_matches:
                song_matches[song_id] = {
                    'matches': len(best_cluster),
                    'time_offset': np.median(best_cluster),
                    'confidence': calculate_match_confidence(best_cluster, matches)
                }
    
    # 結果をソート
    results = []
    for song_id, match_info in song_matches.items():
        song = db.get_song(song_id)
        if song:
            results.append({
                'song': song,
                'matches': match_info['matches'],
                'time_offset': match_info['time_offset'],
                'confidence': match_info['confidence']
            })
    
    return sorted(results, key=lambda x: x['confidence'], reverse=True)

def cluster_time_differences(time_diffs: List[float], min_matches: int, 
                           time_tolerance: float) -> List[List[float]]:
    """時間差のクラスタリング"""
    if not time_diffs:
        return []
    
    clusters = []
    sorted_diffs = sorted(time_diffs)
    
    current_cluster = [sorted_diffs[0]]
    
    for diff in sorted_diffs[1:]:
        if abs(diff - current_cluster[-1]) <= time_tolerance:
            current_cluster.append(diff)
        else:
            if len(current_cluster) >= min_matches:
                clusters.append(current_cluster)
            current_cluster = [diff]
    
    if len(current_cluster) >= min_matches:
        clusters.append(current_cluster)
    
    return clusters

def calculate_match_confidence(cluster: List[float], all_matches: List[Tuple]) -> float:
    """信頼度計算"""
    import numpy as np
    
    cluster_size = len(cluster)
    total_matches = len(all_matches)
    
    # クラスター内の一貫性
    consistency = 1.0 - (np.std(cluster) / (np.mean(cluster) + 1e-10))
    
    # マッチ率
    match_ratio = cluster_size / max(total_matches, 1)
    
    # 総合信頼度
    confidence = (consistency * 0.6 + match_ratio * 0.4) * min(cluster_size / 10, 1.0)
    
    return max(0.0, min(1.0, confidence))

# クエリ音声の処理
query_audio, _ = librosa.load("query.wav", sr=22050)
fingerprinter = AudioFingerprinter()
query_fingerprints = fingerprinter.fingerprint_audio(query_audio)

# カスタムマッチング実行
matches = find_custom_matches(db, query_fingerprints, min_matches=3, time_tolerance=1.5)

for match in matches:
    song = match['song']
    print(f"マッチ: {song.title} by {song.artist}")
    print(f"  - マッチ数: {match['matches']}")
    print(f"  - 時間オフセット: {match['time_offset']:.2f}秒")
    print(f"  - 信頼度: {match['confidence']:.3f}")
```

## 🔧 バックエンド直接操作

### SQLite バックエンドの詳細制御

```python
from mimizam.backends.sqlite_backend import SQLiteBackend

# SQLite バックエンドの直接使用
sqlite_config = DatabaseConfig(
    backend='sqlite',
    file_path='direct_access.db'
)

sqlite_backend = SQLiteBackend(sqlite_config)

if sqlite_backend.connect():
    # パフォーマンス設定の確認
    cursor = sqlite_backend.connection.cursor()
    
    # PRAGMA設定の確認
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    print(f"Journal mode: {journal_mode}")
    
    cursor.execute("PRAGMA cache_size")
    cache_size = cursor.fetchone()[0]
    print(f"Cache size: {cache_size}")
    
    # インデックス情報の取得
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = cursor.fetchall()
    print(f"インデックス: {[idx[0] for idx in indexes]}")
    
    # クエリプランの分析
    cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM fingerprints WHERE hash_value = ?", ("test_hash",))
    query_plan = cursor.fetchall()
    print(f"クエリプラン: {query_plan}")
    
    sqlite_backend.disconnect()
```

### MySQL バックエンドの詳細制御

```python
from mimizam.backends.mysql_backend import MySQLBackend

# MySQL バックエンドの直接使用
mysql_config = DatabaseConfig(
    backend='mysql',
    host='localhost',
    port=3306,
    database='mimizam_advanced',
    username='user',
    password='password'
)

mysql_backend = MySQLBackend(mysql_config)

if mysql_backend.connect():
    cursor = mysql_backend.connection.cursor()
    
    # MySQL設定の確認
    cursor.execute("SHOW VARIABLES LIKE 'innodb_buffer_pool_size'")
    buffer_pool = cursor.fetchone()
    print(f"InnoDB Buffer Pool: {buffer_pool}")
    
    # インデックス使用状況の確認
    cursor.execute("SHOW INDEX FROM fingerprints")
    indexes = cursor.fetchall()
    for idx in indexes:
        print(f"インデックス: {idx[2]} on {idx[4]}")
    
    # クエリ最適化の確認
    cursor.execute("EXPLAIN SELECT * FROM fingerprints WHERE hash_value = %s", ("test_hash",))
    explain = cursor.fetchall()
    print(f"実行計画: {explain}")
    
    mysql_backend.disconnect()
```

## 🎛️ 高度な設定とチューニング

### パフォーマンス監視

```python
from mimizam.adaptive_parameters import PerformanceMonitor
import time

# パフォーマンス監視器の設定
monitor = PerformanceMonitor()

# 処理時間の測定
start_time = time.time()

# 音声処理
audio, sr = librosa.load("test_audio.wav", sr=22050)
fingerprints = fingerprinter.fingerprint_audio(audio)

processing_time = time.time() - start_time
monitor.record_processing_time("fingerprint_generation", processing_time)
monitor.record_fingerprint_count(len(fingerprints))

# パフォーマンスサマリーの表示
print(monitor.get_performance_summary())
```

### メモリ使用量の最適化

```python
import gc
import psutil
import os

def get_memory_usage():
    """現在のメモリ使用量を取得"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    return {
        'rss': memory_info.rss / 1024 / 1024,  # MB
        'vms': memory_info.vms / 1024 / 1024,  # MB
        'percent': process.memory_percent()
    }

def optimize_memory():
    """メモリ最適化実行"""
    # ガベージコレクション実行
    collected = gc.collect()
    print(f"ガベージコレクション: {collected}個のオブジェクトを回収")
    
    # メモリ使用量の表示
    memory = get_memory_usage()
    print(f"メモリ使用量: RSS={memory['rss']:.1f}MB, VMS={memory['vms']:.1f}MB, {memory['percent']:.1f}%")

# メモリ最適化の使用例
print("処理前:")
optimize_memory()

# 大量データ処理
for i in range(10):
    audio, sr = librosa.load(f"audio_{i}.wav", sr=22050)
    fingerprints = fingerprinter.fingerprint_audio(audio)
    
    # 定期的なメモリ最適化
    if i % 3 == 0:
        optimize_memory()

print("処理後:")
optimize_memory()
```

## 🔗 関連ドキュメント

- [統合API](./07_unified_api.md) - 高レベルAPI使用方法
- [データ構造](./09_data_structures.md) - データ構造詳細
- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上技術
- [適応パラメータ調整](./15_adaptive_parameters.md) - パラメータ最適化
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決

## 💡 使用上の注意

### 1. リソース管理
- 低レベルAPIを使用する際は、適切なリソース管理が重要
- データベース接続の明示的な切断
- メモリ使用量の監視

### 2. エラーハンドリング
- 各操作での例外処理の実装
- ログ出力による問題の追跡
- 適切なフォールバック処理

### 3. パフォーマンス考慮
- 大量データ処理時のバッチ処理
- メモリ効率的なアルゴリズムの選択
- 並列処理の活用

低レベルAPIを使用することで、mimizamシステムの全機能を最大限に活用し、特定の要件に合わせたカスタマイズが可能になります。
