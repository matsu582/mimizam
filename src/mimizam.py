"""
Mimizam - 音声・映像指紋システム

AudioFingerprinter、FingerprintDatabase、FingerprintMatcherを統合し、
音楽の追加、検索、管理機能を提供する高レベルAPIを提供。
VideoFingerprinterによる映像指紋機能も統合。
"""

import os
import uuid
import logging
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import json

from .audio_fingerprinter import AudioFingerprinter
from .fingerprint_database import FingerprintDatabase, FingerprintMatcher
from .database_base import DatabaseConfig, Song, Fingerprint, Video


class Mimizam:
    """Shazam風音声指紋のメインクラス"""
    
    def __init__(self, config: Optional[DatabaseConfig] = None, 
                 fingerprinter_config: Optional[Dict[str, Any]] = None,
                 matcher_config: Optional[Dict[str, Any]] = None):
        """
        Mimizamシステムを初期化
        
        Args:
            config: データベース設定。Noneの場合はデフォルトのSQLite設定を使用
            fingerprinter_config: AudioFingerprinterの設定パラメータ
            matcher_config: FingerprintMatcherの設定パラメータ
                - min_confidence: 最小信頼度スコア (float, default: 0.1)
                - max_results: 最大結果数 (int, default: 5)
                - scoring_method: スコアリング手法 (str, default: 'hybrid')
        """
        self.logger = logging.getLogger(__name__)
        
        # デフォルトのfingerprinter設定
        default_fingerprinter_config = {
            'n_fft': 2048,
            'hop_length': 512,
            'sr': 22050,
            'min_amplitude': -60,
            'peak_neighborhood_size': 10,
            'enable_adaptive_params': True,
            'audible_only': False
        }
        
        if fingerprinter_config:
            default_fingerprinter_config.update(fingerprinter_config)
        
        # デフォルトのmatcher設定
        default_matcher_config = {
            'min_confidence': 0.1,
            'max_results': 5,
            'scoring_method': 'hybrid'
        }
        
        if matcher_config:
            default_matcher_config.update(matcher_config)
        
        # コンポーネントを初期化
        self.fingerprinter = AudioFingerprinter(**default_fingerprinter_config)
        self.database = FingerprintDatabase(config)
        self.matcher = FingerprintMatcher(self.database)
        
        # Matcherの設定を適用
        self.matcher.min_confidence = default_matcher_config['min_confidence']
        self.matcher.max_results = default_matcher_config['max_results']
        if hasattr(self.matcher, 'set_scoring_method'):
            self.matcher.set_scoring_method(default_matcher_config['scoring_method'])
        
        self.logger.info("Mimizam system initialized")
        self.logger.info(f"Database backend: {self.database.config.backend}")
        self.logger.info(f"Matcher configuration - confidence: {default_matcher_config['min_confidence']}, max results: {default_matcher_config['max_results']}, scoring: {default_matcher_config['scoring_method']}")
    
    def add_song(self, file_path: str, title: str, artist: str, 
                 song_id: Optional[str] = None,
                 meta_json: Optional[str] = None) -> Optional[str]:
        """
        音楽ファイルをシステムに追加
        
        音声ファイルから指紋を生成し、メタデータとともにデータベースに保存します。
        
        Args:
            file_path: 音声ファイルのパス
            title: 楽曲タイトル
            artist: アーティスト名
            song_id: 楽曲ID（指定しない場合は自動生成）
            meta_json: 追加のメタ情報（JSON文字列、任意）
            
        Returns:
            Optional[str]: 追加に成功した場合は楽曲ID、失敗した場合はNone
            
        Raises:
            FileNotFoundError: 指定されたファイルが存在しない場合
            ValueError: 音声ファイルの読み込みに失敗した場合
        """
        try:
            # ファイルの存在確認
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Audio file not found: {file_path}")
            
            # 楽曲IDの生成
            if song_id is None:
                song_id = str(uuid.uuid4())
            
            self.logger.info(f"Adding song: {title} by {artist} ({file_path})")
            
            # 音声フィンガープリントを生成
            self.logger.debug("Generating audio fingerprints...")
            fingerprints = self.fingerprinter.fingerprint_file(file_path)
            
            if not fingerprints:
                self.logger.warning(f"No fingerprints generated: {file_path}")
                return None
            
            self.logger.info(f"Generated {len(fingerprints)} fingerprints")
            
            # 楽曲メタデータを作成
            meta_dict = None
            if meta_json:
                try:
                    meta_dict = json.loads(meta_json)
                except Exception as e:
                    self.logger.warning(f"Failed to parse meta_json: {e}")
            song = Song(
                id=song_id,
                title=title,
                artist=artist,
                file_path=file_path,
                meta=meta_dict if meta_dict else None
            )
            
            # データベースに楽曲を追加
            if not self.database.add_song(song):
                self.logger.error(f"Failed to add song: {song_id}")
                return None
            
            # フィンガープリントをデータベースに追加
            if not self.database.add_fingerprints(song_id, fingerprints):
                self.logger.error(f"Failed to add fingerprints: {song_id}")
                # 楽曲も削除
                self.database.delete_song(song_id)
                return None
            
            self.logger.info(f"Song successfully added: {song_id} - {title} by {artist}")
            return song_id
            
        except FileNotFoundError:
            self.logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error occurred while adding song: {e}")
            return None
    
    def search_song(self, query_file_path: str, 
                    min_confidence: float = 0.1,
                    top_k: int = 5) -> List[Dict[str, Any]]:
        """
        音声ファイルでデータベースを検索
        
        指定された音声ファイルからフィンガープリントを生成し、
        データベース内の楽曲と照合して類似楽曲を検索します。
        
        Args:
            query_file_path: 検索対象の音声ファイルパス
            min_confidence: 最小信頼度スコア（0.0-1.0）
            top_k: 返す結果の最大数
            
        Returns:
            List[Dict]: 検索結果のリスト。各辞書には以下のキーが含まれます：
                - song: Song オブジェクト（楽曲情報）
                - confidence: 信頼度スコア（0.0-1.0）
                - match_count: マッチしたフィンガープリント数
                - details: 詳細なマッチング情報
                
        Raises:
            FileNotFoundError: 指定されたファイルが存在しない場合
            ValueError: 音声ファイルの読み込みに失敗した場合
        """
        try:
            # ファイルの存在確認
            if not os.path.exists(query_file_path):
                raise FileNotFoundError(f"Audio file not found: {query_file_path}")
            
            self.logger.info(f"Starting audio search: {query_file_path}")
            
            # クエリ音声からフィンガープリントを生成
            self.logger.debug("Generating fingerprints for query audio...")
            query_fingerprints = self.fingerprinter.fingerprint_file(query_file_path)
            
            if not query_fingerprints:
                self.logger.warning(f"No fingerprints generated from query file: {query_file_path}")
                return []
            
            self.logger.info(f"Generated {len(query_fingerprints)} query fingerprints")
            
            # マッチャーの設定を更新
            self.matcher.min_confidence = min_confidence
            self.matcher.max_results = top_k
            
            # データベースで検索
            self.logger.debug("Searching in database...")
            matches = self.matcher.find_matches(
                query_fingerprints,
                min_matches=3,  # 最小マッチ数
                top_k=top_k,
                include_details=True
            )
            
            # 結果を整形
            results = []
            for match in matches:
                song_id = match.get('song_id')
                if song_id:
                    song = self.database.get_song(song_id)
                    if song:
                        result = {
                            'song': song,
                            'confidence': match.get('confidence', 0.0),
                            'match_count': match.get('match_count', 0),
                            'details': match
                        }
                        results.append(result)
            
            self.logger.info(f"Retrieved {len(results)} search results")
            return results
            
        except FileNotFoundError:
            self.logger.error(f"File not found: {query_file_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error occurred during audio search: {e}")
            return []
    
    def identify_audio(self, query_file_path: str, 
                      min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
        """
        音声ファイルを識別（最も可能性の高い楽曲を1つ返す）
        
        Args:
            query_file_path: 識別対象の音声ファイルパス
            min_confidence: 最小信頼度スコア
            
        Returns:
            Optional[Tuple[Song, float]]: 識別された楽曲と信頼度のタプル。
                                       識別できなかった場合はNone
        """
        results = self.search_song(query_file_path, min_confidence, top_k=1)
        
        if results and results[0]['confidence'] >= min_confidence:
            return (results[0]['song'], results[0]['confidence'])
        return None
    
    def list_songs(self) -> List[Song]:
        """
        データベース内の全楽曲をリスト取得
        
        Returns:
            List[Song]: 楽曲リスト
        """
        return self.database.list_songs()
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """
        指定されたIDの楽曲情報を取得
        
        Args:
            song_id: 楽曲ID
            
        Returns:
            Optional[Song]: 楽曲情報。見つからない場合はNone
        """
        return self.database.get_song(song_id)
    
    def delete_song(self, song_id: str) -> bool:
        """
        楽曲をデータベースから削除
        
        Args:
            song_id: 削除する楽曲のID
            
        Returns:
            bool: 削除に成功した場合True、失敗した場合False
        """
        try:
            result = self.database.delete_song(song_id)
            if result:
                self.logger.info(f"Song deleted: {song_id}")
            else:
                self.logger.warning(f"Failed to delete song: {song_id}")
            return result
        except Exception as e:
            self.logger.error(f"Error occurred during song deletion: {e}")
            return False
    
    def get_database_stats(self) -> Dict[str, int]:
        """
        データベースの統計情報を取得
        
        Returns:
            Dict[str, int]: 統計情報（楽曲数、フィンガープリント数など）
        """
        return self.database.get_database_stats()
    
    # ===== 映像指紋機能 =====

    def _ensure_video_system(self) -> None:
        """映像指紋システムを遅延初期化"""
        if not hasattr(self, '_video_fingerprinter'):
            self._video_fingerprinter = None
        if not hasattr(self, '_video_db'):
            self._video_db = None

    def _get_video_fingerprinter(self):
        """映像指紋生成器を取得（遅延インポート）"""
        self._ensure_video_system()
        if self._video_fingerprinter is None:
            from .video_fingerprinter import VideoFingerprinter
            self._video_fingerprinter = VideoFingerprinter()
        return self._video_fingerprinter

    def _get_video_db(self, db_path: Optional[str] = None):
        """映像指紋DBを取得（遅延インポート）"""
        self._ensure_video_system()
        if self._video_db is None:
            from .video_database import VideoFingerprintDatabase
            if db_path is None:
                # 音声DBと同じディレクトリに映像DBを配置
                if hasattr(self.database, 'config') and self.database.config.file_path:
                    base_dir = os.path.dirname(
                        self.database.config.file_path
                    )
                    db_path = os.path.join(
                        base_dir, "video_fingerprints.db"
                    ) if base_dir else "video_fingerprints.db"
                else:
                    db_path = "video_fingerprints.db"
            self._video_db = VideoFingerprintDatabase(db_path)
        return self._video_db

    def add_video(
        self,
        file_path: str,
        title: str,
        video_id: Optional[str] = None,
        video_db_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        映像ファイルをシステムに追加

        映像から指紋を生成し、データベースに保存。
        モデルが未学習の場合は、この映像で学習も行う。

        Args:
            file_path: 映像ファイルのパス
            title: 映像タイトル
            video_id: 映像ID（指定しない場合は自動生成）
            video_db_path: 映像DBファイルパス

        Returns:
            追加に成功した場合は映像ID、失敗した場合はNone
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(
                    f"映像ファイルが見つかりません: {file_path}"
                )

            if video_id is None:
                video_id = str(uuid.uuid4())

            vfp = self._get_video_fingerprinter()
            vdb = self._get_video_db(video_db_path)

            # モデル未学習の場合はこの映像で学習
            if not vfp.is_trained:
                self.logger.info(
                    "モデル未学習: この映像で学習を実行"
                )
                vfp.train_from_videos([file_path])

            fp = vfp.fingerprint_video(file_path)
            if fp is None:
                self.logger.error(
                    f"映像指紋生成失敗: {file_path}"
                )
                return None

            # DBに保存
            import cv2
            cap = cv2.VideoCapture(file_path)
            duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(
                cap.get(cv2.CAP_PROP_FPS), 1
            )
            cap.release()

            video = Video(
                id=video_id,
                title=title,
                file_path=file_path,
                duration=duration,
                frame_count=fp.frame_count,
            )
            vdb.add_video(video)
            vdb.add_video_fingerprint(
                video_id, fp.video_fingerprint, fp.descriptor_count
            )
            vdb.add_frame_fingerprints(
                video_id, fp.frame_fingerprints
            )

            self.logger.info(
                f"映像追加成功: {video_id} - {title}"
            )
            return video_id

        except FileNotFoundError:
            raise
        except Exception as exc:
            self.logger.error(f"映像追加エラー: {exc}")
            return None

    def search_video(
        self,
        query_file_path: str,
        top_k: int = 5,
        use_frame_matching: bool = True,
        video_db_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        映像ファイルでデータベースを検索

        2段階検索:
          1. 映像全体指紋で高速候補絞り込み
          2. フレーム単位指紋で精密照合（PiP対策）

        Args:
            query_file_path: 検索対象の映像ファイルパス
            top_k: 返す結果の最大数
            use_frame_matching: フレーム単位マッチングを使用するか
            video_db_path: 映像DBファイルパス

        Returns:
            検索結果のリスト
        """
        try:
            if not os.path.exists(query_file_path):
                raise FileNotFoundError(
                    f"映像ファイルが見つかりません: {query_file_path}"
                )

            vfp = self._get_video_fingerprinter()
            vdb = self._get_video_db(video_db_path)

            if not vfp.is_trained:
                self.logger.warning(
                    "モデルが未学習です。"
                    "先にadd_video()で映像を登録してください"
                )
                return []

            fp = vfp.fingerprint_video(query_file_path)
            if fp is None:
                return []

            # Step 1: 映像全体指紋で候補絞り込み
            candidates = vdb.search_video(
                fp.video_fingerprint, top_k=top_k * 2
            )

            if not use_frame_matching or not candidates:
                return candidates[:top_k]

            # Step 2: フレーム単位マッチングで精密照合
            candidate_ids = [c["video_id"] for c in candidates]
            frame_results = vdb.search_video_with_frame_matching(
                fp.frame_fingerprints, candidate_ids
            )

            # 結果を統合
            frame_map = {
                r["video_id"]: r for r in frame_results
            }
            results = []
            for cand in candidates:
                vid = cand["video_id"]
                entry = {
                    "video_id": vid,
                    "video_similarity": cand["similarity"],
                    "video": cand["video"],
                }
                if vid in frame_map:
                    entry["frame_similarity"] = frame_map[vid][
                        "frame_similarity"
                    ]
                    # 最終スコア: フレームマッチングの結果を優先
                    entry["similarity"] = max(
                        cand["similarity"],
                        frame_map[vid]["frame_similarity"],
                    )
                else:
                    entry["frame_similarity"] = None
                    entry["similarity"] = cand["similarity"]
                results.append(entry)

            results.sort(
                key=lambda r: r["similarity"], reverse=True
            )
            return results[:top_k]

        except FileNotFoundError:
            raise
        except Exception as exc:
            self.logger.error(f"映像検索エラー: {exc}")
            return []

    def train_video_model(
        self,
        video_paths: List[str],
        model_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        複数映像から映像指紋モデルを学習

        Args:
            video_paths: 学習用映像ファイルパスのリスト
            model_path: モデル保存先パス（オプション）

        Returns:
            学習統計情報
        """
        vfp = self._get_video_fingerprinter()
        stats = vfp.train_from_videos(video_paths)
        if model_path:
            vfp.save_model(model_path)
        return stats

    def load_video_model(self, model_path: str) -> None:
        """
        保存済み映像指紋モデルを読み込み

        Args:
            model_path: モデルファイルパス
        """
        vfp = self._get_video_fingerprinter()
        vfp.load_model(model_path)

    def get_video_database_stats(
        self, video_db_path: Optional[str] = None
    ) -> Dict[str, int]:
        """映像指紋DBの統計情報を取得"""
        vdb = self._get_video_db(video_db_path)
        return vdb.get_stats()

    def close(self) -> None:
        """
        Mimizamシステムを終了（データベース接続を閉じる）
        """
        if hasattr(self, 'database') and self.database:
            self.database.disconnect()
        if hasattr(self, '_video_db') and self._video_db:
            self._video_db.close()
            self._video_db = None
        self.logger.info("Mimizam system terminated")
    
    def __enter__(self):
        """コンテキストマネージャーのエントリ"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.close()
    
    def __del__(self):
        """デストラクタ"""
        self.close()

# 以下、各種バックエンド用のユーティリティ関数

def create_mimizam_sqlite(db_path: str = "mimizam.db", 
                         matcher_config: Optional[Dict[str, Any]] = None,
                         **fingerprinter_config) -> Mimizam:
    """
    SQLiteバックエンドを使用するMimizamインスタンスを簡単に作成
    
    Args:
        db_path: SQLiteデータベースファイルのパス
        matcher_config: FingerprintMatcherの設定パラメータ
        **fingerprinter_config: AudioFingerprinterの設定パラメータ
        
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    """
    config = DatabaseConfig(
        backend='sqlite',
        file_path=db_path
    )
    return Mimizam(config, fingerprinter_config, matcher_config)


def create_mimizam_mysql(host: str, port: int, database: str, 
                        username: str, password: str, 
                        matcher_config: Optional[Dict[str, Any]] = None,
                        **fingerprinter_config) -> Mimizam:
    """
    MySQLバックエンドを使用するMimizamインスタンスを簡単に作成
    
    Args:
        host: MySQLサーバーのホスト
        port: MySQLサーバーのポート
        database: データベース名
        username: ユーザー名
        password: パスワード
        matcher_config: FingerprintMatcherの設定パラメータ
        **fingerprinter_config: AudioFingerprinterの設定パラメータ
        
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    """
    config = DatabaseConfig(
        backend='mysql',
        host=host,
        port=port,
        database=database,
        username=username,
        password=password
    )
    return Mimizam(config, fingerprinter_config, matcher_config)


def create_mimizam_postgresql(host: str, port: int, database: str, 
                             username: str, password: str, 
                             matcher_config: Optional[Dict[str, Any]] = None,
                             **fingerprinter_config) -> Mimizam:
    """
    PostgreSQLバックエンドを使用するMimizamインスタンスを簡単に作成
    
    Args:
        host: PostgreSQLサーバーのホスト
        port: PostgreSQLサーバーのポート
        database: データベース名
        username: ユーザー名
        password: パスワード
        matcher_config: FingerprintMatcherの設定パラメータ
        **fingerprinter_config: AudioFingerprinterの設定パラメータ
        
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    """
    config = DatabaseConfig(
        backend='postgresql',
        host=host,
        port=port,
        database=database,
        username=username,
        password=password
    )
    return Mimizam(config, fingerprinter_config, matcher_config)


def create_mimizam_elasticsearch(host: str, port: int, 
                                index_name: str = "mimizam_songs",
                                matcher_config: Optional[Dict[str, Any]] = None,
                                **fingerprinter_config) -> Mimizam:
    """
    Elasticsearchバックエンドを使用するMimizamインスタンスを簡単に作成
    
    Args:
        host: Elasticsearchサーバーのホスト
        port: Elasticsearchサーバーのポート
        index_name: インデックス名
        matcher_config: FingerprintMatcherの設定パラメータ
        **fingerprinter_config: AudioFingerprinterの設定パラメータ
        
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    """
    config = DatabaseConfig(
        backend='elasticsearch',
        host=host,
        port=port,
        index_name=index_name,
        verify_certs=False
    )
    return Mimizam(config, fingerprinter_config, matcher_config)
