#!/usr/bin/env python3
"""
残り2.6秒の性能劣化（現在7.6秒 vs 目標5秒）を引き起こす
ボトルネックを特定するための包括的性能プロファイリング
"""
import time
import sys
import os
import numpy as np
import cProfile
import pstats
import io
sys.path.insert(0, '/home/ubuntu/mimizam')

from src.audio_fingerprinter import AudioFingerprinter

def profile_pipeline_components():
    print("=== パイプライン個別コンポーネントのプロファイリング ===")
    
    test_file = "/home/ubuntu/mimizam/test_media/demo_song1.wav"
    if not os.path.exists(test_file):
        print(f"テストファイルが見つかりません: {test_file}")
        return
    
    fingerprinter = AudioFingerprinter(
        enable_adaptive_params=False, 
        enable_numba_optimization=False
    )
    audio = fingerprinter.load_audio(test_file)
    extended_audio = np.tile(audio, 50)  # より正確な測定のため50倍に拡張
    
    start_time = time.time()
    magnitude, frequencies, times = fingerprinter.spectrogram_analyzer.generate_spectrogram(
        extended_audio, audible_only=fingerprinter.audible_only
    )
    spectrogram_time = time.time() - start_time
    
    start_time = time.time()
    peaks = fingerprinter.spectrogram_analyzer.detect_peaks(
        magnitude, frequencies, times,
        fingerprinter.min_amplitude, fingerprinter.peak_neighborhood_size, False
    )
    peak_detection_time = time.time() - start_time
    
    start_time = time.time()
    fingerprints = fingerprinter.hash_generator.generate_hashes(peaks, False)
    hash_generation_time = time.time() - start_time
    
    total_time = spectrogram_time + peak_detection_time + hash_generation_time
    audio_duration = len(extended_audio) / fingerprinter.spectrogram_analyzer.sr
    
    print(f"\n📊 パイプラインコンポーネント分析:")
    print(f"音声時間: {audio_duration:.2f}秒")
    print(f"スペクトログラム生成: {spectrogram_time:.3f}秒 ({spectrogram_time/total_time*100:.1f}%)")
    print(f"ピーク検出: {peak_detection_time:.3f}秒 ({peak_detection_time/total_time*100:.1f}%)")
    print(f"ハッシュ生成: {hash_generation_time:.3f}秒 ({hash_generation_time/total_time*100:.1f}%)")
    print(f"パイプライン合計時間: {total_time:.3f}秒")
    
    estimated_24min = (total_time / audio_duration) * (24 * 60)
    print(f"24分動画推定時間: {estimated_24min:.1f}秒")
    
    return {
        'spectrogram': spectrogram_time,
        'peak_detection': peak_detection_time,
        'hash_generation': hash_generation_time,
        'total': total_time,
        'estimated_24min': estimated_24min
    }

def test_dev_branch_settings():
    print(f"\n=== devブランチ設定のテスト ===")
    
    test_file = "/home/ubuntu/mimizam/test_media/demo_song1.wav"
    fingerprinter_dev = AudioFingerprinter(
        enable_adaptive_params=True, 
        enable_numba_optimization=True
    )
    audio = fingerprinter_dev.load_audio(test_file)
    extended_audio = np.tile(audio, 50)
    
    start_time = time.time()
    fingerprints_dev = fingerprinter_dev.fingerprint_audio(extended_audio, debug=False)
    dev_time = time.time() - start_time
    
    audio_duration = len(extended_audio) / fingerprinter_dev.spectrogram_analyzer.sr
    estimated_24min_dev = (dev_time / audio_duration) * (24 * 60)
    
    print(f"dev設定 (adaptive=True, numba=True): {estimated_24min_dev:.1f}秒")
    return estimated_24min_dev

def compare_peak_detection_methods():
    print(f"\n=== ピーク検出手法の比較 ===")
    
    test_file = "/home/ubuntu/mimizam/test_media/demo_song1.wav"
    fingerprinter = AudioFingerprinter(enable_adaptive_params=False)
    audio = fingerprinter.load_audio(test_file)
    extended_audio = np.tile(audio, 20)  # このテスト用に小さめに
    
    magnitude, frequencies, times = fingerprinter.spectrogram_analyzer.generate_spectrogram(
        extended_audio, audible_only=fingerprinter.audible_only
    )
    
    fingerprinter.spectrogram_analyzer.enable_numba_optimization = False
    start_time = time.time()
    peaks_no_numba = fingerprinter.spectrogram_analyzer.detect_peaks(
        magnitude, frequencies, times, fingerprinter.min_amplitude, 
        fingerprinter.peak_neighborhood_size, False
    )
    no_numba_time = time.time() - start_time
    
    fingerprinter.spectrogram_analyzer.enable_numba_optimization = True
    start_time = time.time()
    peaks_numba = fingerprinter.spectrogram_analyzer.detect_peaks(
        magnitude, frequencies, times, fingerprinter.min_amplitude, 
        fingerprinter.peak_neighborhood_size, False
    )
    numba_time = time.time() - start_time
    
    print(f"Numba無効のピーク検出: {no_numba_time:.3f}秒 ({len(peaks_no_numba)} ピーク)")
    print(f"Numba有効のピーク検出: {numba_time:.3f}秒 ({len(peaks_numba)} ピーク)")
    
    if numba_time > 0:
        speedup = no_numba_time / numba_time
        print(f"Numba高速化: {speedup:.1f}倍")
    
    return no_numba_time, numba_time

if __name__ == "__main__":
    current_results = profile_pipeline_components()
    dev_results = test_dev_branch_settings()
    compare_peak_detection_methods()
    
    print(f"\n🎯 性能分析サマリー:")
    print(f"現在の設定: {current_results['estimated_24min']:.1f}秒")
    print(f"dev設定: {dev_results:.1f}秒")
    print(f"目標: 5.0秒")
    
    if dev_results < current_results['estimated_24min']:
        improvement = current_results['estimated_24min'] - dev_results
        print(f"💡 dev設定が{improvement:.1f}秒高速 - dev設定を有効化")
    else:
        print(f"💡 設定以外の最適化を調査する必要あり")
