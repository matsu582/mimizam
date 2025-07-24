"""
Mimizamクラスの統合テスト（SQLiteとコンテナレステスト）

このテストファイルは、MimizamのSQLite統合APIをテストします。
各データベースバックエンドのコンテナテストは以下のファイルを参照してください：
- tests/test_mysql_containers.py - MySQL Mimizam統合テスト
- tests/test_postgresql_containers.py - PostgreSQL Mimizam統合テスト  
- tests/test_elasticsearch_containers.py - Elasticsearch Mimizam統合テスト

audio_fingerprinter.pyとfingerprint_database.pyの個別クラステストは既存のテストファイルで
カバーしているため、ここではMimizamクラスの高レベルAPIに焦点を当てます。
"""

import unittest
import time
import sys
import os
import tempfile
import numpy as np
import librosa
from pathlib import Path
from typing import List, Optional


try:
    from testcontainers.elasticsearch import ElasticSearchContainer
    from testcontainers.mysql import MySqlContainer
    from testcontainers.postgres import PostgresContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError as e:
    print(f"Testcontainers import error: {e}")
    TESTCONTAINERS_AVAILABLE = False
    # 代替クラスを定義
    class ElasticSearchContainer:
        pass
    class MySqlContainer:
        pass  
    class PostgresContainer:
        pass

from mimizam import (
    Mimizam, create_mimizam_sqlite, create_mimizam_mysql,
    create_mimizam_postgresql, create_mimizam_elasticsearch
)
from mimizam import DatabaseConfig


