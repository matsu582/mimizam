import unittest

from mimizam import PerformanceMonitor

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
