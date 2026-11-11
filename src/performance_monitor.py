"""フィンガープリンティングの処理時間・件数を記録するモジュール"""

import logging

import numpy as np


class PerformanceMonitor:
    """フィンガープリンティングのパフォーマンスを監視するクラス"""
    
    def __init__(self):
        """パフォーマンス監視器を初期化"""
        self.logger = logging.getLogger(__name__)
        self.metrics = {}
        self.processing_times = []
        self.fingerprint_counts = []
        self.peak_counts = []
    
    def record_processing_time(self, operation: str, time_seconds: float):
        """処理時間を記録"""
        if operation not in self.metrics:
            self.metrics[operation] = []
        self.metrics[operation].append(time_seconds)
        self.processing_times.append(time_seconds)
    
    def record_fingerprint_count(self, count: int):
        """生成されたフィンガープリント数を記録"""
        self.fingerprint_counts.append(count)
    
    def record_peak_count(self, count: int):
        """検出されたピーク数を記録"""
        self.peak_counts.append(count)
    
    def get_performance_summary(self) -> str:
        """パフォーマンスサマリーを取得"""
        summary = "Performance Monitoring Results:\n"
        
        if self.processing_times:
            summary += f"- Average processing time: {np.mean(self.processing_times):.3f}s\n"
            summary += f"- Max processing time: {np.max(self.processing_times):.3f}s\n"
        
        if self.fingerprint_counts:
            summary += f"- Average fingerprint count: {np.mean(self.fingerprint_counts):.0f}\n"
            summary += f"- Fingerprint range: {np.min(self.fingerprint_counts)} - {np.max(self.fingerprint_counts)}\n"
        
        if self.peak_counts:
            summary += f"- Average peak count: {np.mean(self.peak_counts):.0f}\n"
        
        for operation, times in self.metrics.items():
            summary += f"- {operation}: average {np.mean(times):.3f}s\n"
        
        return summary
    
    def reset_metrics(self):
        """すべてのメトリクスをリセット"""
        self.metrics.clear()
        self.processing_times.clear()
        self.fingerprint_counts.clear()
        self.peak_counts.clear()
