#!/usr/bin/env python3
"""AudioFingerprinter パラメータ比較テスト

異なるパラメータ設定でのAudioFingerprinterの性能を比較します：
- デフォルト設定（適応パラメータ有効）
- 保守的設定（適応パラメータ無効）  
- 並列処理有効設定
"""

import sys
import time
import logging
import tracemalloc
from pathlib import Path

# プロジェクトルートをPATHに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def measure_fingerprinter_performance(fingerprinter, audio_path, method_name):
    """フィンガープリンター性能測定"""
    logger.info(f"🚀 {method_name} 測定開始...")
    
    tracemalloc.start()
    start_time = time.time()
    
    try:
        fingerprints = fingerprinter.fingerprint_file(audio_path)
        
        processing_time = time.time() - start_time
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_mb = peak_memory / 1024 / 1024
        
        return {
            'method': method_name,
            'fingerprints': len(fingerprints),
            'time': processing_time,
            'memory_mb': memory_mb,
            'fps_per_sec': len(fingerprints) / processing_time if processing_time > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"❌ {method_name} エラー: {e}")
        tracemalloc.stop()
        return None

def compare_audio_fingerprinters(audio_path):
    """AudioFingerprinter速度比較"""
    logger.info(f"🎵 AudioFingerprinter速度比較: {Path(audio_path).name}")
    
    results = []
    
    # 標準AudioFingerprinter（デフォルト設定）
    try:
        from src.audio_fingerprinter import AudioFingerprinter
        
        # デフォルト設定（最適化済み）
        default_fp = AudioFingerprinter()
        result = measure_fingerprinter_performance(
            default_fp, audio_path, "AudioFingerprinter（デフォルト）"
        )
        if result:
            results.append(result)
            
    except Exception as e:
        logger.error(f"AudioFingerprinter（デフォルト）初期化エラー: {e}")
    
    # 標準AudioFingerprinter（適応パラメータ無効）
    try:
        from src.audio_fingerprinter import AudioFingerprinter
        
        conservative_fp = AudioFingerprinter(
            enable_adaptive_params=False
        )
        result = measure_fingerprinter_performance(
            conservative_fp, audio_path, "AudioFingerprinter（保守的）"
        )
        if result:
            results.append(result)
            
    except Exception as e:
        logger.error(f"AudioFingerprinter（保守的）初期化エラー: {e}")
    
    
    # 結果表示
    display_comparison_results(results, audio_path)

def display_comparison_results(results, audio_path):
    """比較結果表示"""
    if not results:
        print("❌ 比較テストに失敗しました")
        return
    
    print("\n" + "="*80)
    print("🚀 AudioFingerprinter 速度比較結果")
    print("============================================================")
    print(f"📁 テストファイル: {Path(audio_path).name}")
    print("------------------------------------------------------------")

    # ヘッダー
    print(f"{'実装':<30} {'時間(秒)':<10} {'高速化率':<10} {'FP数':<10} {'FP/秒':<10}")
    print("------------------------------------------------------------")

    # 基準となる保守的実装
    conservative_result = None
    for result in results:
        if "保守的" in result['method']:
            conservative_result = result
            break
    
    # 結果表示
    for result in results:
        speedup = "1.00x"
        if conservative_result and result != conservative_result:
            speedup = f"{conservative_result['time'] / result['time']:.2f}x"
        
        print(f"{result['method']:<30} "
              f"{result['time']:<10.3f} "
              f"{speedup:<10} "
              f"{result['fingerprints']:<10} "
              f"{result['fps_per_sec']:<10.0f}")

    print("============================================================")

    # 分析
    if conservative_result:
        default_result = None
        for result in results:
            if "デフォルト" in result['method']:
                default_result = result
                break
        
        if default_result:
            speedup = conservative_result['time'] / default_result['time']
            accuracy = default_result['fingerprints'] / conservative_result['fingerprints']
            
            print("📊 パフォーマンス分析:")
            print(f"  ⚡ 適応パラメータによる高速化: {speedup:.1f}倍")
            print(f"  🎯 フィンガープリント比率: {accuracy:.1%}")
            
            if speedup > 2.0:
                print(f"  🎉 {speedup:.0f}倍の大幅な高速化を達成！")
            elif speedup > 1.2:
                print(f"  ✅ {speedup:.1f}倍の高速化を実現")
            else:
                print("  ⚠️ 高速化効果が限定的です")

def main():
    """メイン関数"""
    if len(sys.argv) < 2:
        print("使用方法: python compare_audio_fingerprinters.py <音声ファイル>")
        return
    
    audio_path = sys.argv[1]
    
    if not Path(audio_path).exists():
        logger.error(f"❌ ファイルが見つかりません: {audio_path}")
        return
    
    compare_audio_fingerprinters(audio_path)

if __name__ == "__main__":
    main()
