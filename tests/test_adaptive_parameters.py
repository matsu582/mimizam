import unittest
import numpy as np

from src.adaptive_parameters import AdaptiveParameterTuner, PerformanceMonitor

class TestAdaptiveParameterTuner(unittest.TestCase):
    def setUp(self):
        self.tuner = AdaptiveParameterTuner()
        # Simple audio: sine wave + silence
        sr = 1000
        t = np.linspace(0, 1, sr, endpoint=False)
        sine = 0.5 * np.sin(2 * np.pi * 5 * t)
        silence = np.zeros(sr)
        self.audio = np.concatenate([sine, silence])
        self.sr = sr

    def test_analyze_audio_characteristics(self):
        characteristics = self.tuner.analyze_audio_characteristics(self.audio, self.sr)
        # Check that key features are present and reasonable
        self.assertIn('duration', characteristics)
        self.assertAlmostEqual(characteristics['duration'], 2.0, places=2)
        self.assertIn('rms', characteristics)
        self.assertIn('silence_ratio', characteristics)
        self.assertGreaterEqual(characteristics['silence_ratio'], 0.49)

    def test_adjust_parameters_silence(self):
        # Force high silence_ratio
        char = {'silence_ratio': 0.6, 'spectral_entropy': 5, 'rms': 0.02,
                'peak_amplitude': 1, 'tempo': 100, 'duration': 50,
                'spectral_centroid_mean': 2000}
        params = self.tuner.adjust_parameters(char)
        # Silence adjustment should lower min_amplitude and max_peaks_per_second
        self.assertEqual(params['min_amplitude'], -70)
        self.assertEqual(params['max_peaks_per_second'], 10)

    def test_get_parameter_summary(self):
        char = {'duration': 5.0, 'rms': 0.05, 'silence_ratio': 0.1,
                'spectral_entropy': 6.0, 'tempo': 120, 'spectral_centroid_mean': 1500}
        adjusted = {'min_amplitude': -60, 'peak_neighborhood_size': 10,
                    'target_zone_size': 5, 'max_peaks_per_second': 15,
                    'min_peak_separation': 0.02}
        summary = self.tuner.get_parameter_summary(char, adjusted)
        self.assertIn('Duration: 5.00s', summary)
        self.assertIn('Min amplitude: -60', summary)
        self.assertIn('Max peaks/second: 15', summary)

class TestPerformanceMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = PerformanceMonitor()

    def test_record_and_summary(self):
        self.monitor.record_processing_time('op1', 0.1)
        self.monitor.record_processing_time('op1', 0.2)
        self.monitor.record_fingerprint_count(10)
        self.monitor.record_fingerprint_count(20)
        self.monitor.record_peak_count(5)
        summary = self.monitor.get_performance_summary()
        self.assertIn('Average processing time', summary)
        self.assertIn('op1', summary)
        self.assertIn('Average fingerprint count', summary)
        self.assertIn('Average peak count', summary)

    def test_reset_metrics(self):
        self.monitor.record_processing_time('op2', 0.1)
        self.monitor.reset_metrics()
        summary = self.monitor.get_performance_summary()
        # After reset, summary should have minimal content
        self.assertNotIn('op2', summary)

if __name__ == '__main__':
    unittest.main()