class TestMimizamSQLite(unittest.TestCase):
    """MimizamのSQLiteバックエンドテスト"""
    
    def setUp(self):
        """各テストの前処理"""
        # テスト用の一時ファイルを作成
        self.temp_dir = tempfile.mkdtemp()
        self.test_audio_file = self.create_test_audio_file()
        
        # Mimizamインスタンスを作成（SQLite、インメモリ）
        self.mimizam = create_mimizam_sqlite(
            db_path=':memory:',
            matcher_config={
                'min_confidence': 0.1,
                'max_results': 10,
                'scoring_method': 'hybrid'
            },
            enable_adaptive_params=False  # テストの一貫性のため無効化
        )
    
    def tearDown(self):
        """各テストの後処理"""
        if hasattr(self, 'mimizam'):
            self.mimizam.close()
        
        # 一時ファイルの削除
        if hasattr(self, 'test_audio_file') and os.path.exists(self.test_audio_file):
            os.unlink(self.test_audio_file)
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def create_test_audio_file(self) -> str:
        """テスト用の音声ファイルを作成"""
        # シンプルな合成音声を作成
        duration = 3.0
        sr = 22050
        t = np.linspace(0, duration, int(duration * sr))
        
        # 複数の周波数成分を持つ信号
        audio = (
            0.5 * np.sin(2 * np.pi * 440 * t) +  # A4
            0.3 * np.sin(2 * np.pi * 880 * t) +  # A5
            0.2 * np.sin(2 * np.pi * 1320 * t)   # E6
        )
        
        # ファイルに保存
        audio_file = os.path.join(self.temp_dir, "test_audio.wav")
        try:
            import soundfile as sf
            sf.write(audio_file, audio, sr)
        except ImportError:
            # soundfileが利用できない場合、wavファイル形式で直接保存
            import wave
            with wave.open(audio_file, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sr)
                # float32からint16に変換
                audio_int16 = (audio * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
        return audio_file
    
    def test_add_song_basic(self):
        """基本的な楽曲追加テスト"""
        song_id = self.mimizam.add_song(
            file_path=self.test_audio_file,
            title="Test Song",
            artist="Test Artist",
            song_id="test_song_1"
        )
        
        self.assertIsNotNone(song_id, "楽曲の追加に失敗しました")
        self.assertEqual(song_id, "test_song_1", "指定されたsong_idが返されませんでした")
        
        # データベース統計を確認
        stats = self.mimizam.get_database_stats()
        self.assertEqual(stats['songs'], 1)
        self.assertGreater(stats['fingerprints'], 0)
    
    def test_add_and_retrieve_song(self):
        """楽曲追加と取得のテスト"""
        song_id = "test_song_retrieve"
        title = "Retrieve Test Song"
        artist = "Retrieve Test Artist"
        
        # 楽曲を追加
        returned_song_id = self.mimizam.add_song(
            file_path=self.test_audio_file,
            title=title,
            artist=artist,
            song_id=song_id
        )
        self.assertIsNotNone(returned_song_id)
        self.assertEqual(returned_song_id, song_id)
        
        # 楽曲を取得
        retrieved_song = self.mimizam.get_song(song_id)
        self.assertIsNotNone(retrieved_song)
        self.assertEqual(retrieved_song.title, title)
        self.assertEqual(retrieved_song.artist, artist)
        self.assertEqual(retrieved_song.file_path, self.test_audio_file)
    
    def test_search_song_exact_match(self):
        """完全一致での楽曲検索テスト"""
        # 楽曲を追加
        song_id = "test_song_search"
        self.mimizam.add_song(
            file_path=self.test_audio_file,
            title="Search Test Song",
            artist="Search Test Artist",
            song_id=song_id
        )
        
        # 同じファイルで検索
        results = self.mimizam.search_song(
            query_file_path=self.test_audio_file,
            min_confidence=0.1,
            top_k=5
        )
        
        # 結果を検証
        self.assertGreater(len(results), 0, "検索結果が見つかりません")
        
        best_match = results[0]
        self.assertEqual(best_match['song'].id, song_id)
        self.assertGreater(best_match['confidence'], 0.5, "信頼度が低すぎます")
        self.assertGreater(best_match['match_count'], 0)
    
    def test_identify_audio(self):
        """音声識別テスト"""
        # 楽曲を追加
        song_id = "test_song_identify"
        self.mimizam.add_song(
            file_path=self.test_audio_file,
            title="Identify Test Song",
            artist="Identify Test Artist",
            song_id=song_id
        )
        
        # 音声を識別
        result = self.mimizam.identify_audio(
            query_file_path=self.test_audio_file,
            min_confidence=0.3
        )
        
        # 結果を検証
        self.assertIsNotNone(result, "音声識別に失敗しました")
        song, confidence = result
        self.assertEqual(song.id, song_id)
        self.assertGreater(confidence, 0.3)
    
    def test_list_songs(self):
        """楽曲一覧取得テスト"""
        # 最初は空
        songs = self.mimizam.list_songs()
        self.assertEqual(len(songs), 0)
        
        # 複数の楽曲を追加
        for i in range(3):
            self.mimizam.add_song(
                file_path=self.test_audio_file,
                title=f"Song {i+1}",
                artist=f"Artist {i+1}",
                song_id=f"song_{i+1}"
            )
        
        # 楽曲一覧を取得
        songs = self.mimizam.list_songs()
        self.assertEqual(len(songs), 3)
        
        # 楽曲の詳細を確認
        titles = [song.title for song in songs]
        self.assertIn("Song 1", titles)
        self.assertIn("Song 2", titles)
        self.assertIn("Song 3", titles)
    
    def test_delete_song(self):
        """楽曲削除テスト"""
        # 楽曲を追加
        song_id = "test_song_delete"
        self.mimizam.add_song(
            file_path=self.test_audio_file,
            title="Delete Test Song",
            artist="Delete Test Artist",
            song_id=song_id
        )
        
        # 楽曲が存在することを確認
        self.assertIsNotNone(self.mimizam.get_song(song_id))
        
        # 楽曲を削除
        success = self.mimizam.delete_song(song_id)
        self.assertTrue(success)
        
        # 楽曲が削除されたことを確認
        self.assertIsNone(self.mimizam.get_song(song_id))
    
    def test_context_manager(self):
        """コンテキストマネージャーとしての使用テスト"""
        with create_mimizam_sqlite(':memory:') as mimizam:
            # 楽曲を追加
            song_id = mimizam.add_song(
                file_path=self.test_audio_file,
                title="Context Test Song",
                artist="Context Test Artist"
            )
            self.assertIsNotNone(song_id)
            
            # 統計を確認
            stats = mimizam.get_database_stats()
            self.assertEqual(stats['songs'], 1)
        
        # コンテキスト終了後は自動的にクローズされる


if __name__ == '__main__':
    print("🎵 Mimizam SQLite統合テストを開始します...")
    print("📌 注意: コンテナベースのMimizam統合テストは以下のファイルで実行してください:")
    print("  - tests/test_mysql_containers.py")
    print("  - tests/test_postgresql_containers.py")
    print("  - tests/test_elasticsearch_containers.py")
    
    unittest.main(verbosity=2)
