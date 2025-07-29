# 17. 高度な使用例

mimizamの高度な機能を活用した実践的な使用例を紹介します。

## 🎛️ 適応的パラメータ調整

### AdaptiveParameterTunerを使用した音声特性に応じた最適化

```python
from mimizam import AudioFingerprinter, AdaptiveParameterTuner
import numpy as np
import librosa

# 適応的パラメータ調整を有効にしたFingerprinter
fingerprinter = AudioFingerprinter(
    n_fft=2048,
    hop_length=512,
    sr=22050,
    enable_adaptive_params=True  # 適応的パラメータ調整を有効化
)

# 音声ファイルを読み込み
audio, sr = librosa.load("test_audio.wav", sr=22050)

# フィンガープリント生成（自動的にパラメータが調整される）
fingerprints = fingerprinter.fingerprint_audio(audio, debug=True)

print(f"生成されたフィンガープリント数: {len(fingerprints)}")

### 手動でのパラメータ調整

```python
from mimizam import AdaptiveParameterTuner

# パラメータチューナーを作成
tuner = AdaptiveParameterTuner()

# 音声特性を分析
characteristics = tuner.analyze_audio_characteristics(audio, sr=22050)

# パラメータを調整
adjusted_params = tuner.adjust_parameters(characteristics)

# 調整結果を表示
summary = tuner.get_parameter_summary(characteristics, adjusted_params)
print("パラメータ調整結果:")
print(summary)

# 調整されたパラメータでFingerprinterを作成
fingerprinter = AudioFingerprinter(
    n_fft=2048,
    hop_length=512,
    sr=22050,
    min_amplitude=adjusted_params['min_amplitude'],
    peak_neighborhood_size=adjusted_params['peak_neighborhood_size'],
    enable_adaptive_params=False  # 手動設定を使用
)
    """カスタムパラメータ最適化器"""
    
    def __init__(self):
        self.parameter_sets = {
            'speech_optimized': {
                'n_fft': 1024,          # 音声に適した小さなFFTサイズ
                'hop_length': 256,      # 高い時間解像度
                'min_amplitude': -50,   # 音声レベルに合わせた閾値
                'peak_neighborhood_size': 10
            },
            'music_optimized': {
                'n_fft': 2048,          # 音楽に適した標準FFTサイズ
                'hop_length': 512,      # バランスの取れた解像度
                'min_amplitude': -60,   # 音楽の動的レンジに対応
                'peak_neighborhood_size': 20
            },
            'high_quality': {
                'n_fft': 4096,          # 高品質分析用
                'hop_length': 256,      # 高い時間解像度
                'min_amplitude': -70,   # 低レベル音声も検出
                'peak_neighborhood_size': 30
            },
            'fast_processing': {
                'n_fft': 1024,          # 高速処理用
                'hop_length': 1024,     # 大きなホップ長
                'min_amplitude': -40,   # 高い閾値
                'peak_neighborhood_size': 5
            }
        }
    
    def analyze_audio_characteristics(self, audio: np.ndarray) -> Dict[str, float]:
        """音声特性分析"""
        
        # 基本統計
        rms = np.sqrt(np.mean(audio**2))
        peak_amplitude = np.max(np.abs(audio))
        dynamic_range = 20 * np.log10(peak_amplitude / (rms + 1e-10))
        
        # スペクトル特性
        S = librosa.stft(audio, n_fft=2048, hop_length=512)
        magnitude = np.abs(S)
        
        # スペクトル重心
        spectral_centroids = librosa.feature.spectral_centroid(S=magnitude)[0]
        avg_spectral_centroid = np.mean(spectral_centroids)
        
        # スペクトル帯域幅
        spectral_bandwidth = librosa.feature.spectral_bandwidth(S=magnitude)[0]
        avg_spectral_bandwidth = np.mean(spectral_bandwidth)
        
        # ゼロ交差率
        zcr = librosa.feature.zero_crossing_rate(audio)[0]
        avg_zcr = np.mean(zcr)
        
        return {
            'rms': rms,
            'peak_amplitude': peak_amplitude,
            'dynamic_range': dynamic_range,
            'spectral_centroid': avg_spectral_centroid,
            'spectral_bandwidth': avg_spectral_bandwidth,
            'zero_crossing_rate': avg_zcr
        }
    
    def recommend_parameters(self, audio: np.ndarray) -> Dict[str, Any]:
        """音声特性に基づくパラメータ推奨"""
        
        characteristics = self.analyze_audio_characteristics(audio)
        
        # 推奨ロジック
        if characteristics['zero_crossing_rate'] > 0.1:
            # 音声らしい特徴
            recommended_set = 'speech_optimized'
        elif characteristics['spectral_centroid'] > 3000:
            # 高周波成分が多い（楽器音楽など）
            recommended_set = 'music_optimized'
        elif characteristics['dynamic_range'] > 20:
            # 動的レンジが広い
            recommended_set = 'high_quality'
        else:
            # 一般的な音声
            recommended_set = 'music_optimized'
        
        recommended_params = self.parameter_sets[recommended_set].copy()
        
        # 動的調整
        if characteristics['rms'] < 0.01:  # 低レベル音声
            recommended_params['min_amplitude'] -= 10
        
        if characteristics['peak_amplitude'] > 0.9:  # 高レベル音声
            recommended_params['min_amplitude'] += 5
        
        return {
            'recommended_set': recommended_set,
            'parameters': recommended_params,
            'characteristics': characteristics,
            'reasoning': self._generate_reasoning(characteristics, recommended_set)
        }
    
    def _generate_reasoning(self, characteristics: Dict[str, float], recommended_set: str) -> str:
        """推奨理由の生成"""
        
        reasons = []
        
        if characteristics['zero_crossing_rate'] > 0.1:
            reasons.append("高いゼロ交差率により音声と判定")
        
        if characteristics['spectral_centroid'] > 3000:
            reasons.append("高い周波数重心により楽器音楽と判定")
        
        if characteristics['dynamic_range'] > 20:
            reasons.append("広い動的レンジにより高品質設定を推奨")
        
        if characteristics['rms'] < 0.01:
            reasons.append("低RMSレベルにより感度を上げる設定を適用")
        
        return f"{recommended_set}を推奨: " + ", ".join(reasons)

