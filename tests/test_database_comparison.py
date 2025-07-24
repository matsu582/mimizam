"""
データベースバックエンド比較テスト
SQLite、MySQL、PostgreSQL、Elasticsearchの性能と機能比較
"""

import unittest
import time
import sys
import os
from pathlib import Path
from typing import Dict, Any

# srcディレクトリをパスに追加
try:
    from testcontainers.mysql import MySqlContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.elasticsearch import ElasticSearchContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from mimizam import DatabaseConfig, Song
from mimizam import FingerprintDatabase
from mimizam import Fingerprint


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestDatabaseBackendComparison(unittest.TestCase):
    """データベースバックエンド比較テスト"""
    
    def test_mysql_vs_postgresql_vs_sqlite_performance_comparison(self):
        """MySQL vs PostgreSQL vs SQLite性能比較テスト"""
        print("🏁 MySQL vs PostgreSQL vs SQLite性能比較テスト開始...")
        
        # テスト用データ準備
        test_songs = [
            Song(
                id=f"comparison_test_song_{i}",
                title=f"Comparison Test Song {i}",
                artist=f"Test Artist {i}",
                file_path=f"/path/to/comparison_test{i}.wav"
            )
            for i in range(1, 6)  # 5楽曲
        ]
        
        fingerprints_per_song = 10
        
        # 結果を格納する辞書
        results = {}
        
        # SQLite性能テスト（インメモリ）
        print("📊 SQLite性能テスト...")
        try:
            config = DatabaseConfig(
                backend='sqlite',
                file_path=':memory:'  # インメモリデータベース
            )
            
            db = FingerprintDatabase(config)
            
            # 楽曲追加性能
            start_time = time.time()
            for song in test_songs:
                db.add_song(song)
            song_add_time = time.time() - start_time
            
            # フィンガープリント追加性能
            start_time = time.time()
            for song in test_songs:
                fingerprints = [
                    Fingerprint(hash_value=f"sqlite_comp_hash_{song.id}_{j}", time_offset=j*0.1)
                    for j in range(fingerprints_per_song)
                ]
                db.add_fingerprints(song.id, fingerprints)
            fingerprint_add_time = time.time() - start_time
            
            # 検索性能
            start_time = time.time()
            query_fingerprints = [
                Fingerprint(hash_value=f"sqlite_comp_hash_{test_songs[0].id}_0", time_offset=0.05)
            ]
            matches = db.search_fingerprints(query_fingerprints)
            search_time = time.time() - start_time
            
            results['sqlite'] = {
                'song_add_time': song_add_time,
                'fingerprint_add_time': fingerprint_add_time,
                'search_time': search_time,
                'matches_found': len(matches)
            }
            
            db.disconnect()
            
        except Exception as e:
            print(f"SQLite性能テストエラー: {e}")
            results['sqlite'] = {'error': str(e)}
        
        # MySQL性能テスト
        print("📊 MySQL性能テスト...")
        with MySqlContainer("mysql:8.0") as mysql:
            config = DatabaseConfig(
                backend='mysql',
                host=mysql.get_container_host_ip(),
                port=int(mysql.get_exposed_port(3306)),
                database=mysql.dbname,
                username=mysql.username,
                password=mysql.password
            )
            
            time.sleep(5)  # 起動待機
            
            try:
                db = FingerprintDatabase(config)
                
                # 楽曲追加性能
                start_time = time.time()
                for song in test_songs:
                    db.add_song(song)
                song_add_time = time.time() - start_time
                
                # フィンガープリント追加性能
                start_time = time.time()
                for song in test_songs:
                    fingerprints = [
                        Fingerprint(hash_value=f"mysql_comp_hash_{song.id}_{j}", time_offset=j*0.1)
                        for j in range(fingerprints_per_song)
                    ]
                    db.add_fingerprints(song.id, fingerprints)
                fingerprint_add_time = time.time() - start_time
                
                # 検索性能
                start_time = time.time()
                query_fingerprints = [
                    Fingerprint(hash_value=f"mysql_comp_hash_{test_songs[0].id}_0", time_offset=0.05)
                ]
                matches = db.search_fingerprints(query_fingerprints)
                search_time = time.time() - start_time
                
                results['mysql'] = {
                    'song_add_time': song_add_time,
                    'fingerprint_add_time': fingerprint_add_time,
                    'search_time': search_time,
                    'matches_found': len(matches)
                }
                
                db.disconnect()
                
            except Exception as e:
                print(f"MySQL性能テストエラー: {e}")
                results['mysql'] = {'error': str(e)}
        
        # PostgreSQL性能テスト
        print("📊 PostgreSQL性能テスト...")
        with PostgresContainer("postgres:15") as postgres:
            config = DatabaseConfig(
                backend='postgresql',
                host=postgres.get_container_host_ip(),
                port=int(postgres.get_exposed_port(5432)),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            time.sleep(3)  # 起動待機
            
            try:
                db = FingerprintDatabase(config)
                
                # 楽曲追加性能
                start_time = time.time()
                for song in test_songs:
                    db.add_song(song)
                song_add_time = time.time() - start_time
                
                # フィンガープリント追加性能
                start_time = time.time()
                for song in test_songs:
                    fingerprints = [
                        Fingerprint(hash_value=f"pg_comp_hash_{song.id}_{j}", time_offset=j*0.1)
                        for j in range(fingerprints_per_song)
                    ]
                    db.add_fingerprints(song.id, fingerprints)
                fingerprint_add_time = time.time() - start_time
                
                # 検索性能
                start_time = time.time()
                query_fingerprints = [
                    Fingerprint(hash_value=f"pg_comp_hash_{test_songs[0].id}_0", time_offset=0.05)
                ]
                matches = db.search_fingerprints(query_fingerprints)
                search_time = time.time() - start_time
                
                results['postgresql'] = {
                    'song_add_time': song_add_time,
                    'fingerprint_add_time': fingerprint_add_time,
                    'search_time': search_time,
                    'matches_found': len(matches)
                }
                
                db.disconnect()
                
            except Exception as e:
                print(f"PostgreSQL性能テストエラー: {e}")
                results['postgresql'] = {'error': str(e)}
        
        # 結果の比較と検証
        print("\n📈 性能比較結果:")
        for backend, result in results.items():
            if 'error' not in result:
                print(f"{backend.upper()}:")
                print(f"  楽曲追加: {result['song_add_time']:.3f}s")
                print(f"  フィンガープリント追加: {result['fingerprint_add_time']:.3f}s")
                print(f"  検索: {result['search_time']:.3f}s")
                print(f"  マッチ数: {result['matches_found']}")
                
                # 基本的な妥当性チェック
                self.assertGreater(result['matches_found'], 0, f"{backend}で検索結果が見つかりません")
                self.assertLess(result['song_add_time'], 10.0, f"{backend}の楽曲追加時間が長すぎます")
                self.assertLess(result['fingerprint_add_time'], 30.0, f"{backend}のフィンガープリント追加時間が長すぎます")
                self.assertLess(result['search_time'], 5.0, f"{backend}の検索時間が長すぎます")
            else:
                print(f"{backend.upper()}: エラー - {result['error']}")
        
        # 性能比較分析（SQLite、MySQL、PostgreSQLすべてが成功した場合）
        successful_backends = [name for name, result in results.items() if 'error' not in result]
        if len(successful_backends) >= 2:
            print("\n🔍 詳細比較分析:")
            print("性能ランキング（楽曲追加）:")
            sorted_by_song_add = sorted(successful_backends, key=lambda x: results[x]['song_add_time'])
            for i, backend in enumerate(sorted_by_song_add, 1):
                print(f"  {i}. {backend.upper()}: {results[backend]['song_add_time']:.3f}s")
            
            print("性能ランキング（フィンガープリント追加）:")
            sorted_by_fp_add = sorted(successful_backends, key=lambda x: results[x]['fingerprint_add_time'])
            for i, backend in enumerate(sorted_by_fp_add, 1):
                print(f"  {i}. {backend.upper()}: {results[backend]['fingerprint_add_time']:.3f}s")
            
            print("性能ランキング（検索）:")
            sorted_by_search = sorted(successful_backends, key=lambda x: results[x]['search_time'])
            for i, backend in enumerate(sorted_by_search, 1):
                print(f"  {i}. {backend.upper()}: {results[backend]['search_time']:.3f}s")
    
    def test_database_feature_compatibility(self):
        """データベース機能互換性テスト"""
        print("🔧 データベース機能互換性テスト開始...")
        
        # 共通テストデータ
        test_song = Song(
            id="feature_test_song",
            title="Feature Test Song",
            artist="Feature Test Artist",
            file_path="/path/to/feature_test.wav"
        )
        
        test_fingerprints = [
            Fingerprint(hash_value="feature_hash1", time_offset=0.1),
            Fingerprint(hash_value="feature_hash2", time_offset=0.2),
            Fingerprint(hash_value="feature_hash3", time_offset=0.3),
        ]
        
        # 機能テスト結果
        feature_results = {}
        
        # MySQL機能テスト
        print("🔧 MySQL機能テスト...")
        with MySqlContainer("mysql:8.0") as mysql:
            config = DatabaseConfig(
                backend='mysql',
                host=mysql.get_container_host_ip(),
                port=int(mysql.get_exposed_port(3306)),
                database=mysql.dbname,
                username=mysql.username,
                password=mysql.password
            )
            
            time.sleep(5)
            
            try:
                db = FingerprintDatabase(config)
                
                # 基本機能テスト
                features = self._test_database_features(db, test_song, test_fingerprints)
                feature_results['mysql'] = features
                
                db.disconnect()
                
            except Exception as e:
                feature_results['mysql'] = {'error': str(e)}
        
        # PostgreSQL機能テスト
        print("🔧 PostgreSQL機能テスト...")
        with PostgresContainer("postgres:15") as postgres:
            config = DatabaseConfig(
                backend='postgresql',
                host=postgres.get_container_host_ip(),
                port=int(postgres.get_exposed_port(5432)),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            time.sleep(3)
            
            try:
                db = FingerprintDatabase(config)
                
                # 基本機能テスト
                features = self._test_database_features(db, test_song, test_fingerprints)
                feature_results['postgresql'] = features
                
                db.disconnect()
                
            except Exception as e:
                feature_results['postgresql'] = {'error': str(e)}
        
        # 機能互換性分析
        print("\n🔍 機能互換性分析:")
        for backend, features in feature_results.items():
            if 'error' not in features:
                print(f"{backend.upper()}:")
                for feature, status in features.items():
                    status_icon = "✅" if status else "❌"
                    print(f"  {feature}: {status_icon}")
                
                # 全機能が動作することを確認
                for feature, status in features.items():
                    self.assertTrue(status, f"{backend}の{feature}機能が失敗")
            else:
                print(f"{backend.upper()}: エラー - {features['error']}")
                self.fail(f"{backend}機能テストでエラーが発生: {features['error']}")
    
    def _test_database_features(self, db: FingerprintDatabase, test_song: Song, test_fingerprints: list) -> Dict[str, bool]:
        """データベースの基本機能をテスト"""
        features = {}
        
        try:
            # 楽曲追加機能
            features['song_add'] = db.add_song(test_song)
            
            # 楽曲取得機能
            retrieved_song = db.get_song(test_song.id)
            features['song_get'] = retrieved_song is not None and retrieved_song.title == test_song.title
            
            # フィンガープリント追加機能
            features['fingerprint_add'] = db.add_fingerprints(test_song.id, test_fingerprints)
            
            # フィンガープリント検索機能
            query_fingerprints = [
                Fingerprint(hash_value="feature_hash1", time_offset=0.05)
            ]
            matches = db.search_fingerprints(query_fingerprints)
            features['fingerprint_search'] = test_song.id in matches
            
            # 楽曲リスト機能
            all_songs = db.list_songs()
            features['song_list'] = len(all_songs) > 0 and any(song.id == test_song.id for song in all_songs)
            
            # 統計取得機能
            stats = db.get_database_stats()
            features['stats'] = isinstance(stats, dict) and 'songs' in stats and 'fingerprints' in stats
            
        except Exception as e:
            print(f"機能テスト中にエラー: {e}")
            # エラーが発生した機能については False を設定
            for feature in ['song_add', 'song_get', 'fingerprint_add', 'fingerprint_search', 'song_list', 'stats']:
                if feature not in features:
                    features[feature] = False
        
        return features
    
    def test_all_backends_performance_comparison(self):
        """SQLite vs MySQL vs PostgreSQL vs Elasticsearch 全バックエンド性能比較テスト"""
        print("🏁 全バックエンド（SQLite、MySQL、PostgreSQL、Elasticsearch）性能比較テスト開始...")
        
        # テスト用データ準備
        test_songs = [
            Song(
                id=f"all_backends_test_song_{i}",
                title=f"All Backends Test Song {i}",
                artist=f"Test Artist {i}",
                file_path=f"/path/to/all_backends_test{i}.wav"
            )
            for i in range(1, 4)  # 3楽曲（Elasticsearchは時間がかかるため）
        ]
        
        fingerprints_per_song = 8
        
        # 各バックエンドをテスト
        results = {}
        results['sqlite'] = self._test_sqlite_performance(test_songs, fingerprints_per_song)
        results['mysql'] = self._test_mysql_performance(test_songs, fingerprints_per_song)
        results['postgresql'] = self._test_postgresql_performance(test_songs, fingerprints_per_song)
        results['elasticsearch'] = self._test_elasticsearch_performance(test_songs, fingerprints_per_song)
        
        # 結果の分析と検証
        self._analyze_all_backends_results(results)
    
    def _test_sqlite_performance(self, test_songs, fingerprints_per_song):
        """SQLite性能テスト"""
        print("📊 SQLite性能テスト...")
        try:
            config = DatabaseConfig(backend='sqlite', file_path=':memory:')
            return self._run_performance_test(config, test_songs, fingerprints_per_song, "sqlite_all")
        except Exception as e:
            print(f"SQLite性能テストエラー: {e}")
            return {'error': str(e)}
    
    def _test_mysql_performance(self, test_songs, fingerprints_per_song):
        """MySQL性能テスト"""
        print("📊 MySQL性能テスト...")
        try:
            with MySqlContainer("mysql:8.0") as mysql:
                config = DatabaseConfig(
                    backend='mysql',
                    host=mysql.get_container_host_ip(),
                    port=int(mysql.get_exposed_port(3306)),
                    database=mysql.dbname,
                    username=mysql.username,
                    password=mysql.password
                )
                time.sleep(5)
                return self._run_performance_test(config, test_songs, fingerprints_per_song, "mysql_all")
        except Exception as e:
            print(f"MySQL性能テストエラー: {e}")
            return {'error': str(e)}
    
    def _test_postgresql_performance(self, test_songs, fingerprints_per_song):
        """PostgreSQL性能テスト"""
        print("📊 PostgreSQL性能テスト...")
        try:
            with PostgresContainer("postgres:15") as postgres:
                config = DatabaseConfig(
                    backend='postgresql',
                    host=postgres.get_container_host_ip(),
                    port=int(postgres.get_exposed_port(5432)),
                    database=postgres.dbname,
                    username=postgres.username,
                    password=postgres.password
                )
                time.sleep(3)
                return self._run_performance_test(config, test_songs, fingerprints_per_song, "pg_all")
        except Exception as e:
            print(f"PostgreSQL性能テストエラー: {e}")
            return {'error': str(e)}
    
    def _test_elasticsearch_performance(self, test_songs, fingerprints_per_song):
        """Elasticsearch性能テスト"""
        print("📊 Elasticsearch性能テスト...")
        try:
            with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
                "discovery.type", "single-node"
            ).with_env(
                "xpack.security.enabled", "false"
            ).with_env(
                "xpack.security.http.ssl.enabled", "false"
            ).with_env(
                "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
            ) as elasticsearch:
                config = DatabaseConfig(
                    backend='elasticsearch',
                    host=elasticsearch.get_container_host_ip(),
                    port=int(elasticsearch.get_exposed_port(9200)),
                    index_name="all_backends_comparison",
                    verify_certs=False,
                    pool_timeout=30
                )
                time.sleep(20)
                result = self._run_performance_test(config, test_songs, fingerprints_per_song, "es_all", 
                                                   has_index_delay=True)
                return result
        except Exception as e:
            print(f"Elasticsearch性能テストエラー: {e}")
            return {'error': str(e)}
    
    def _run_performance_test(self, config, test_songs, fingerprints_per_song, hash_prefix, has_index_delay=False):
        """共通の性能テスト実行"""
        db = FingerprintDatabase(config)
        
        # 楽曲追加性能
        start_time = time.time()
        for song in test_songs:
            db.add_song(song)
        song_add_time = time.time() - start_time
        
        if has_index_delay:
            time.sleep(1)
        
        # フィンガープリント追加性能
        start_time = time.time()
        for song in test_songs:
            fingerprints = [
                Fingerprint(hash_value=f"{hash_prefix}_hash_{song.id}_{j}", time_offset=j*0.1)
                for j in range(fingerprints_per_song)
            ]
            db.add_fingerprints(song.id, fingerprints)
        fingerprint_add_time = time.time() - start_time
        
        if has_index_delay:
            time.sleep(2)
        
        # 検索性能
        start_time = time.time()
        query_fingerprints = [
            Fingerprint(hash_value=f"{hash_prefix}_hash_{test_songs[0].id}_0", time_offset=0.05)
        ]
        matches = db.search_fingerprints(query_fingerprints)
        search_time = time.time() - start_time
        
        db.disconnect()
        
        return {
            'song_add_time': song_add_time,
            'fingerprint_add_time': fingerprint_add_time,
            'search_time': search_time,
            'matches_found': len(matches)
        }
    
    def _analyze_all_backends_results(self, results):
        """全バックエンド結果の分析と検証"""
        print("\n📈 全バックエンド性能比較結果:")
        
        for backend, result in results.items():
            if 'error' not in result:
                print(f"{backend.upper()}:")
                print(f"  楽曲追加: {result['song_add_time']:.3f}s")
                print(f"  フィンガープリント追加: {result['fingerprint_add_time']:.3f}s")
                print(f"  検索: {result['search_time']:.3f}s")
                print(f"  マッチ数: {result['matches_found']}")
                
                # 基本的な妥当性チェック
                self.assertGreater(result['matches_found'], 0, f"{backend}で検索結果が見つかりません")
                self._validate_backend_performance(backend, result)
            else:
                print(f"{backend.upper()}: エラー - {result['error']}")
        
        # 性能ランキングの表示
        self._display_performance_rankings(results)
    
    def _validate_backend_performance(self, backend, result):
        """バックエンド別の性能検証"""
        if backend == 'elasticsearch':
            self.assertLess(result['song_add_time'], 20.0, f"{backend}の楽曲追加時間が長すぎます")
            self.assertLess(result['fingerprint_add_time'], 60.0, f"{backend}のフィンガープリント追加時間が長すぎます")
            self.assertLess(result['search_time'], 15.0, f"{backend}の検索時間が長すぎます")
        else:
            self.assertLess(result['song_add_time'], 10.0, f"{backend}の楽曲追加時間が長すぎます")
            self.assertLess(result['fingerprint_add_time'], 30.0, f"{backend}のフィンガープリント追加時間が長すぎます")
            self.assertLess(result['search_time'], 5.0, f"{backend}の検索時間が長すぎます")
    
    def _display_performance_rankings(self, results):
        """性能ランキングの表示"""
        successful_backends = [name for name, result in results.items() if 'error' not in result]
        
        if len(successful_backends) >= 2:
            print("\n🔍 詳細比較分析（全バックエンド）:")
            
            # 各操作の性能ランキング
            self._show_ranking("楽曲追加", successful_backends, results, 'song_add_time')
            self._show_ranking("フィンガープリント追加", successful_backends, results, 'fingerprint_add_time')
            self._show_ranking("検索", successful_backends, results, 'search_time')
            
            # 各バックエンドの特徴分析
            print("\n💡 バックエンド特徴分析:")
            backend_characteristics = {
                'sqlite': "高速（インメモリ）、開発・テスト向け",
                'mysql': "バランス型、安定性重視",
                'postgresql': "高機能、大規模データ向け",
                'elasticsearch': "検索特化、スケーラブル"
            }
            
            for backend in successful_backends:
                if backend in backend_characteristics:
                    print(f"  {backend.upper()}: {backend_characteristics[backend]}")
    
    def _show_ranking(self, operation_name, backends, results, metric_key):
        """特定の操作の性能ランキングを表示"""
        print(f"性能ランキング（{operation_name}）:")
        sorted_backends = sorted(backends, key=lambda x: results[x][metric_key])
        for i, backend in enumerate(sorted_backends, 1):
            print(f"  {i}. {backend.upper()}: {results[backend][metric_key]:.3f}s")


if __name__ == "__main__":
    if not TESTCONTAINERS_AVAILABLE:
        print("⚠️  Testcontainersが利用できません。以下のコマンドでインストールしてください：")
        print("pip install testcontainers")
        sys.exit(1)
    
    print("🏁 データベースバックエンド比較テストを開始します...")
    print("⏳ 複数のコンテナを起動するため、時間がかかる場合があります...")
    
    # 全てのテストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = unittest.main(exit=False, verbosity=2)
    
    # 適切なコードで終了
    sys.exit(0 if result.result.wasSuccessful() else 1)
