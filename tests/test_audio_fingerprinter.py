import unittest
import numpy as np
from src.audio_fingerprinter import SpectrogramAnalyzer, Peak

class TestSpectrogramAnalyzer(unittest.TestCase):
    def setUp(self):
        sr = 1000
        t = np.linspace(0, 1, sr, endpoint=False)
        # Generate a simple sine wave signal
        self.audio = 0.5 * np.sin(2 * np.pi * 5 * t)
        self.sr = sr
        self.analyzer = SpectrogramAnalyzer(n_fft=256, hop_length=128, sr=sr)
        magnitude, freqs, times = self.analyzer.generate_spectrogram(self.audio, audible_only=False)
        self.magnitude = magnitude
        self.freqs = freqs
        self.times = times

    def test_generate_spectrogram_shape(self):
        self.assertEqual(self.magnitude.ndim, 2)
        self.assertEqual(self.freqs.ndim, 1)
        self.assertEqual(self.times.ndim, 1)
        # Check that time axis length matches spectrogram frames
        self.assertEqual(self.magnitude.shape[1], len(self.times))

    def test_detect_peaks_defaults(self):
        peaks = self.analyzer.detect_peaks(self.magnitude, self.freqs, self.times)
        # Should return a list of Peak objects
        self.assertIsInstance(peaks, list)
        for p in peaks:
            self.assertIsInstance(p, Peak)
            self.assertGreaterEqual(p.amplitude, -100)

    def test_detect_peaks_with_debug(self):
        # Ensure debug flag doesn't break detection
        peaks = self.analyzer.detect_peaks(
            self.magnitude, self.freqs, self.times,
            min_amplitude=-80, peak_neighborhood_size=5, debug=True)
        self.assertIsInstance(peaks, list)

if __name__ == '__main__':
    unittest.main()