# 使用例
optimizer = CustomParameterOptimizer()

# テスト音声読み込み
audio, sr = librosa.load("test_audio.wav", sr=22050)

# パラメータ推奨
recommendation = optimizer.recommend_parameters(audio)

print(f"推奨設定: {recommendation['recommended_set']}")
print(f"理由: {recommendation['reasoning']}")
print(f"パラメータ: {recommendation['parameters']}")

# 推奨パラメータでAudioFingerprinter作成
fingerprinter = AudioFingerprinter(**recommendation['parameters'])
fingerprints = fingerprinter.fingerprint_audio(audio)

print(f"生成された指紋数: {len(fingerprints)}")
```

## 🔄 複数バックエンドの統合活用

### ハイブリッドデータベース戦略

```python
from mimizam import create_mimizam_sqlite, create_mimizam_mysql, create_mimizam_elasticsearch
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import List, Dict, Any

def compare_multiple_backends(file_path: str, title: str, artist: str):
    """複数バックエンドでの楽曲追加と検索性能比較"""
    
    # SQLiteバックエンド
    sqlite_mimizam = create_mimizam_sqlite("cache.db")
    
    # MySQLバックエンド（利用可能な場合）
    try:
        mysql_mimizam = create_mimizam_mysql(
            host="localhost",
            database="music_main", 
            username="user",
            password="password"
        )
        mysql_available = True
    except:
        mysql_available = False
        print("MySQL接続失敗 - SQLiteのみ使用")
    
    results = {}
    
    # SQLiteに楽曲追加
    start_time = time.time()
    sqlite_id = sqlite_mimizam.add_song(file_path, title, artist)
    sqlite_add_time = time.time() - start_time
    results['sqlite'] = {
        'song_id': sqlite_id,
        'add_time': sqlite_add_time
    }
    
    # MySQLに楽曲追加（利用可能な場合）
    if mysql_available:
        start_time = time.time()
        mysql_id = mysql_mimizam.add_song(file_path, title, artist)
        mysql_add_time = time.time() - start_time
        results['mysql'] = {
            'song_id': mysql_id,
            'add_time': mysql_add_time
        }
    
    # 検索性能比較
    query_file = file_path  # 同じファイルで検索テスト
    
    # SQLiteで検索
    start_time = time.time()
    sqlite_results = sqlite_mimizam.search_song(query_file)
    sqlite_search_time = time.time() - start_time
    results['sqlite']['search_time'] = sqlite_search_time
    results['sqlite']['search_results'] = len(sqlite_results)
    
    # MySQLで検索（利用可能な場合）
    if mysql_available:
        start_time = time.time()
        mysql_results = mysql_mimizam.search_song(query_file)
        mysql_search_time = time.time() - start_time
        results['mysql']['search_time'] = mysql_search_time
        results['mysql']['search_results'] = len(mysql_results)
        mysql_mimizam.close()
    
    sqlite_mimizam.close()
    return results

