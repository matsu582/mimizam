#!/usr/bin/env python3
"""
Test Numba optimization performance to verify it solves the regression
"""
import time
import sys
import os
import numpy as np
sys.path.insert(0, '/home/ubuntu/mimizam')

from src.audio_fingerprinter import AudioFingerprinter

def test_numba_performance():
    print("Testing Numba optimization performance...")
    
    test_file = "/home/ubuntu/mimizam/test_media/demo_song1.wav"
    if not os.path.exists(test_file):
        print(f"Test file not found: {test_file}")
        return
    
    fingerprinter = AudioFingerprinter(enable_numba_optimization=True)  # Enable Numba
    audio = fingerprinter.load_audio(test_file)
    
    extended_audio = np.tile(audio, 20)  # 20x longer for better simulation
    print(f"Extended audio length: {len(extended_audio)} samples ({len(extended_audio)/fingerprinter.sr:.2f}s)")
    
    print("\n=== Testing with Numba optimization enabled ===")
    start_time = time.time()
    fingerprints = fingerprinter.fingerprint_audio(extended_audio, debug=True)
    processing_time = time.time() - start_time
    
    print(f"✅ Numba optimization: {len(fingerprints)} fingerprints in {processing_time:.3f}s")
    
    audio_duration = len(extended_audio) / fingerprinter.sr
    time_per_second = processing_time / audio_duration
    estimated_24min_time = time_per_second * (24 * 60)  # 24 minutes
    
    print(f"📊 Performance metrics:")
    print(f"   - Processing rate: {time_per_second:.4f}s per second of audio")
    print(f"   - Estimated 24-minute video time: {estimated_24min_time:.1f}s")
    
    if estimated_24min_time <= 6.0:  # Target is 5s, allow small margin
        print(f"✅ SUCCESS: Estimated time ({estimated_24min_time:.1f}s) meets target (~5s)")
        return True
    else:
        print(f"⚠️ WARNING: Estimated time ({estimated_24min_time:.1f}s) exceeds target (~5s)")
        return False

if __name__ == "__main__":
    success = test_numba_performance()
    if success:
        print("\n🎉 Performance optimization successful! Ready to commit changes.")
    else:
        print("\n❌ Performance optimization needs more work.")
