"""
実際の音源を使用した大量データ性能評価テスト

このテストは実際の音源ファイルを使用して：
1. 大量の楽曲データベース構築
2. フィンガープリント生成・保存性能
3. 音声識別精度・速度の評価
4. データベースバックエンド間の性能比較
を行います。
"""

import unittest
import time
import os
import sys
import tempfile
import shutil
import glob
from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple, Optional
import statistics
import json

try:
    from testcontainers.elasticsearch import ElasticSearchContainer
    from testcontainers.mysql import MySqlContainer  
    from testcontainers.postgres import PostgresContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

# テストユーティリティをインポート
import sys
import os
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from test_utils import TestAudioMixin

from src.database_base import DatabaseConfig, Song
from src.fingerprint_database import FingerprintDatabase, FingerprintMatcher
from src.audio_fingerprinter import AudioFingerprinter, Fingerprint
from src.mimizam import (
    Mimizam, create_mimizam_sqlite, create_mimizam_mysql,
    create_mimizam_postgresql, create_mimizam_elasticsearch
)


class AudioDataGenerator:
    """テスト用の音声データ生成・管理クラス"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.join(os.path.dirname(__file__), '..', 'test_media')
        self.temp_dir = None
        
    def generate_synthetic_audio(self, duration: float = 30.0, num_files: int = 10) -> List[str]:
        """合成音声ファイルを生成"""
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp()
            
        audio_files = []
        sr = 22050
        
        for i in range(num_files):
            # 異なる周波数成分を持つ合成音声を生成
            t = np.linspace(0, duration, int(sr * duration))
            
            # 複数の周波数成分を組み合わせ
            frequencies = [440 + i * 50, 880 + i * 30, 1320 + i * 20]  # 基本周波数を変化
            audio = np.zeros_like(t)
            
            for freq in frequencies:
                audio += 0.3 * np.sin(2 * np.pi * freq * t)
                # ノイズと変調を追加して実際の音楽に近づける
                audio += 0.1 * np.sin(2 * np.pi * freq * 1.5 * t) * np.sin(2 * np.pi * 2 * t)
            
            # ホワイトノイズを追加
            rng = np.random.default_rng(seed=42 + i)  # 再現可能な結果のためのシード
            audio += 0.05 * rng.normal(0, 1, len(audio))
            
            # 正規化
            audio = audio / np.max(np.abs(audio)) * 0.8
            
            # WAVファイルとして保存
            filename = os.path.join(self.temp_dir, f"synthetic_song_{i:03d}.wav")
            
            # soundfileを使用してWAVファイルを保存
            try:
                import soundfile as sf
                sf.write(filename, audio, sr)
                audio_files.append(filename)
            except ImportError:
                # soundfileが無い場合はskip
                print("⚠️ soundfileが必要です: pip install soundfile")
                continue
                
        return audio_files
    
    def get_existing_audio_files(self) -> List[str]:
        """既存の音声ファイルを取得"""
        audio_files = []
        extensions = ['*.wav', '*.mp3', '*.m4a', '*.flac']
        
        for ext in extensions:
            files = glob.glob(os.path.join(self.base_dir, ext))
            audio_files.extend(files)
            
        return audio_files
    
    def create_audio_segments(self, source_file: str, segment_duration: float = 30.0, 
                            num_segments: int = 5) -> List[str]:
        """既存の音声ファイルからセグメントを作成"""
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp()
            
        segments = []
        
        try:
            import librosa
            
            # 音声ファイルを読み込み
            audio, sr = librosa.load(source_file, sr=22050)
            segment_samples = int(segment_duration * sr)
            
            for i in range(num_segments):
                start_sample = i * segment_samples
                end_sample = start_sample + segment_samples
                
                if end_sample > len(audio):
                    break
                    
                segment = audio[start_sample:end_sample]
                filename = os.path.join(self.temp_dir, f"segment_{i:03d}_{Path(source_file).stem}.wav")
                
                # soundfileで保存
                import soundfile as sf
                sf.write(filename, segment, sr)
                segments.append(filename)
                
        except Exception as e:
            print(f"⚠️ セグメント作成エラー: {e}")
            
        return segments
    
    def cleanup(self):
        """一時ファイルをクリーンアップ"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class PerformanceMetrics:
    """性能測定とレポート生成クラス"""
    
    def __init__(self):
        self.metrics = {
            'fingerprint_generation': [],
            'database_operations': {},
            'search_performance': {},
            'identification_accuracy': {}
        }
    
    def time_operation(self, operation_name: str, func, *args, **kwargs):
        """操作の実行時間を測定"""
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        duration = end_time - start_time
        
        if operation_name not in self.metrics:
            self.metrics[operation_name] = []
        self.metrics[operation_name].append(duration)
        
        return result, duration
    
    def add_database_metric(self, backend: str, operation: str, duration: float):
        """データベース操作の性能を記録"""
        if backend not in self.metrics['database_operations']:
            self.metrics['database_operations'][backend] = {}
        if operation not in self.metrics['database_operations'][backend]:
            self.metrics['database_operations'][backend][operation] = []
            
        self.metrics['database_operations'][backend][operation].append(duration)
    
    def add_identification_result(self, backend: str, correct: bool, confidence: float, 
                                response_time: float):
        """識別結果を記録"""
        if backend not in self.metrics['identification_accuracy']:
            self.metrics['identification_accuracy'][backend] = {
                'correct': 0,
                'total': 0,
                'confidence_scores': [],
                'response_times': []
            }
        
        self.metrics['identification_accuracy'][backend]['total'] += 1
        if correct:
            self.metrics['identification_accuracy'][backend]['correct'] += 1
            
        self.metrics['identification_accuracy'][backend]['confidence_scores'].append(confidence)
        self.metrics['identification_accuracy'][backend]['response_times'].append(response_time)
    
    def _generate_fingerprint_report(self) -> Dict:
        """フィンガープリント生成レポートを生成"""
        if not self.metrics['fingerprint_generation']:
            return {}
            
        fp_times = self.metrics['fingerprint_generation']
        return {
            'fingerprint_generation': {
                'mean_time': statistics.mean(fp_times),
                'median_time': statistics.median(fp_times),
                'min_time': min(fp_times),
                'max_time': max(fp_times),
                'total_files': len(fp_times)
            }
        }
    
    def _generate_database_report(self) -> Dict:
        """データベース性能レポートを生成"""
        report = {}
        for backend, operations in self.metrics['database_operations'].items():
            report[backend] = {}
            for operation, times in operations.items():
                if times:
                    report[backend][operation] = {
                        'mean_time': statistics.mean(times),
                        'median_time': statistics.median(times),
                        'min_time': min(times),
                        'max_time': max(times),
                        'operations_count': len(times)
                    }
        return {'database_performance': report}
    
    def _generate_identification_report(self) -> Dict:
        """識別性能レポートを生成"""
        report = {}
        for backend, data in self.metrics['identification_accuracy'].items():
            if data['total'] > 0:
                accuracy = data['correct'] / data['total']
                report[backend] = {
                    'accuracy': accuracy,
                    'total_tests': data['total'],
                    'correct_identifications': data['correct'],
                    'mean_confidence': statistics.mean(data['confidence_scores']) if data['confidence_scores'] else 0,
                    'mean_response_time': statistics.mean(data['response_times']) if data['response_times'] else 0
                }
        return {'identification_performance': report}

    def generate_report(self) -> Dict:
        """性能レポートを生成"""
        report = {}
        
        # 各種レポートを統合
        report.update(self._generate_fingerprint_report())
        report.update(self._generate_database_report()) 
        report.update(self._generate_identification_report())
        
        return report
    
    def print_summary(self):
        """性能サマリーを出力"""
        report = self.generate_report()
        
        print("\n" + "="*80)
        print("🎵 実音源性能評価結果サマリー")
        print("="*80)
        
        # フィンガープリント生成
        if 'fingerprint_generation' in report:
            fp = report['fingerprint_generation']
            print("\n📊 フィンガープリント生成性能:")
            print(f"  処理ファイル数: {fp['total_files']}")
            print(f"  平均処理時間: {fp['mean_time']:.3f}秒/ファイル")
            print(f"  中央値: {fp['median_time']:.3f}秒")
            print(f"  最速: {fp['min_time']:.3f}秒")
            print(f"  最遅: {fp['max_time']:.3f}秒")
        
        # データベース性能比較
        if 'database_performance' in report:
            print("\n🗄️ データベース性能比較:")
            for backend, operations in report['database_performance'].items():
                print(f"\n  【{backend.upper()}】")
                for operation, metrics in operations.items():
                    print(f"    {operation}: {metrics['mean_time']:.3f}秒 "
                          f"(中央値: {metrics['median_time']:.3f}秒, "
                          f"回数: {metrics['operations_count']})")
        
        # 識別性能
        if 'identification_performance' in report:
            print("\n🎯 音声識別性能:")
            for backend, metrics in report['identification_performance'].items():
                print(f"\n  【{backend.upper()}】")
                print(f"    識別精度: {metrics['accuracy']:.1%} "
                      f"({metrics['correct_identifications']}/{metrics['total_tests']})")
                print(f"    平均信頼度: {metrics['mean_confidence']:.3f}")
                print(f"    平均応答時間: {metrics['mean_response_time']:.3f}秒")
        
        print("\n" + "="*80)


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestRealAudioPerformance(unittest.TestCase):
    """実音源を使用した大量データ性能評価テスト"""
    
    def setUp(self):
        """テスト準備"""
        self.audio_generator = AudioDataGenerator()
        self.metrics = PerformanceMetrics()
        self.fingerprinter = AudioFingerprinter()
        
        # テスト設定
        self.max_test_files = 100  # テストファイル数
        self.segment_duration = 30.0  # セグメント長（秒）
        self.identification_samples = 10  # 識別テスト数
        
    def tearDown(self):
        """テスト後処理"""
        self.audio_generator.cleanup()
    
    def _create_sqlite_config(self) -> DatabaseConfig:
        """SQLite設定を作成"""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        return DatabaseConfig(
            backend='sqlite',
            file_path=temp_db.name
        )
    
    def _create_mysql_config(self, container) -> DatabaseConfig:
        """MySQL設定を作成"""
        return DatabaseConfig(
            backend='mysql',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(3306),
            username='test',
            password='test',
            database='test'
        )
    
    def _create_postgresql_config(self, container) -> DatabaseConfig:
        """PostgreSQL設定を作成"""
        return DatabaseConfig(
            backend='postgresql',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(5432),
            username='test',
            password='test',
            database='test'
        )
    
    def _create_elasticsearch_config(self, container) -> DatabaseConfig:
        """Elasticsearch設定を作成"""
        return DatabaseConfig(
            backend='elasticsearch',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(9200),
            index_name="performance_test",
            verify_certs=False
        )
    
    def _wait_for_elasticsearch(self, host: str, port: int, timeout: int = 60) -> bool:
        """Elasticsearchの起動を待機"""
        import requests
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://{host}:{port}/_cluster/health", timeout=5)
                if response.status_code == 200:
                    health = response.json()
                    if health.get('status') in ['green', 'yellow']:
                        return True
            except Exception:
                pass
            time.sleep(2)
        return False
    
    def _prepare_audio_files(self) -> List[str]:
        """テスト用音声ファイルを準備"""
        print("🎵 テスト用音声ファイルを準備中...")
        
        # 既存の音声ファイルを探す
        existing_files = self.audio_generator.get_existing_audio_files()
        audio_files = []
        
        if existing_files:
            print(f"📂 既存ファイルを発見: {len(existing_files)}個")
            # 最初のファイルからセグメントを作成
            for file_path in existing_files[:3]:  # 最大3ファイル
                segments = self.audio_generator.create_audio_segments(
                    file_path, self.segment_duration, 5
                )
                audio_files.extend(segments)
                if len(audio_files) >= self.max_test_files:
                    break
        
        # 不足分は合成音声で補完
        needed_files = max(0, self.max_test_files - len(audio_files))
        if needed_files > 0:
            print(f"🔧 合成音声を生成中: {needed_files}個")
            synthetic_files = self.audio_generator.generate_synthetic_audio(
                self.segment_duration, needed_files
            )
            audio_files.extend(synthetic_files)
        
        print(f"✅ 準備完了: {len(audio_files)}個のテストファイル")
        return audio_files[:self.max_test_files]
    
    def _generate_fingerprints_for_files(self, audio_files: List[str]) -> Dict[str, List[Fingerprint]]:
        """音声ファイルからフィンガープリントを生成"""
        print("🔍 フィンガープリント生成中...")
        fingerprints_data = {}
        
        for i, file_path in enumerate(audio_files):
            print(f"  処理中 ({i+1}/{len(audio_files)}): {Path(file_path).name}")
            
            fingerprints, duration = self.metrics.time_operation(
                'fingerprint_generation',
                self.fingerprinter.fingerprint_file,
                file_path
            )
            
            song_id = f"song_{i:03d}_{Path(file_path).stem}"
            fingerprints_data[song_id] = fingerprints
            
            print(f"    生成: {len(fingerprints)}個のフィンガープリント ({duration:.3f}秒)")
        
        return fingerprints_data
    
    def _test_database_backend(self, backend_name: str, config: DatabaseConfig, 
                             fingerprints_data: Dict[str, List[Fingerprint]]) -> FingerprintDatabase:
        """データベースバックエンドをテスト"""
        print(f"\n📊 {backend_name}バックエンドテスト開始...")
        
        db = FingerprintDatabase(config)
        
        # 楽曲追加性能
        print("  📝 楽曲追加テスト...")
        for song_id, fingerprints in fingerprints_data.items():
            song = Song(
                id=song_id,
                title=f"Test Song {song_id}",
                artist="Test Artist",
                file_path=f"/test/{song_id}.wav"
            )
            
            # 楽曲追加
            _, duration = self.metrics.time_operation(
                'add_song',
                db.add_song,
                song
            )
            self.metrics.add_database_metric(backend_name, 'add_song', duration)
            
            # フィンガープリント追加
            _, duration = self.metrics.time_operation(
                'add_fingerprints',
                db.add_fingerprints,
                song_id,
                fingerprints
            )
            self.metrics.add_database_metric(backend_name, 'add_fingerprints', duration)
        
        # 検索性能テスト
        print("  🔎 検索性能テスト...")
        test_queries = list(fingerprints_data.keys())[:self.identification_samples]
        
        for song_id in test_queries:
            query_fingerprints = fingerprints_data[song_id][:10]  # 最初の10個を使用
            
            # 検索実行
            start_time = time.time()
            matches = db.search_fingerprints(query_fingerprints)
            search_time = time.time() - start_time
            
            self.metrics.add_database_metric(backend_name, 'search', search_time)
            
            # 正解判定
            correct = song_id in matches
            confidence = 1.0 if correct else 0.0  # 簡易的な信頼度
            
            self.metrics.add_identification_result(backend_name, correct, confidence, search_time)
        
        print(f"  ✅ {backend_name}テスト完了")
        return db
    
    def test_sqlite_real_audio_performance(self):
        """SQLiteでの実音源性能テスト"""
        print("\n🗄️ SQLite実音源性能テスト...")
        
        # 音声ファイル準備
        audio_files = self._prepare_audio_files()
        self.assertGreater(len(audio_files), 0, "テスト用音声ファイルが準備できませんでした")
        
        # フィンガープリント生成
        fingerprints_data = self._generate_fingerprints_for_files(audio_files)
        
        # SQLiteテスト
        config = self._create_sqlite_config()
        db = self._test_database_backend('sqlite', config, fingerprints_data)
        
        # 統計確認
        stats = db.get_database_stats()
        self.assertEqual(stats['songs'], len(fingerprints_data))
        
        db.disconnect()
        
        # 性能レポート表示
        self.metrics.print_summary()
        
        # 一時ファイル削除
        if hasattr(config, 'file_path') and os.path.exists(config.file_path):
            os.unlink(config.file_path)
    
    def test_mysql_real_audio_performance(self):
        """MySQLでの実音源性能テスト"""
        print("\n🗄️ MySQL実音源性能テスト...")
        
        with MySqlContainer("mysql:8.0").with_env("MYSQL_ROOT_PASSWORD", "test").with_env(
            "MYSQL_DATABASE", "test"
        ).with_env("MYSQL_USER", "test").with_env("MYSQL_PASSWORD", "test") as mysql:
            
            # 音声ファイル準備
            audio_files = self._prepare_audio_files()
            self.assertGreater(len(audio_files), 0, "テスト用音声ファイルが準備できませんでした")
            
            # フィンガープリント生成
            fingerprints_data = self._generate_fingerprints_for_files(audio_files)
            
            # MySQLテスト
            config = self._create_mysql_config(mysql)
            db = self._test_database_backend('mysql', config, fingerprints_data)
            
            # 統計確認
            stats = db.get_database_stats()
            self.assertEqual(stats['songs'], len(fingerprints_data))
            
            db.disconnect()
    
    def test_postgresql_real_audio_performance(self):
        """PostgreSQLでの実音源性能テスト"""
        print("\n🗄️ PostgreSQL実音源性能テスト...")
        
        with PostgresContainer("postgres:15").with_env("POSTGRES_DB", "test").with_env(
            "POSTGRES_USER", "test"
        ).with_env("POSTGRES_PASSWORD", "test") as postgres:
            
            # 音声ファイル準備
            audio_files = self._prepare_audio_files()
            self.assertGreater(len(audio_files), 0, "テスト用音声ファイルが準備できませんでした")
            
            # フィンガープリント生成
            fingerprints_data = self._generate_fingerprints_for_files(audio_files)
            
            # PostgreSQLテスト
            config = self._create_postgresql_config(postgres)
            db = self._test_database_backend('postgresql', config, fingerprints_data)
            
            # 統計確認
            stats = db.get_database_stats()
            self.assertEqual(stats['songs'], len(fingerprints_data))
            
            db.disconnect()
    
    def test_elasticsearch_real_audio_performance(self):
        """Elasticsearchでの実音源性能テスト"""
        print("\n🗄️ Elasticsearch実音源性能テスト...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            # Elasticsearch起動待機
            config = self._create_elasticsearch_config(elasticsearch)
            self.assertTrue(
                self._wait_for_elasticsearch(config.host, config.port),
                "Elasticsearchの起動に失敗しました"
            )
            
            # 音声ファイル準備
            audio_files = self._prepare_audio_files()
            self.assertGreater(len(audio_files), 0, "テスト用音声ファイルが準備できませんでした")
            
            # フィンガープリント生成
            fingerprints_data = self._generate_fingerprints_for_files(audio_files)
            
            # Elasticsearchテスト
            db = self._test_database_backend('elasticsearch', config, fingerprints_data)
            
            # インデックス更新待機
            time.sleep(2)
            
            # 統計確認
            stats = db.get_database_stats()
            self.assertEqual(stats['songs'], len(fingerprints_data))
            
            db.disconnect()
    
    def test_all_backends_comparison(self):
        """全データベースバックエンドの性能比較テスト"""
        print("\n🏁 全バックエンド性能比較テスト...")
        
        # 音声ファイル準備（共通）
        audio_files = self._prepare_audio_files()
        self.assertGreater(len(audio_files), 0, "テスト用音声ファイルが準備できませんでした")
        
        # フィンガープリント生成（共通）
        fingerprints_data = self._generate_fingerprints_for_files(audio_files)
        
        # SQLiteテスト
        print("\n📊 SQLite比較テスト...")
        sqlite_config = self._create_sqlite_config()
        sqlite_db = self._test_database_backend('sqlite_comparison', sqlite_config, fingerprints_data)
        sqlite_db.disconnect()
        
        # MySQLテスト
        print("\n📊 MySQL比較テスト...")
        with MySqlContainer("mysql:8.0").with_env("MYSQL_ROOT_PASSWORD", "test").with_env(
            "MYSQL_DATABASE", "test"
        ).with_env("MYSQL_USER", "test").with_env("MYSQL_PASSWORD", "test") as mysql:
            mysql_config = self._create_mysql_config(mysql)
            mysql_db = self._test_database_backend('mysql_comparison', mysql_config, fingerprints_data)
            mysql_db.disconnect()
        
        # PostgreSQLテスト
        print("\n📊 PostgreSQL比較テスト...")
        with PostgresContainer("postgres:15").with_env("POSTGRES_DB", "test").with_env(
            "POSTGRES_USER", "test"
        ).with_env("POSTGRES_PASSWORD", "test") as postgres:
            postgresql_config = self._create_postgresql_config(postgres)
            postgresql_db = self._test_database_backend('postgresql_comparison', postgresql_config, fingerprints_data)
            postgresql_db.disconnect()
        
        # Elasticsearchテスト
        print("\n📊 Elasticsearch比較テスト...")
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            es_config = self._create_elasticsearch_config(elasticsearch)
            self.assertTrue(
                self._wait_for_elasticsearch(es_config.host, es_config.port),
                "Elasticsearchの起動に失敗しました"
            )
            
            es_db = self._test_database_backend('elasticsearch_comparison', es_config, fingerprints_data)
            time.sleep(2)  # インデックス更新待機
            es_db.disconnect()
        
        # 性能レポート生成・表示
        self.metrics.print_summary()
        
        # 一時ファイル削除
        if hasattr(sqlite_config, 'file_path') and os.path.exists(sqlite_config.file_path):
            os.unlink(sqlite_config.file_path)


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")  
class TestMultiBackendComparison(TestAudioMixin, unittest.TestCase):
    """複数バックエンド間の性能比較テスト"""
    
    def setUp(self):
        """テスト準備"""
        self.setup_audio()
        self.audio_generator = AudioDataGenerator()
        self.metrics = PerformanceMetrics()
        self.fingerprinter = AudioFingerprinter()
        
        # テスト設定
        self.test_files = 20  # 比較テスト用のファイル数
        self.segment_duration = 10.0  # セグメント長（短縮）
        
    def tearDown(self):
        """テスト後処理"""
        self.teardown_audio()
        self.audio_generator.cleanup()
    
    def _prepare_test_data(self) -> Tuple[List[str], Dict[str, List[Fingerprint]]]:
        """テストデータを準備"""
        print("🎵 比較テスト用データ準備中...")
        
        # 音声ファイル作成
        audio_files = self.audio_generator.generate_synthetic_audio(
            self.segment_duration, self.test_files
        )
        
        # フィンガープリント生成
        fingerprints_data = {}
        for i, file_path in enumerate(audio_files):
            fingerprints = self.fingerprinter.fingerprint_file(file_path)
            song_id = f"comparison_song_{i:03d}"
            fingerprints_data[song_id] = fingerprints
        
        return audio_files, fingerprints_data
    
    def _create_sqlite_config(self) -> DatabaseConfig:
        """SQLite設定を作成"""
        import tempfile
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        return DatabaseConfig(
            backend='sqlite',
            file_path=temp_db.name
        )
    
    def _create_mysql_config(self, container) -> DatabaseConfig:
        """MySQL設定を作成"""
        return DatabaseConfig(
            backend='mysql',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(3306),
            username=container.username,
            password=container.password,
            database=container.dbname
        )
    
    def _create_postgresql_config(self, container) -> DatabaseConfig:
        """PostgreSQL設定を作成"""
        return DatabaseConfig(
            backend='postgresql',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(5432),
            username=container.username,
            password=container.password,
            database=container.dbname
        )
    
    def _create_elasticsearch_config(self, container) -> DatabaseConfig:
        """Elasticsearch設定を作成"""
        return DatabaseConfig(
            backend='elasticsearch',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(9200),
            index_name="fingerprints_performance_test",
            username=None,
            password=None,
            verify_certs=False,
            pool_timeout=30
        )
    
    def _wait_for_elasticsearch(self, host, port, timeout=60):
        """Elasticsearchが利用可能になるまで待機"""
        import requests
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://{host}:{port}/_cluster/health", timeout=5)
                if response.status_code == 200:
                    health = response.json()
                    if health.get('status') in ['green', 'yellow']:
                        print(f"✅ Elasticsearchクラスターの状態: {health.get('status')}")
                        return True
            except Exception:
                pass
            
            print("⏳ Elasticsearchの起動を待機中...")
            time.sleep(5)
        
        print("❌ Elasticsearchの起動タイムアウト")
        return False
    
    def _test_backend_performance(self, backend_name: str, config: DatabaseConfig, 
                                 fingerprints_data: Dict[str, List[Fingerprint]]) -> Dict:
        """バックエンドの性能を測定"""
        print(f"📊 {backend_name}性能測定開始...")
        
        db = FingerprintDatabase(config)
        performance_results = {
            'add_song_times': [],
            'add_fingerprints_times': [],
            'search_times': [],
            'successful_searches': 0,
            'total_searches': 0
        }
        
        try:
            # Elasticsearchの場合は待機
            if backend_name == 'elasticsearch':
                time.sleep(2)
            
            # 楽曲とフィンガープリント追加
            for song_id, fingerprints in fingerprints_data.items():
                song = Song(
                    id=song_id,
                    title=f"Comparison Test Song {song_id}",
                    artist="Performance Test Artist",
                    file_path=f"/test/{song_id}.wav"
                )
                
                # 楽曲追加時間測定
                start_time = time.time()
                db.add_song(song)
                add_song_time = time.time() - start_time
                performance_results['add_song_times'].append(add_song_time)
                
                # フィンガープリント追加時間測定
                start_time = time.time()
                db.add_fingerprints(song_id, fingerprints)
                add_fp_time = time.time() - start_time
                performance_results['add_fingerprints_times'].append(add_fp_time)
            
            # Elasticsearchの場合はインデックス更新待機
            if backend_name == 'elasticsearch':
                time.sleep(3)
            
            # 検索性能測定
            test_songs = list(fingerprints_data.keys())[:5]  # 5曲でテスト
            for song_id in test_songs:
                query_fingerprints = fingerprints_data[song_id][:5]  # 最初の5個
                
                start_time = time.time()
                matches = db.search_fingerprints(query_fingerprints)
                search_time = time.time() - start_time
                
                performance_results['search_times'].append(search_time)
                performance_results['total_searches'] += 1
                
                if song_id in matches:
                    performance_results['successful_searches'] += 1
            
        finally:
            db.disconnect()
        
        return performance_results
    
    def test_all_backends_performance_comparison(self):
        """全バックエンドの性能比較テスト"""
        print("\n🏁 全バックエンド性能比較テストを開始...")
        
        # テストデータ準備
        _, fingerprints_data = self._prepare_test_data()
        
        results = {}
        
        # SQLiteテスト
        print("\n📊 SQLite性能測定...")
        sqlite_config = self._create_sqlite_config()
        try:
            results['sqlite'] = self._test_backend_performance(
                'sqlite', sqlite_config, fingerprints_data
            )
        finally:
            if hasattr(sqlite_config, 'file_path') and os.path.exists(sqlite_config.file_path):
                os.unlink(sqlite_config.file_path)
        
        # MySQLテスト
        print("\n📊 MySQL性能測定...")
        with MySqlContainer("mysql:8.0") as mysql:
            mysql_config = self._create_mysql_config(mysql)
            results['mysql'] = self._test_backend_performance(
                'mysql', mysql_config, fingerprints_data
            )
        
        # PostgreSQLテスト
        print("\n📊 PostgreSQL性能測定...")
        with PostgresContainer("postgres:15") as postgres:
            postgresql_config = self._create_postgresql_config(postgres)
            results['postgresql'] = self._test_backend_performance(
                'postgresql', postgresql_config, fingerprints_data
            )
        
        # Elasticsearchテスト
        print("\n📊 Elasticsearch性能測定...")
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            es_config = self._create_elasticsearch_config(elasticsearch)
            if self._wait_for_elasticsearch(es_config.host, es_config.port):
                results['elasticsearch'] = self._test_backend_performance(
                    'elasticsearch', es_config, fingerprints_data
                )
        
        # 結果分析と表示
        self._print_performance_comparison(results)
        
        # アサーション
        self.assertGreater(len(results), 1, "複数のバックエンドでテストが実行されませんでした")
        for backend, result in results.items():
            self.assertGreater(result['successful_searches'], 0, 
                             f"{backend}で成功した検索がありません")
    
    def _print_performance_comparison(self, results: Dict):
        """性能比較結果を表示"""
        print("\n" + "="*80)
        print("🎯 バックエンド性能比較結果")
        print("="*80)
        
        # ヘッダー
        print(f"{'バックエンド':<15} {'楽曲追加':<12} {'FP追加':<12} {'検索':<10} {'精度':<8}")
        print("-" * 60)
        
        for backend, result in results.items():
            avg_song_add = statistics.mean(result['add_song_times'])
            avg_fp_add = statistics.mean(result['add_fingerprints_times'])
            avg_search = statistics.mean(result['search_times'])
            accuracy = result['successful_searches'] / result['total_searches'] if result['total_searches'] > 0 else 0
            
            print(f"{backend:<15} {avg_song_add:<12.3f} {avg_fp_add:<12.3f} {avg_search:<10.3f} {accuracy:<8.1%}")
        
        print("\n📊 詳細統計:")
        for backend, result in results.items():
            print(f"\n【{backend.upper()}】")
            print(f"  楽曲追加: {statistics.mean(result['add_song_times']):.3f}s ± {statistics.stdev(result['add_song_times']) if len(result['add_song_times']) > 1 else 0:.3f}s")
            print(f"  FP追加:   {statistics.mean(result['add_fingerprints_times']):.3f}s ± {statistics.stdev(result['add_fingerprints_times']) if len(result['add_fingerprints_times']) > 1 else 0:.3f}s")
            print(f"  検索:     {statistics.mean(result['search_times']):.3f}s ± {statistics.stdev(result['search_times']) if len(result['search_times']) > 1 else 0:.3f}s")
            print(f"  精度:     {result['successful_searches']}/{result['total_searches']} ({result['successful_searches']/result['total_searches']*100:.1f}%)")

@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestMimizamPerformanceIntegration(TestAudioMixin, unittest.TestCase):
    """Mimizam統合APIの性能テスト"""
    
    def setUp(self):
        """テスト準備"""
        self.setup_audio()
        self.test_audio_file = self._create_test_audio_file("performance_test.wav")
        self.metrics = PerformanceMetrics()
        
    def tearDown(self):
        """テスト後処理"""
        self.teardown_audio()
    
    def _create_sqlite_config(self) -> DatabaseConfig:
        """SQLite設定を作成"""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        return DatabaseConfig(
            backend='sqlite',
            file_path=temp_db.name
        )
    
    def _create_mysql_config(self, container) -> DatabaseConfig:
        """MySQL設定を作成"""
        return DatabaseConfig(
            backend='mysql',
            host=container.get_container_host_ip(),
            port=container.get_exposed_port(3306),
            username=container.username,
            password=container.password,
            database=container.dbname
        )
    
    def test_mimizam_mysql_performance_workflow(self):
        """MimizamとMySQLの性能ワークフローテスト"""
        print("🎵 Mimizam MySQL性能テストを開始...")
        
        with MySqlContainer("mysql:8.0") as mysql:
            config = self._create_mysql_config(mysql)
            mysql_config = {
                'host': config.host,
                'port': config.port,
                'database': config.database,
                'username': config.username,
                'password': config.password
            }
            
            mimizam = create_mimizam_mysql(
                **mysql_config,
                matcher_config={
                    'min_confidence': 0.1,
                    'max_results': 10,
                    'scoring_method': 'hybrid'
                },
                enable_adaptive_params=False
            )
            
            try:
                performance_metrics = {}
                
                # 楽曲追加性能測定
                start_time = time.time()
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="Mimizam Performance Test Song",
                    artist="Performance Test Artist",
                    song_id="mimizam_perf_test"
                )
                add_song_time = time.time() - start_time
                performance_metrics['add_song_time'] = add_song_time
                
                self.assertTrue(success, "楽曲追加に失敗")
                
                # 検索性能測定（5回実行して平均を取る）
                search_times = []
                for i in range(5):
                    start_time = time.time()
                    results = mimizam.search_song(
                        query_file_path=self.test_audio_file,
                        min_confidence=0.05,
                        top_k=5
                    )
                    search_time = time.time() - start_time
                    search_times.append(search_time)
                    
                    self.assertGreater(len(results), 0, f"検索{i+1}で結果が見つかりません")
                
                performance_metrics['avg_search_time'] = statistics.mean(search_times)
                performance_metrics['search_times'] = search_times
                
                # 識別性能測定
                start_time = time.time()
                identification = mimizam.identify_audio(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.1
                )
                identify_time = time.time() - start_time
                performance_metrics['identify_time'] = identify_time
                
                self.assertIsNotNone(identification, "音声識別に失敗")
                
                # 結果表示
                print("📊 Mimizam MySQL性能結果:")
                print(f"  楽曲追加: {performance_metrics['add_song_time']:.3f}秒")
                print(f"  平均検索: {performance_metrics['avg_search_time']:.3f}秒")
                print(f"  音声識別: {performance_metrics['identify_time']:.3f}秒")
                print(f"  検索結果数: {len(results)}")
                
                # 性能アサーション
                self.assertLess(performance_metrics['add_song_time'], 30.0, "楽曲追加時間が長すぎます")
                self.assertLess(performance_metrics['avg_search_time'], 5.0, "平均検索時間が長すぎます")
                self.assertLess(performance_metrics['identify_time'], 10.0, "識別時間が長すぎます")
                
            finally:
                mimizam.close()
    
    def test_mimizam_sqlite_vs_mysql_comparison(self):
        """SQLiteとMySQLのMimizam性能比較"""
        print("🎵 Mimizam SQLite vs MySQL性能比較を開始...")
        
        performance_results = {}
        
        # SQLiteテスト
        print("📊 SQLite Mimizamテスト...")
        sqlite_config = self._create_sqlite_config()
        mimizam_sqlite = create_mimizam_sqlite(
            db_path=sqlite_config.file_path,
            matcher_config={'min_confidence': 0.1, 'max_results': 5},
            enable_adaptive_params=False
        )
        
        try:
            # SQLite性能測定
            start_time = time.time()
            mimizam_sqlite.add_song(
                file_path=self.test_audio_file,
                title="SQLite Comparison Test",
                artist="Comparison Artist"
            )
            sqlite_add_time = time.time() - start_time
            
            start_time = time.time()
            sqlite_results = mimizam_sqlite.search_song(
                query_file_path=self.test_audio_file,
                min_confidence=0.05,
                top_k=3
            )
            sqlite_search_time = time.time() - start_time
            
            performance_results['sqlite'] = {
                'add_time': sqlite_add_time,
                'search_time': sqlite_search_time,
                'results_count': len(sqlite_results)
            }
            
        finally:
            mimizam_sqlite.close()
            if os.path.exists(sqlite_config.file_path):
                os.unlink(sqlite_config.file_path)
        
        # MySQLテスト
        print("📊 MySQL Mimizamテスト...")
        with MySqlContainer("mysql:8.0") as mysql:
            mysql_config = {
                'host': mysql.get_container_host_ip(),
                'port': mysql.get_exposed_port(3306),
                'database': mysql.dbname,
                'username': mysql.username,
                'password': mysql.password
            }
            
            mimizam_mysql = create_mimizam_mysql(
                **mysql_config,
                matcher_config={'min_confidence': 0.1, 'max_results': 5},
                enable_adaptive_params=False
            )
            
            try:
                # MySQL性能測定
                start_time = time.time()
                mimizam_mysql.add_song(
                    file_path=self.test_audio_file,
                    title="MySQL Comparison Test",
                    artist="Comparison Artist"
                )
                mysql_add_time = time.time() - start_time
                
                start_time = time.time()
                mysql_results = mimizam_mysql.search_song(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.05,
                    top_k=3
                )
                mysql_search_time = time.time() - start_time
                
                performance_results['mysql'] = {
                    'add_time': mysql_add_time,
                    'search_time': mysql_search_time,
                    'results_count': len(mysql_results)
                }
                
            finally:
                mimizam_mysql.close()
        
        # 比較結果表示
        print("\n🎯 Mimizam性能比較結果:")
        print(f"{'バックエンド':<10} {'楽曲追加':<12} {'検索時間':<12} {'結果数':<8}")
        print("-" * 45)
        
        for backend, metrics in performance_results.items():
            print(f"{backend:<10} {metrics['add_time']:<12.3f} {metrics['search_time']:<12.3f} {metrics['results_count']:<8}")
        
        # アサーション
        self.assertEqual(len(performance_results), 2, "両方のバックエンドでテストが実行されませんでした")
        for backend, metrics in performance_results.items():
            self.assertGreater(metrics['results_count'], 0, f"{backend}で検索結果が見つかりません")

# ...existing classes...


if __name__ == "__main__":
    if not TESTCONTAINERS_AVAILABLE:
        print("⚠️  Testcontainersが利用できません。以下のコマンドでインストールしてください：")
        print("pip install testcontainers mysql-connector-python psycopg2-binary elasticsearch")
        sys.exit(1)
    
    # 必要なライブラリの確認
    try:
        import librosa
        import soundfile
    except ImportError as e:
        print(f"⚠️  音声処理ライブラリが不足しています: {e}")
        print("以下のコマンドでインストールしてください：")
        print("pip install librosa soundfile")
        sys.exit(1)
    
    print("🎵 実音源性能評価テストを開始します...")
    print("📊 このテストでは以下を評価します：")
    print("   - フィンガープリント生成性能")
    print("   - データベース操作性能（CRUD）")
    print("   - 音声識別精度と応答速度")
    print("   - バックエンド間の性能比較")
    print("⏳ テストには10-15分かかる場合があります...")
    
    # テスト実行
    unittest.main(verbosity=2, buffer=False)