# 使用例
results = compare_multiple_backends(
    "new_song.wav",
    "New Song", 
    "Artist Name"
)

print("バックエンド性能比較結果:")
for backend, data in results.items():
    print(f"{backend.upper()}:")
    print(f"  楽曲ID: {data['song_id']}")
    print(f"  追加時間: {data['add_time']:.3f}秒")
    print(f"  検索時間: {data['search_time']:.3f}秒")
    print(f"  検索結果数: {data['search_results']}件")
```

## 🚀 高性能バッチ処理

### 大規模データセット処理

```python
import os
import glob
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing
import time
import logging
from pathlib import Path

def process_music_directory_batch(directory_path: str, file_patterns=None, batch_size=50):
    """音楽ディレクトリのバッチ処理"""
    
    if file_patterns is None:
        file_patterns = ['*.wav', '*.mp3', '*.flac', '*.m4a']
    
    # ファイル一覧取得
    all_files = []
    for pattern in file_patterns:
        all_files.extend(glob.glob(os.path.join(directory_path, '**', pattern), recursive=True))
    
    print(f"処理対象ファイル数: {len(all_files)}")
    
    # mimizamインスタンス作成
    mimizam = create_mimizam_sqlite("batch_music.db")
    
    results = {
        'total_files': len(all_files),
        'processed_files': 0,
        'failed_files': 0,
        'processing_time': 0,
        'errors': []
    }
    
    start_time = time.time()
    
    # バッチ処理
    for i in range(0, len(all_files), batch_size):
        batch = all_files[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(all_files) + batch_size - 1) // batch_size
        
        print(f"バッチ {batch_num}/{total_batches} 処理中...")
        
        for file_path in batch:
            try:
                # ファイル名から楽曲情報を推測
                title = os.path.splitext(os.path.basename(file_path))[0]
                artist = os.path.basename(os.path.dirname(file_path))
                
                # 楽曲を追加
                song_id = mimizam.add_song(file_path, title, artist)
                results['processed_files'] += 1
                
            except Exception as e:
                results['failed_files'] += 1
                results['errors'].append(f"{file_path}: {str(e)}")
                print(f"処理エラー {file_path}: {e}")
        
        print(f"バッチ {batch_num} 完了: 成功 {len(batch) - len([e for e in results['errors'] if e.startswith(batch[0])])}, "
              f"失敗 {len([e for e in results['errors'] if any(f in e for f in batch)])}")
    
    results['processing_time'] = time.time() - start_time
    
    print(f"全体処理完了: {results['processed_files']}/{results['total_files']} "
          f"({results['processing_time']:.2f}秒)")
    
    mimizam.close()
    return results

# 使用例
results = process_music_directory_batch(
    "/path/to/music/library",
    file_patterns=['*.wav', '*.mp3', '*.flac'],
    batch_size=50
)

print(f"処理結果: {results['processed_files']}/{results['total_files']} "
      f"({results['processing_time']:.2f}秒)")

# エラーがあった場合の詳細表示
if results['errors']:
    print(f"\nエラー詳細 ({len(results['errors'])}件):")
    for error in results['errors'][:5]:  # 最初の5件のみ表示
        print(f"  {error}")
```

## 🔗 関連ドキュメント

- [基本的な使用例](./16_basic_examples.md) - 基本操作
- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上
- [バックエンド比較](./11_backend_comparison.md) - データベース選択
- [適応的パラメータ](./15_adaptive_parameters.md) - 自動調整
- [動画処理](./18_video_processing.md) - 動画音声処理

## 💡 高度な使用例のベストプラクティス

### 1. パラメータ最適化
- 音声特性の事前分析
- 用途に応じた設定選択
- 継続的な性能監視

### 2. システム統合
- 適切なアーキテクチャ設計
- 障害対応の実装
- スケーラビリティの考慮

### 3. パフォーマンス管理
- リソース使用量の監視
- ボトルネックの特定
- 最適化の継続的実施

mimizamの高度な機能を活用して、実用的で高性能な音声識別システムを構築してください。
