#!/usr/bin/env python3
"""
Test script to verify performance optimization works
"""
import time
import sys
import os
sys.path.insert(0, '/home/ubuntu/mimizam')

from src.audio_fingerprinter import AudioFingerprinter

def test_performance():
    print("Testing performance optimization...")
    
    test_file = "/home/ubuntu/mimizam/test_media/demo_song1.wav"
    if not os.path.exists(test_file):
        print(f"Test file not found: {test_file}")
        return
    
    print("\n=== Testing with Numba optimization (should be faster) ===")
    fingerprinter_numba = AudioFingerprinter(enable_numba_optimization=True)
    
    start_time = time.time()
    audio = fingerprinter_numba.load_audio(test_file)
    fingerprints_numba = fingerprinter_numba.fingerprint_audio(audio, debug=True)
    numba_time = time.time() - start_time
    
    print(f"Numba optimization: {len(fingerprints_numba)} fingerprints in {numba_time:.3f}s")
    
    print("\n=== Testing with peak_local_max fallback ===")
    fingerprinter_fallback = AudioFingerprinter(enable_numba_optimization=False)
    
    start_time = time.time()
    audio = fingerprinter_fallback.load_audio(test_file)
    fingerprints_fallback = fingerprinter_fallback.fingerprint_audio(audio, debug=True)
    fallback_time = time.time() - start_time
    
    print(f"peak_local_max fallback: {len(fingerprints_fallback)} fingerprints in {fallback_time:.3f}s")
    
    print(f"\n=== Performance Comparison ===")
    print(f"Numba: {numba_time:.3f}s ({len(fingerprints_numba)} fingerprints)")
    print(f"Fallback: {fallback_time:.3f}s ({len(fingerprints_fallback)} fingerprints)")
    
    if numba_time < fallback_time:
        speedup = fallback_time / numba_time
        print(f"✅ Numba is {speedup:.1f}x faster")
    else:
        slowdown = numba_time / fallback_time
        print(f"⚠️ Numba is {slowdown:.1f}x slower")
    
    print("✅ Performance optimization test completed successfully!")

if __name__ == "__main__":
    test_performance()
