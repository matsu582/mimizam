"""
Mimizam - 音声・映像指紋システム

AudioFingerprinter、FingerprintDatabase、FingerprintMatcherを統合し、
音楽の追加、検索、管理機能を提供する高レベルAPIを提供。
VideoFingerprinterによる映像指紋機能も統合。
"""

import os
import uuid
import math
import shutil
import logging
import tempfile
import subprocess
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
        if not hasattr(self, '_video_config'):
            self._video_config = None

    def configure_video(
        self,
        scene_eval_fps: Optional[float] = None,
        profile_frames: Optional[bool] = None,
    ) -> None:
        """映像指紋の実行時設定を行う

        環境変数ではなく VideoFingerprintConfig のフィールドとして
        渡す。VideoFingerprinter 生成前・生成後のどちらでも呼べる。

        Args:
            scene_eval_fps: シーン検出の評価fps（Noneで変更なし）
            profile_frames: 処理時間内訳のログ出力（Noneで変更なし）
        """
        from .video_fingerprinter import VideoFingerprintConfig
        self._ensure_video_system()
        if self._video_config is None:
            self._video_config = VideoFingerprintConfig()
        if scene_eval_fps is not None:
            self._video_config.scene_eval_fps = scene_eval_fps
        if profile_frames is not None:
            self._video_config.profile_frames = profile_frames
        # 既に生成済みなら即反映（全クラスでconfigを共有）
        vfp = self._video_fingerprinter
        if vfp is not None:
            vfp.config.scene_eval_fps = self._video_config.scene_eval_fps
            vfp.config.profile_frames = self._video_config.profile_frames
            vfp.frame_selector.config = vfp.config
            vfp.encoder.config.scene_eval_fps = vfp.config.scene_eval_fps
            vfp.encoder.config.profile_frames = vfp.config.profile_frames

    def _get_video_fingerprinter(self):
        """映像指紋生成器を取得（遅延インポート）"""
        self._ensure_video_system()
        if self._video_fingerprinter is None:
            from .video_fingerprinter import VideoFingerprinter
            self._video_fingerprinter = VideoFingerprinter(
                config=self._video_config
            )
        return self._video_fingerprinter

    def _get_video_db(
        self,
        db_path: Optional[str] = None,
        config: Optional[DatabaseConfig] = None,
    ):
        """映像指紋DBを取得（遅延インポート、音声と同じバックエンドを使用）"""
        self._ensure_video_system()
        if self._video_db is None:
            from .video_database import VideoFingerprintDatabase
            if config is not None:
                self._video_db = VideoFingerprintDatabase(config=config)
            elif hasattr(self.database, 'config') and self.database.config:
                audio_cfg = self.database.config
                if audio_cfg.backend == 'sqlite':
                    if db_path is None:
                        base_dir = os.path.dirname(
                            audio_cfg.file_path or ""
                        )
                        db_path = os.path.join(
                            base_dir, "video_fingerprints.db"
                        ) if base_dir else "video_fingerprints.db"
                    video_cfg = DatabaseConfig(
                        backend='sqlite', file_path=db_path,
                    )
                else:
                    video_cfg = DatabaseConfig(
                        backend=audio_cfg.backend,
                        host=audio_cfg.host,
                        port=audio_cfg.port,
                        database=audio_cfg.database,
                        username=audio_cfg.username,
                        password=audio_cfg.password,
                        file_path=audio_cfg.file_path,
                        index_name=audio_cfg.index_name,
                        ca_certs=audio_cfg.ca_certs,
                        verify_certs=audio_cfg.verify_certs,
                        pool_size=audio_cfg.pool_size,
                        pool_timeout=audio_cfg.pool_timeout,
                    )
                self._video_db = VideoFingerprintDatabase(config=video_cfg)
            else:
                path = db_path or "video_fingerprints.db"
                self._video_db = VideoFingerprintDatabase(db_path=path)
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
            vdb.add_frame_fingerprints(
                video_id, fp.frame_fingerprints
            )

            # AKAZE記述子を保存（指紋再生成用）
            if fp.raw_descriptors:
                vdb.add_frame_descriptors(video_id, fp.raw_descriptors)

            self.logger.info(
                f"映像追加成功: {video_id} - {title}"
            )
            return video_id

        except FileNotFoundError:
            raise
        except Exception as exc:
            self.logger.error(f"映像追加エラー: {exc}")
            return None

    @staticmethod
    def _effective_video_score(
        frame_similarity: float,
        match_details: Dict[str, Any],
        votes: int,
        floor: float = 0.2,
    ) -> float:
        """被覆率・票数を反映した実効的な映像スコアを算出する

        frame_similarity（最良フレームのピーク類似度）だけでは、ごく僅かな
        フレームが偶発的に高一致した候補（例: 4/84フレーム）が高評価に
        なってしまう。クエリのどれだけが一致したかを表す被覆率(match_ratio)と
        ANN得票率を反映し、薄い偶発一致を減点する。

        strength = 0.5 * 被覆率 + 0.5 * 得票率  (いずれも0..1に正規化)
        実効スコア = frame_similarity * (floor + (1 - floor) * strength)
        """
        total = match_details.get("total_frames", 0) or 0
        coverage = match_details.get("match_ratio", 0.0) or 0.0
        vote_ratio = min(1.0, votes / total) if total > 0 else 0.0
        strength = 0.5 * coverage + 0.5 * vote_ratio
        return frame_similarity * (floor + (1.0 - floor) * strength)

    def search_video(
        self,
        query_file_path: str,
        top_k: int = 5,
        use_frame_matching: bool = True,
        detect_pip: bool = True,
        video_db_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        映像ファイルでデータベースを検索

        2段階検索:
          1. フレーム指紋のANN近傍投票で候補映像を絞り込み
          2. フレーム単位指紋で精密照合（時間整合区間を確認）
          3. PiP矩形検出 → 矩形内指紋でDB検索（PiP対策）

        部分クリップでも該当フレームがANNで直接引けるため、
        25分全編に対する数分クリップの検索でも取りこぼしにくい。

        Args:
            query_file_path: 検索対象の映像ファイルパス
            top_k: 返す結果の最大数
            use_frame_matching: フレーム単位マッチングで精密照合するか
            detect_pip: PiP矩形検出を行うか
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

            # Step 1: フレーム指紋のANN近傍投票で候補絞り込み
            candidates = vdb.search_frame_candidates(
                fp.frame_fingerprints, top_k=top_k * 2
            )

            if not use_frame_matching or not candidates:
                results = candidates[:top_k]
            else:
                # Step 2: フレーム単位マッチングで精密照合
                candidate_ids = [c["video_id"] for c in candidates]
                frame_results = vdb.search_video_with_frame_matching(
                    fp.frame_fingerprints, candidate_ids
                )

                # 結果を統合
                frame_map = {
                    r["video_id"]: r for r in frame_results
                }
                cand_map = {c["video_id"]: c for c in candidates}
                # フレームマッチで時間的一貫性が確認された結果のみ採用
                results = []
                for vid, fm in frame_map.items():
                    cand = cand_map.get(vid, {})
                    votes = cand.get("votes", 0)
                    md = fm.get("match_details", {})
                    effective = self._effective_video_score(
                        fm["frame_similarity"], md, votes
                    )
                    entry = {
                        "video_id": vid,
                        "video_similarity": cand.get("similarity", 0.0),
                        "video": cand.get("video"),
                        "vote_count": votes,
                        "frame_similarity": fm["frame_similarity"],
                        # ランキング/統合に使う実効スコアは被覆率・票数を反映
                        "similarity": effective,
                    }
                    if "match_details" in fm:
                        entry["match_details"] = fm[
                            "match_details"
                        ]
                    results.append(entry)

                results.sort(
                    key=lambda r: r["similarity"], reverse=True
                )
                results = results[:top_k]

            # Step 3: PiP矩形検出 → 矩形内指紋でDB検索
            if detect_pip:
                pip_results = self._search_pip_regions(
                    query_file_path, vfp, vdb, top_k
                )
                if pip_results:
                    results = self._merge_pip_results(
                        results, pip_results, top_k
                    )

            return results

        except FileNotFoundError:
            raise
        except Exception as exc:
            self.logger.error(f"映像検索エラー: {exc}")
            return []

    def _extract_audio_to_wav(self, video_path: str, out_dir: str) -> str:
        """ffmpegで動画から音声を22050Hzモノラルwavとして抽出する

        映像検索と組み合わせる統合検索で音声トラックを得るために使う。
        登録時（movie_fingerprinter）と同じ抽出条件に揃える。
        """
        out_path = os.path.join(
            out_dir, f"{Path(video_path).stem}.wav"
        )
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "22050", "-ac", "1",
            "-y", out_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out_path

    @staticmethod
    def _movie_position_diverges(
        audio: Optional[Dict[str, Any]],
        visual: Optional[Dict[str, Any]],
        tolerance: float,
    ) -> bool:
        """同一動画内で音声位置と映像位置が乖離しているか判定する

        音声のDB区間は time_offset（=query_time - db_time の代表値）と
        クリップ長から推定し、映像の最大整列区間(db_start..db_end)と比較する。
        両区間の隙間が tolerance を超える場合は乖離とみなす。
        判定に必要なデータが揃わない場合は False（乖離なし扱い＝除外しない）。
        """
        if not audio or not visual:
            return False
        offset = audio.get("time_offset")
        md = visual.get("match_details") or {}
        regions = md.get("regions") or []
        if offset is None or not regions:
            return False

        clip_len = md.get("query_duration", 0.0) or 0.0
        audio_db_start = -offset
        audio_db_end = audio_db_start + clip_len
        a_lo = min(audio_db_start, audio_db_end)
        a_hi = max(audio_db_start, audio_db_end)

        # 映像はフレーム数最多の整列区間を代表とする
        region = max(regions, key=lambda r: r.get("frame_count", 0))
        v_lo = region.get("db_start", 0.0)
        v_hi = region.get("db_end", 0.0)

        # 区間同士の隙間（重なれば0）
        gap = max(0.0, v_lo - a_hi, a_lo - v_hi)
        return gap > tolerance

    def _merge_movie_results(
        self,
        audio_results: List[Dict[str, Any]],
        visual_results: List[Dict[str, Any]],
        divergence_tolerance: float,
    ) -> List[Dict[str, Any]]:
        """音声検索と映像検索の結果をIDで結合し統合スコアを算出する

        同一UUIDで登録されている場合、song_id と video_id が一致する。
        両方一致（かつ位置が乖離しない）なら幾何平均で持ち上げ、片方のみ
        または位置乖離ありなら高い方のモダリティを 0.8 掛けで評価する。

        統合スコアの式:
            両モダリティ一致・非乖離: √(音声信頼度 × 実効映像スコア)
            片方のみ / 位置乖離あり:   max(音声信頼度, 実効映像スコア) × 0.8
        """
        audio_map: Dict[str, Dict[str, Any]] = {}
        for match in audio_results:
            song = match.get("song")
            if song is not None:
                sid = song.id if hasattr(song, "id") else str(song)
                audio_map[sid] = match

        visual_map: Dict[str, Dict[str, Any]] = {}
        for result in visual_results:
            visual_map[result.get("video_id", "")] = result

        merged: List[Dict[str, Any]] = []
        for item_id in set(audio_map) | set(visual_map):
            audio = audio_map.get(item_id)
            visual = visual_map.get(item_id)

            a_score = 0.0
            v_score = 0.0
            entry: Dict[str, Any] = {"id": item_id}

            if audio:
                a_score = audio.get("confidence", 0.0)
                entry["audio_confidence"] = a_score
                entry["audio_match"] = audio

            if visual:
                v_score = visual.get("similarity", 0.0)
                entry["visual_similarity"] = v_score
                entry["visual_match"] = visual

            diverged = self._movie_position_diverges(
                audio, visual, divergence_tolerance
            )
            entry["position_diverged"] = diverged

            if a_score > 0 and v_score > 0 and not diverged:
                entry["combined_score"] = math.sqrt(a_score * v_score)
            else:
                entry["combined_score"] = max(a_score, v_score) * 0.8

            song = audio.get("song") if audio else None
            video = visual.get("video") if visual else None
            entry["title"] = (
                getattr(song, "title", None)
                or getattr(video, "title", None)
                or "不明"
            )
            entry["file_path"] = (
                getattr(video, "file_path", None)
                or getattr(song, "file_path", None)
                or "不明"
            )

            merged.append(entry)

        merged.sort(key=lambda x: x["combined_score"], reverse=True)
        return merged

    def search_movie(
        self,
        query_file_path: str,
        top_k: int = 5,
        use_frame_matching: bool = True,
        detect_pip: bool = False,
        video_db_path: Optional[str] = None,
        skip_audio: bool = False,
        skip_visual: bool = False,
        divergence_tolerance: float = 30.0,
        min_combined_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """動画を音声指紋と映像指紋の両方で検索し、結果を統合する

        動画から音声を抽出して音声検索し、同じ動画で映像検索した結果を
        同一UUID（song_id / video_id）で結合する。両モダリティが一致し
        位置が乖離しなければ幾何平均で持ち上げ、片方のみ・位置乖離ありなら
        高い方のモダリティを 0.8 掛けで評価する（統合スコアの詳細は
        docs/video_fingerprint_spec.md 3.3 の実効映像スコアも参照）。

        Args:
            query_file_path: 検索対象の動画ファイルパス
            top_k: 返す結果の最大数
            use_frame_matching: 映像でフレーム単位精密照合を行うか
            detect_pip: PiP矩形検出を行うか
            video_db_path: 映像DBファイルパス
            skip_audio: 音声検索をスキップする
            skip_visual: 映像検索をスキップする
            divergence_tolerance: 音声DB区間と映像DB区間の乖離許容（秒）
            min_combined_score: これ未満の統合スコアを除外する閾値

        Returns:
            統合検索結果のリスト（combined_score 降順）。各要素は id / title /
            file_path / combined_score / position_diverged を持ち、該当時に
            audio_confidence / audio_match / visual_similarity / visual_match を含む。
        """
        if not os.path.exists(query_file_path):
            raise FileNotFoundError(
                f"動画ファイルが見つかりません: {query_file_path}"
            )

        audio_results: List[Dict[str, Any]] = []
        visual_results: List[Dict[str, Any]] = []

        if not skip_audio:
            temp_dir = tempfile.mkdtemp(prefix="movie_search_")
            try:
                audio_path = self._extract_audio_to_wav(
                    query_file_path, temp_dir
                )
                raw_matches = self.search_song(
                    audio_path, min_confidence=0.0, top_k=top_k * 4
                )
                for match in raw_matches:
                    details = match.get("details", {})
                    audio_results.append({
                        "song": match["song"],
                        "confidence": match["confidence"],
                        "match_count": match.get("match_count", 0),
                        "time_offset": details.get("time_offset", 0),
                        "time_scale": details.get("time_scale", 1.0),
                        "freq_scale": details.get("freq_scale", 1.0),
                        "detailed_info": details.get("detailed_info"),
                    })
            except Exception as exc:
                self.logger.warning(f"統合検索の音声検索エラー: {exc}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        if not skip_visual:
            try:
                visual_results = self.search_video(
                    query_file_path=query_file_path,
                    top_k=top_k * 4,
                    use_frame_matching=use_frame_matching,
                    detect_pip=detect_pip,
                    video_db_path=video_db_path,
                )
            except Exception as exc:
                self.logger.warning(f"統合検索の映像検索エラー: {exc}")

        merged = self._merge_movie_results(
            audio_results, visual_results, divergence_tolerance
        )
        if min_combined_score > 0.0:
            merged = [
                m for m in merged
                if m["combined_score"] >= min_combined_score
            ]
        return merged[:top_k]

    def _search_pip_regions(
        self, query_path, vfp, vdb, top_k
    ) -> List[Dict[str, Any]]:
        """PiP矩形内の指紋でDB検索"""
        try:
            pip_fps = vfp.fingerprint_pip_regions(query_path)
            if not pip_fps:
                return []

            pip_results = []
            for region, pip_fp in pip_fps:
                matches = vdb.search_frame_candidates(
                    pip_fp.frame_fingerprints, top_k=top_k
                )
                for m in matches:
                    m["pip_region"] = {
                        "x": region.x, "y": region.y,
                        "w": region.w, "h": region.h,
                        "pip_score": region.pip_score,
                    }
                    m["pip_similarity"] = m["similarity"]
                pip_results.extend(matches)

            return pip_results
        except Exception as exc:
            self.logger.warning(f"PiP検索エラー: {exc}")
            return []

    @staticmethod
    def _merge_pip_results(
        base_results, pip_results, top_k
    ) -> List[Dict[str, Any]]:
        """通常検索結果とPiP検索結果を統合"""
        existing_ids = {r["video_id"] for r in base_results}
        merged = list(base_results)

        for pr in pip_results:
            vid = pr["video_id"]
            if vid in existing_ids:
                for r in merged:
                    if r["video_id"] == vid:
                        pip_sim = pr.get("pip_similarity", 0)
                        if pip_sim > r.get("similarity", 0):
                            r["similarity"] = pip_sim
                            r["pip_region"] = pr.get("pip_region")
                            r["pip_similarity"] = pip_sim
                        break
            else:
                pr["similarity"] = pr.get("pip_similarity", 0)
                merged.append(pr)
                existing_ids.add(vid)

        merged.sort(
            key=lambda r: r.get("similarity", 0), reverse=True
        )
        return merged[:top_k]

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

    def rebuild_video_fingerprints(
        self,
        video_db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DB内の全映像指紋を保存済み記述子から再生成

        モデル更新後に元映像なしで指紋を再計算する。
        事前にload_video_model()で新モデルを読み込んでおくこと。

        Args:
            video_db_path: 映像DBファイルパス

        Returns:
            再生成統計: {"total": 件数, "success": 成功数, "skip": スキップ数}
        """
        vfp = self._get_video_fingerprinter()
        vdb = self._get_video_db(video_db_path)

        if not vfp.is_trained:
            raise RuntimeError(
                "モデルが未学習です。"
                "先にload_video_model()を呼んでください"
            )

        all_desc = vdb.get_all_frame_descriptors()
        stats = {"total": len(all_desc), "success": 0, "skip": 0}

        for vid_id, frame_descs in all_desc.items():
            if not frame_descs:
                stats["skip"] += 1
                self.logger.warning(
                    f"記述子なし（スキップ）: {vid_id}"
                )
                continue

            fp = vfp.rebuild_from_descriptors(frame_descs)
            if fp is None:
                stats["skip"] += 1
                continue

            vdb.add_frame_fingerprints(
                vid_id, fp.frame_fingerprints
            )
            stats["success"] += 1
            self.logger.info(
                f"指紋再生成: {vid_id} "
                f"({fp.frame_count}フレーム)"
            )

        self.logger.info(
            f"指紋再生成完了: "
            f"{stats['success']}/{stats['total']}件成功"
        )
        return stats

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


def create_mimizam_mariadb(host: str, port: int, database: str,
                           username: str, password: str,
                           matcher_config: Optional[Dict[str, Any]] = None,
                           **fingerprinter_config) -> Mimizam:
    """
    MariaDBバックエンドを使用するMimizamインスタンスを簡単に作成

    MariaDB 11.7+ ではフレーム指紋検索にネイティブベクトルANN
    （VECTOR型 + VECTOR INDEX + VEC_DISTANCE_COSINE）が用いられる。

    Args:
        host: MariaDBサーバーのホスト
        port: MariaDBサーバーのポート
        database: データベース名
        username: ユーザー名
        password: パスワード
        matcher_config: FingerprintMatcherの設定パラメータ
        **fingerprinter_config: AudioFingerprinterの設定パラメータ

    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    """
    config = DatabaseConfig(
        backend='mariadb',
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
