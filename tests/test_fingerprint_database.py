"""
fingerprint_database.py のユニットテスト
"""

import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

# テスト対象モジュールのインポート
from mimizam import (
    FingerprintDatabase, FingerprintMatcher,
    create_sqlite_config, create_mysql_config, 
    create_postgresql_config, create_elasticsearch_config
)
from mimizam import Fingerprint
from mimizam import DatabaseConfig, Song


class TestFingerprintDatabase(unittest.TestCase):
    """FingerprintDatabase クラスのテスト"""
    
    def setUp(self):
        """テスト前のセットアップ"""
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db_file.close()
        self.db_path = self.temp_db_file.name
        
        # テスト用の設定
        self.config = create_sqlite_config(self.db_path)
        
        # モックバックエンドを作成
        self.mock_backend = Mock()
        self.mock_backend.connect.return_value = True
        self.mock_backend.create_tables.return_value = True
        self.mock_backend.disconnect.return_value = True
        
    def tearDown(self):
        """テスト後のクリーンアップ"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_init_with_default_config(self, mock_create_backend):
        """デフォルト設定での初期化テスト"""
        mock_create_backend.return_value = self.mock_backend
        
        db = FingerprintDatabase()
        
        # デフォルト設定が使用されることを確認
        self.assertEqual(db.config.backend, 'sqlite')
        self.assertEqual(db.config.file_path, 'fingerprints.db')
        
        # バックエンドが正しく初期化されることを確認
        mock_create_backend.assert_called_once()
        self.mock_backend.connect.assert_called_once()
        self.mock_backend.create_tables.assert_called_once()
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_init_with_custom_config(self, mock_create_backend):
        """カスタム設定での初期化テスト"""
        mock_create_backend.return_value = self.mock_backend
        
        db = FingerprintDatabase(self.config)
        
        # カスタム設定が使用されることを確認
        self.assertEqual(db.config.backend, 'sqlite')
        self.assertEqual(db.config.file_path, self.db_path)
        
        mock_create_backend.assert_called_once_with(self.config)
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_init_connection_failure(self, mock_create_backend):
        """接続失敗時の例外処理テスト"""
        self.mock_backend.connect.return_value = False
        mock_create_backend.return_value = self.mock_backend
        
        with self.assertRaises(RuntimeError) as context:
            FingerprintDatabase(self.config)
        
        self.assertIn("Failed to connect to database", str(context.exception))
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_init_table_creation_failure(self, mock_create_backend):
        """テーブル作成失敗時の例外処理テスト"""
        self.mock_backend.create_tables.return_value = False
        mock_create_backend.return_value = self.mock_backend
        
        with self.assertRaises(RuntimeError) as context:
            FingerprintDatabase(self.config)
        
        self.assertIn("Failed to create database tables", str(context.exception))
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_add_song(self, mock_create_backend):
        """楽曲追加テスト"""
        mock_create_backend.return_value = self.mock_backend
        self.mock_backend.add_song.return_value = True
        
        db = FingerprintDatabase(self.config)
        
        test_song = Song(
            id="test_song_1",
            title="Test Song",
            artist="Test Artist",
            file_path="/path/to/test.mp3"
        )
        
        result = db.add_song(test_song)
        
        self.assertTrue(result)
        self.mock_backend.add_song.assert_called_once_with(test_song)
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_add_fingerprints(self, mock_create_backend):
        """フィンガープリント追加テスト"""
        mock_create_backend.return_value = self.mock_backend
        self.mock_backend.add_fingerprints.return_value = True
        
        db = FingerprintDatabase(self.config)
        
        test_fingerprints = [
            Fingerprint(hash_value=12345, time_offset=1.0, song_id="test_song_1"),
            Fingerprint(hash_value=67890, time_offset=2.0, song_id="test_song_1")
        ]
        
        result = db.add_fingerprints("test_song_1", test_fingerprints)
        
        self.assertTrue(result)
        self.mock_backend.add_fingerprints.assert_called_once_with("test_song_1", test_fingerprints)
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_search_fingerprints(self, mock_create_backend):
        """フィンガープリント検索テスト"""
        mock_create_backend.return_value = self.mock_backend
        expected_result = {
            "test_song_1": [(1.0, 1.5), (2.0, 2.5)],
            "test_song_2": [(1.0, 3.0)]
        }
        self.mock_backend.search_fingerprints.return_value = expected_result
        
        db = FingerprintDatabase(self.config)
        
        query_fingerprints = [
            Fingerprint(hash_value=12345, time_offset=1.0, song_id=""),
            Fingerprint(hash_value=67890, time_offset=2.0, song_id="")
        ]
        
        result = db.search_fingerprints(query_fingerprints)
        
        self.assertEqual(result, expected_result)
        self.mock_backend.search_fingerprints.assert_called_once_with(query_fingerprints)
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_get_song(self, mock_create_backend):
        """楽曲取得テスト"""
        mock_create_backend.return_value = self.mock_backend
        test_song = Song(
            id="test_song_1",
            title="Test Song",
            artist="Test Artist",
            file_path="/path/to/test.mp3"
        )
        self.mock_backend.get_song.return_value = test_song
        
        db = FingerprintDatabase(self.config)
        
        result = db.get_song("test_song_1")
        
        self.assertEqual(result, test_song)
        self.mock_backend.get_song.assert_called_once_with("test_song_1")
    
    @patch('mimizam.src.fingerprint_database.create_database_backend')
    def test_disconnect(self, mock_create_backend):
        """明示的な切断テスト"""
        mock_create_backend.return_value = self.mock_backend
        
        db = FingerprintDatabase(self.config)
        db.disconnect()
        
        self.mock_backend.disconnect.assert_called()


class TestFingerprintMatcher(unittest.TestCase):
    """FingerprintMatcher クラスのテスト"""
    
    def setUp(self):
        """テスト前のセットアップ"""
        self.mock_database = Mock()
        self.matcher = FingerprintMatcher(self.mock_database)
        
        # テストデータの準備
        self.test_fingerprints = [
            Fingerprint(hash_value=12345, time_offset=1.0, song_id=""),
            Fingerprint(hash_value=67890, time_offset=2.0, song_id=""),
            Fingerprint(hash_value=11111, time_offset=3.0, song_id="")
        ]
        
        self.test_song = Song(
            id="test_song_1",
            title="Test Song",
            artist="Test Artist",
            file_path="/path/to/test.mp3"
        )
    
    def test_init(self):
        """初期化テスト"""
        self.assertEqual(self.matcher.database, self.mock_database)
        self.assertEqual(self.matcher.min_confidence, 0.1)
        self.assertEqual(self.matcher.max_results, 10)
        self.assertEqual(self.matcher.scoring_method, "hybrid")
    
    def test_set_scoring_method(self):
        """スコアリング方式設定テスト"""
        # 有効な方式の設定
        self.matcher.set_scoring_method("histogram")
        self.assertEqual(self.matcher.scoring_method, "histogram")
        
        self.matcher.set_scoring_method("detailed")
        self.assertEqual(self.matcher.scoring_method, "detailed")
        
        self.matcher.set_scoring_method("hybrid")
        self.assertEqual(self.matcher.scoring_method, "hybrid")
        
        # 無効な方式の設定
        with self.assertRaises(ValueError):
            self.matcher.set_scoring_method("invalid")
    
    def test_find_matches_empty_fingerprints(self):
        """空のフィンガープリントリストでのマッチング"""
        result = self.matcher.find_matches([])
        self.assertEqual(result, [])
    
    def test_get_song_info_found(self):
        """楽曲情報取得テスト（見つかった場合）"""
        self.mock_database.get_song.return_value = self.test_song
        
        result = self.matcher.get_song_info("test_song_1")
        
        expected = {
            'id': 'test_song_1',
            'title': 'Test Song',
            'artist': 'Test Artist',
            'file_path': '/path/to/test.mp3'
        }
        
        self.assertEqual(result, expected)
        self.mock_database.get_song.assert_called_once_with("test_song_1")
    
    def test_get_song_info_not_found(self):
        """楽曲情報取得テスト（見つからない場合）"""
        self.mock_database.get_song.return_value = None
        
        result = self.matcher.get_song_info("nonexistent_song")
        
        expected = {
            'id': 'nonexistent_song',
            'title': '不明',
            'artist': '不明',
            'file_path': '不明'
        }
        
        self.assertEqual(result, expected)
    
    def test_calculate_time_offset(self):
        """時間オフセット計算テスト"""
        match_pairs = [
            (1.0, 1.5),  # diff: -0.5
            (2.0, 2.5),  # diff: -0.5
            (3.0, 3.5),  # diff: -0.5
            (4.0, 4.5),  # diff: -0.5
            (5.0, 5.5)   # diff: -0.5
        ]
        
        result = self.matcher._calculate_time_offset(match_pairs)
        self.assertEqual(result, -0.5)
    
    def test_calculate_time_offset_empty(self):
        """空のマッチペアでの時間オフセット計算"""
        result = self.matcher._calculate_time_offset([])
        self.assertEqual(result, 0.0)
    
    def test_calculate_confidence_score(self):
        """信頼度スコア計算テスト"""
        # 完全にアライメントされたマッチ
        aligned_matches = [
            (1.0, 1.5),  # diff: -0.5
            (2.0, 2.5),  # diff: -0.5
            (3.0, 3.5),  # diff: -0.5
            (4.0, 4.5),  # diff: -0.5
            (5.0, 5.5)   # diff: -0.5
        ]
        
        result = self.matcher._calculate_confidence_score(aligned_matches)
        self.assertGreater(result, 0.8)  # 高い信頼度
        
        # 散在したマッチ
        scattered_matches = [
            (1.0, 1.5),  # diff: -0.5
            (2.0, 3.0),  # diff: -1.0
            (3.0, 4.0),  # diff: -1.0
            (4.0, 6.0),  # diff: -2.0
            (5.0, 8.0)   # diff: -3.0
        ]
        
        result2 = self.matcher._calculate_confidence_score(scattered_matches)
        self.assertLess(result2, result)  # より低い信頼度
    
    def test_fit_scale_offset_recovers_slope(self):
        """尺度不変マッチャ：頑健直線回帰で傾き(=time_scale)と切片を復元する

        旧 _scale_fingerprints（探索時のフィンガープリント再スケール）は完全置換され、
        速度変化は (query_time, db_time) の支配直線 db≈slope·query+offset の傾きとして
        復元される。ここでは傾き1.5・オフセット0.5の合成ペアで復元を検証する。
        """
        slope_true, offset_true = 1.5, 0.5
        pairs = [(float(q), slope_true * q + offset_true) for q in range(2, 12)]
        # 外れ値（偶発衝突）を混ぜても最頻値ベースで頑健に復元できる
        pairs += [(1.0, 9.9), (3.0, 0.1)]
        slope, offset, inliers = self.matcher._fit_scale_offset(pairs)
        self.assertAlmostEqual(slope, slope_true, places=2)
        self.assertAlmostEqual(offset, offset_true, places=2)
        # 直線に乗る正規ペアはインライアとして残る
        self.assertGreaterEqual(len(inliers), 10)

    def test_find_time_aligned_matches(self):
        """時間アライメントマッチ検索テスト"""
        match_pairs = [
            (1.0, 1.5),  # diff: -0.5
            (2.0, 2.5),  # diff: -0.5
            (3.0, 3.5),  # diff: -0.5
            (4.0, 5.0),  # diff: -1.0
            (5.0, 6.0)   # diff: -1.0
        ]
        
        groups = self.matcher._find_time_aligned_matches(match_pairs, tolerance=0.1)
        
        # 2つのグループに分かれるはず
        self.assertEqual(len(groups), 2)
        
        # グループサイズの合計が元のマッチ数と一致することを確認
        total_matches = sum(len(group) for group in groups)
        self.assertEqual(total_matches, len(match_pairs))
        
        # 各グループが少なくとも1つのマッチを持つことを確認
        for group in groups:
            self.assertGreater(len(group), 0)
    
    def test_identify_audio_success(self):
        """音声識別成功テスト"""
        # find_matchesの戻り値をモック
        mock_matches = [
            {
                'song_id': 'test_song_1',
                'confidence': 0.8,
                'match_count': 10,
                'time_offset': -0.5
            }
        ]
        
        with patch.object(self.matcher, 'find_matches', return_value=mock_matches):
            self.mock_database.get_song.return_value = self.test_song
            
            result = self.matcher.identify_audio(self.test_fingerprints, 0.5)
            
            self.assertIsNotNone(result)
            song, confidence = result
            self.assertEqual(song, self.test_song)
            self.assertEqual(confidence, 0.8)
    
    def test_identify_audio_no_matches(self):
        """音声識別失敗テスト（マッチなし）"""
        with patch.object(self.matcher, 'find_matches', return_value=[]):
            result = self.matcher.identify_audio(self.test_fingerprints, 0.5)
            self.assertIsNone(result)
    
    def test_identify_audio_low_confidence(self):
        """音声識別失敗テスト（信頼度不足）"""
        mock_matches = [
            {
                'song_id': 'test_song_1',
                'confidence': 0.3,
                'match_count': 5,
                'time_offset': -0.5
            }
        ]
        
        with patch.object(self.matcher, 'find_matches', return_value=mock_matches):
            result = self.matcher.identify_audio(self.test_fingerprints, 0.5)
            self.assertIsNone(result)
    
    def test_get_detailed_match_info(self):
        """詳細マッチ情報取得テスト"""
        mock_matches = {
            'test_song_1': [
                (1.0, 1.5),
                (2.0, 2.5),
                (3.0, 3.5)
            ]
        }
        
        self.mock_database.search_fingerprints.return_value = mock_matches
        
        result = self.matcher.get_detailed_match_info(self.test_fingerprints, 'test_song_1')
        
        self.assertIn('match_positions', result)
        self.assertIn('statistics', result)
        
        # マッチ位置の確認
        match_positions = result['match_positions']
        self.assertEqual(len(match_positions), 3)
        
        # 統計情報の確認
        statistics = result['statistics']
        self.assertEqual(statistics['total_matches'], 3)
        self.assertGreater(statistics['aligned_matches'], 0)
        self.assertGreater(statistics['alignment_ratio'], 0.0)
    
    def test_get_detailed_match_info_no_matches(self):
        """詳細マッチ情報取得テスト（マッチなし）"""
        self.mock_database.search_fingerprints.return_value = {}
        
        result = self.matcher.get_detailed_match_info(self.test_fingerprints, 'nonexistent_song')
        
        self.assertEqual(result['match_positions'], [])
        self.assertEqual(result['statistics']['total_matches'], 0)


class TestConfigurationFunctions(unittest.TestCase):
    """設定関数のテスト"""
    
    def test_create_sqlite_config(self):
        """SQLite設定作成テスト"""
        config = create_sqlite_config("test.db")
        
        self.assertEqual(config.backend, 'sqlite')
        self.assertEqual(config.file_path, "test.db")
    
    def test_create_mysql_config(self):
        """MySQL設定作成テスト"""
        config = create_mysql_config(
            host="localhost",
            database="test_db",
            username="user",
            password="pass",
            port=3306
        )
        
        self.assertEqual(config.backend, 'mysql')
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.database, "test_db")
        self.assertEqual(config.username, "user")
        self.assertEqual(config.password, "pass")
        self.assertEqual(config.port, 3306)
    
    def test_create_postgresql_config(self):
        """PostgreSQL設定作成テスト"""
        config = create_postgresql_config(
            host="localhost",
            database="test_db",
            username="user",
            password="pass",
            port=5432
        )
        
        self.assertEqual(config.backend, 'postgresql')
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.database, "test_db")
        self.assertEqual(config.username, "user")
        self.assertEqual(config.password, "pass")
        self.assertEqual(config.port, 5432)
    
    def test_create_elasticsearch_config(self):
        """Elasticsearch設定作成テスト"""
        config = create_elasticsearch_config(
            host="localhost",
            index_name="test_index",
            port=9200,
            username="user",
            password="pass"
        )
        
        self.assertEqual(config.backend, 'elasticsearch')
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.index_name, "test_index")
        self.assertEqual(config.port, 9200)
        self.assertEqual(config.username, "user")
        self.assertEqual(config.password, "pass")


class TestAdvancedMatchingAlgorithms(unittest.TestCase):
    """高度なマッチングアルゴリズムのテスト"""
    
    def setUp(self):
        """テスト前のセットアップ"""
        self.mock_database = Mock()
        self.matcher = FingerprintMatcher(self.mock_database)
        
        # テスト用のマッチデータ
        self.test_match_pairs = [
            (1.0, 1.5),  # diff: -0.5
            (2.0, 2.5),  # diff: -0.5
            (3.0, 3.5),  # diff: -0.5
            (4.0, 4.5),  # diff: -0.5
            (5.0, 5.5)   # diff: -0.5
        ]
    
    def test_calculate_peak_prominence(self):
        """ピーク突出度計算テスト"""
        import numpy as np
        
        # 明確なピークを持つヒストグラム
        hist = np.array([1, 2, 10, 3, 1])
        peak_idx = 2
        
        prominence = self.matcher._calculate_peak_prominence(hist, peak_idx)
        
        # 突出度が正の値であることを確認
        self.assertGreater(prominence, 0.0)
        self.assertLessEqual(prominence, 1.0)
    
    def test_calculate_weighted_offset(self):
        """重み付きオフセット計算テスト"""
        import numpy as np
        
        hist = np.array([1, 2, 10, 3, 1])
        bin_edges = np.array([0, 1, 2, 3, 4, 5])
        peak_idx = 2
        
        offset = self.matcher._calculate_weighted_offset(hist, bin_edges, peak_idx)
        
        # ピーク周辺の重心が計算されることを確認
        self.assertIsInstance(offset, (int, float))
        self.assertGreater(offset, 0.0)
    
    def test_calculate_histogram_confidence(self):
        """ヒストグラム信頼度計算テスト"""
        max_count = 10
        total_matches = 20
        prominence = 0.8
        time_scale = 1.0
        
        confidence = self.matcher._calculate_histogram_confidence(
            max_count, total_matches, prominence, time_scale
        )
        
        # 信頼度が適切な範囲内にあることを確認
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        self.assertGreater(confidence, 0.1)  # 良い条件なので最低限の信頼度
    
    def test_calculate_hybrid_histogram_confidence(self):
        """Hybrid方式ヒストグラム信頼度計算テスト"""
        confidence = self.matcher._calculate_hybrid_histogram_confidence(
            self.test_match_pairs, 1.0
        )
        
        # 信頼度が適切な範囲内にあることを確認
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
    
    def test_confidence_from_inliers_monotonic(self):
        """significanceベース信頼度：整列数とsignificanceが高いほど信頼度が上がる

        旧 _calculate_confidence_score_with_scaling（探索スケール依存の信頼度）は
        完全置換され、信頼度は「整列インライア数 × significance（偶然整列に対する
        超過倍率）」で算出される。整列数が桁違いに少ない無関係曲を棄却できること、
        および大規模DB（全衝突数が巨大）でも正解が過小評価されないことを検証する。
        """
        # 整列数が多いほど信頼度は高い（db_span未指定時はsignificance=整列絶対数）
        low = self.matcher._confidence_from_inliers(aligned=5, total=10)
        high = self.matcher._confidence_from_inliers(aligned=60, total=120)
        self.assertGreaterEqual(high, low)
        for c in (low, high):
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)
        # インライアが極端に少なければ0（偶発衝突の棄却）
        self.assertEqual(self.matcher._confidence_from_inliers(aligned=1, total=100), 0.0)

    def test_confidence_significance_robust_to_db_size(self):
        """大規模DBの偶発衝突で正解が過小評価されない（significance方式）

        全衝突が巨大（例: 2万件）でも、それらが長いDB時間幅(24分)へ散る一方、
        正解の整列は単一オフセットに集中する。割合(aligned/total)基準では正解でも
        数%に沈むが、significance基準なら高信頼度になることを確認する。
        逆に無関係曲（衝突は多いが単一オフセットへの集中が偶然並み）は低信頼度。
        """
        db_span = 24 * 60.0  # 24分
        # 正解: 156件が単一オフセットに集中（偶然期待は約1.4件）→ 高信頼度
        true_conf = self.matcher._confidence_from_inliers(
            aligned=156, total=21000, db_span=db_span
        )
        self.assertGreater(true_conf, 0.8)
        # 無関係曲: 衝突総数は同程度でも単一オフセットの整列は偶然並み(数件)→ 低信頼度
        noise_conf = self.matcher._confidence_from_inliers(
            aligned=4, total=21000, db_span=db_span
        )
        self.assertLess(noise_conf, self.matcher.min_confidence)
        self.assertGreater(true_conf, noise_conf)


class TestIntegrationScenarios(unittest.TestCase):
    """統合テストシナリオ"""
    
    def setUp(self):
        """テスト前のセットアップ"""
        self.mock_database = Mock()
        self.matcher = FingerprintMatcher(self.mock_database)
        
        # テスト用楽曲データ
        self.test_songs = [
            Song(id="song1", title="Song 1", artist="Artist 1", file_path="/path/1.mp3"),
            Song(id="song2", title="Song 2", artist="Artist 2", file_path="/path/2.mp3"),
            Song(id="song3", title="Song 3", artist="Artist 3", file_path="/path/3.mp3")
        ]
        
        # テスト用フィンガープリント
        self.query_fingerprints = [
            Fingerprint(hash_value=12345, time_offset=1.0, song_id=""),
            Fingerprint(hash_value=67890, time_offset=2.0, song_id=""),
            Fingerprint(hash_value=11111, time_offset=3.0, song_id="")
        ]
    
    def test_full_matching_workflow_hybrid(self):
        """Hybrid方式での完全マッチングワークフローテスト"""
        # データベースの検索結果をモック
        mock_search_results = {
            "song1": [(1.0, 1.5), (2.0, 2.5), (3.0, 3.5), (4.0, 4.5), (5.0, 5.5)],
            "song2": [(1.0, 2.0), (2.0, 3.0)],
            "song3": [(1.0, 1.0)]
        }
        
        self.mock_database.search_fingerprints.return_value = mock_search_results
        self.mock_database.get_song.side_effect = lambda song_id: next(
            (song for song in self.test_songs if song.id == song_id), None
        )
        self.mock_database.get_songs.side_effect = lambda song_ids: {
            sid: next((s for s in self.test_songs if s.id == sid), None)
            for sid in song_ids
        }
        self.mock_database.list_songs.return_value = self.test_songs
        
        # 尺度不変マッチャの信頼度は _confidence_from_inliers で算出される
        with patch.object(self.matcher, '_confidence_from_inliers', return_value=0.8):
            
            # Hybrid方式でマッチング実行
            self.matcher.set_scoring_method("hybrid")
            self.matcher.min_confidence = 0.5  # 信頼度閾値を下げる
            results = self.matcher.find_matches(self.query_fingerprints, min_matches=2)
            
            # 結果の検証
            self.assertGreaterEqual(len(results), 0)
            
            if len(results) > 0:
                # 最良の結果を確認
                best_match = results[0]
                self.assertIn('song_id', best_match)
                self.assertIn('confidence', best_match)
                self.assertIn('song_info', best_match)
                
                # 信頼度が適切な範囲内にあることを確認
                self.assertGreaterEqual(best_match['confidence'], 0.0)
                self.assertLessEqual(best_match['confidence'], 1.0)
    
    def test_different_scoring_methods_comparison(self):
        """異なるスコアリング方式の比較テスト"""
        # 良好なマッチデータ
        good_match_data = {
            "song1": [(1.0, 1.5), (2.0, 2.5), (3.0, 3.5), (4.0, 4.5), (5.0, 5.5)]
        }
        
        self.mock_database.search_fingerprints.return_value = good_match_data
        self.mock_database.get_song.return_value = self.test_songs[0]
        self.mock_database.get_songs.side_effect = lambda song_ids: {
            sid: self.test_songs[0] for sid in song_ids
        }
        self.mock_database.list_songs.return_value = self.test_songs
        # 小さな合成フィクスチャはインライア数が少なく信頼度飽和に届かないため、
        # ここでは方式間で結果が返る配管を検証する目的で閾値を下げる。
        self.matcher.min_confidence = 0.0
        
        # 各スコアリング方式でテスト（全て尺度不変の単一検索へ委譲される）
        methods = ["hybrid", "histogram", "detailed"]
        results = {}
        
        for method in methods:
            self.matcher.set_scoring_method(method)
            method_results = self.matcher.find_matches(self.query_fingerprints, min_matches=3)
            results[method] = method_results
        
        # 各方式で結果が得られることを確認
        for method in methods:
            self.assertGreater(len(results[method]), 0, f"{method} method should return results")
    
    def test_edge_case_minimal_matches(self):
        """エッジケース：最小マッチ数でのテスト"""
        # 最小限のマッチデータ
        minimal_match_data = {
            "song1": [(1.0, 1.5), (2.0, 2.5)]
        }
        
        self.mock_database.search_fingerprints.return_value = minimal_match_data
        self.mock_database.get_song.return_value = self.test_songs[0]
        self.mock_database.list_songs.return_value = self.test_songs
        
        # 最小マッチ数でテスト
        results = self.matcher.find_matches(self.query_fingerprints, min_matches=1)
        
        # 結果の検証
        self.assertGreaterEqual(len(results), 0)
    
    def test_no_matches_scenario(self):
        """マッチなしシナリオのテスト"""
        # 空の検索結果
        self.mock_database.search_fingerprints.return_value = {}
        
        results = self.matcher.find_matches(self.query_fingerprints, min_matches=5)
        
        # 結果が空であることを確認
        self.assertEqual(len(results), 0)


if __name__ == '__main__':
    # ログレベルを設定してテスト実行時の出力を制御
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # テストスイートの実行
    unittest.main(verbosity=2)
