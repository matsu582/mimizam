"""
音声指紋のデータベース管理
複数のデータベースバックエンド（SQLite、MySQL、PostgreSQL、Elasticsearch）をサポート
"""

from typing import List, Optional, Tuple, Dict, Any
import logging
import numpy as np
from scipy import stats
from pathlib import Path

from .database_base import Fingerprint
from .database_backends import (
    DatabaseBackend, DatabaseConfig, Song, 
    create_database_backend
)


class FingerprintDatabase:
    """音声フィンガープリントのデータベース管理クラス（複数バックエンド対応）"""
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        フィンガープリントデータベースを初期化
        
        Args:
            config: データベース設定。Noneの場合はデフォルトのSQLite設定を使用
        """
        self.logger = logging.getLogger(__name__)
        
        # デフォルト設定（SQLite）
        if config is None:
            config = DatabaseConfig(
                backend='sqlite',
                file_path='fingerprints.db'
            )
        
        self.config = config
        self.backend = create_database_backend(config)
        
        # データベースに接続して初期化
        if not self.backend.connect():
            raise RuntimeError(f"Failed to connect to database: {config.backend}")
        
        if not self.backend.create_tables():
            raise RuntimeError("Failed to create database tables")
    
    def __del__(self):
        """デストラクタ：データベース接続を確実に切断"""
        try:
            if hasattr(self, 'backend') and self.backend:
                self.backend.disconnect()
        except Exception:
            pass  # デストラクタでの例外は無視
    
    def disconnect(self) -> None:
        """データベース接続を明示的に切断"""
        if self.backend:
            self.backend.disconnect()
    
    def add_song(self, song: Song) -> bool:
        """
        データベースに楽曲を追加
        
        Args:
            song: 追加する楽曲オブジェクト
            
        Returns:
            成功時True、失敗時False
        """
        success = self.backend.add_song(song)
        if success:
            self.logger.info(f"Song added: {song.title} by {song.artist}")
        return success
    
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """
        楽曲のフィンガープリントをデータベースに追加
        
        Args:
            song_id: 楽曲識別子
            fingerprints: 追加するフィンガープリントのリスト
            
        Returns:
            成功時True、失敗時False
        """
        success = self.backend.add_fingerprints(song_id, fingerprints)
        if success:
            self.logger.info(f"Added {len(fingerprints)} fingerprints to song {song_id}")
        return success
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """
        データベース内の一致するフィンガープリントを検索
        
        Args:
            query_fingerprints: クエリフィンガープリントのリスト
            
        Returns:
            song_idと(query_time_offset, db_time_offset)タプルのリストのマッピング辞書
        """
        return self.backend.search_fingerprints(query_fingerprints)
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """
        IDで楽曲情報を取得
        
        Args:
            song_id: 楽曲識別子
            
        Returns:
            見つかった場合は楽曲オブジェクト、そうでなければNone
        """
        return self.backend.get_song(song_id)
    
    def list_songs(self) -> List[Song]:
        """
        データベース内の全楽曲をリスト表示
        
        Returns:
            楽曲オブジェクトのリスト
        """
        return self.backend.list_songs()
    
    def get_database_stats(self) -> Dict[str, int]:
        """
        データベース統計を取得
        
        Returns:
            データベース統計の辞書
        """
        return self.backend.get_database_stats()
    
    def delete_song(self, song_id: str) -> bool:
        """
        楽曲とそのフィンガープリントをデータベースから削除
        
        Args:
            song_id: 楽曲識別子
            
        Returns:
            成功時True、失敗時False
        """
        success = self.backend.delete_song(song_id)
        if success:
            self.logger.info(f"Song {song_id} deleted")
        return success
    
    def get_fingerprints_by_song(self, song_id: str) -> List[Fingerprint]:
        """
        指定した楽曲のフィンガープリントを取得
        
        Args:
            song_id: 楽曲識別子
            
        Returns:
            フィンガープリントのリスト
        """
        return self.backend.get_fingerprints_by_song(song_id)


class FingerprintMatcher:
    """速度とピッチ変化をサポートするクエリ音声とフィンガープリントデータベースのマッチャー"""
    
    def __init__(self, database: FingerprintDatabase):
        """
        フィンガープリントマッチャーを初期化
        
        Args:
            database: FingerprintDatabaseインスタンス
        """
        self.database = database
        self.logger = logging.getLogger(__name__)
        self.min_confidence = 0.1
        self.max_results = 10
        
        # スコアリング方式の選択
        self.scoring_method = "hybrid"  # "hybrid", "histogram", "detailed"
        
        # 速度/ピッチ変化の許容範囲
        self.freq_scale_factors = [0.9, 0.95, 1.0, 1.05, 1.1]  # ±10%のピッチ変化
        
        # スケール係数の定義（用途別）
        self.detailed_scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]  # 包括的（0.5倍-2倍）
        self.histogram_scales = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.5]  # 細かい刻み（ヒストグラム方式）
        self.hybrid_fast_scales = [0.8, 0.9, 1.0, 1.1, 1.2, 1.5]  # 高速候補抽出用（限定的）
        
        # 後方互換性のため、detailed_scalesをtime_scale_factorsとしても参照可能
        self.time_scale_factors = self.detailed_scales
        
        self.time_tolerance = 0.3  # 秒 - より広い速度範囲のため許容度を増加
        self.freq_tolerance = 100  # Hz - 周波数許容度を増加
    
    def set_scoring_method(self, method: str) -> None:
        """
        スコアリング方式を設定
        
        Args:
            method: "hybrid" (2段階), "histogram" (ヒストグラムのみ), "detailed" (多面的のみ)
        """
        if method not in ["hybrid", "histogram", "detailed"]:
            raise ValueError("method must be 'hybrid', 'histogram', or 'detailed'")
        self.scoring_method = method
        self.logger.info(f"Scoring method set to {method}")
    
    def find_matches(self, query_fingerprints: List[Fingerprint], 
                    min_matches: int = 5, top_k: int = 10, 
                    include_details: bool = True) -> List[Dict[str, Any]]:
        """
        選択されたスコアリング方式でクエリフィンガープリントに一致する楽曲を検索
        
        Args:
            query_fingerprints: クエリフィンガープリントのリスト
            min_matches: 必要な最小フィンガープリント一致数
            top_k: ヒストグラム段階で絞り込む候補数（hybrid方式のみ）
            include_details: 詳細なマッチ情報を含めるかどうか（デフォルト: True）
            
        Returns:
            楽曲情報と信頼度スコアを含む一致辞書のリスト
            song_info と詳細なマッチ情報を含む
        """
        if not query_fingerprints:
            return []
        
        # スコアリング方式に応じた最小一致数の調整
        adjusted_min_matches = min_matches
        if self.scoring_method in ["histogram", "hybrid"]:
            adjusted_min_matches = max(5, min_matches // 2)  # ヒストグラム方式では5以上を維持

        import time
        self.logger.info("[BENCHMARK] start benchmark")
        t0 = time.perf_counter()

        if self.scoring_method == "hybrid":
            results = self._find_matches_hybrid_new(query_fingerprints, adjusted_min_matches, top_k)
        elif self.scoring_method == "histogram":
            results = self._find_matches_histogram(query_fingerprints, adjusted_min_matches, top_k)
        elif self.scoring_method == "detailed":
            results = self._find_matches_detailed(query_fingerprints, min_matches, top_k)
        else:
            raise ValueError(f"Unknown scoring method: {self.scoring_method}")
        t1 = time.perf_counter()
        self.logger.info(f"[BENCHMARK] {self.scoring_method}: {t1-t0:.4f}s")
        
        # song_info と詳細情報を追加
        if results:
            for result in results:
                song_id = result['song_id']
                
                # song_info を追加
                song_info = self.get_song_info(song_id)
                result['song_info'] = song_info
                
                # 詳細情報を追加
                if include_details:
                    detailed_info = self.get_detailed_match_info(query_fingerprints, song_id)
                    result['detailed_info'] = detailed_info
        
        return results
    
    def _find_matches_hybrid(self, query_fingerprints: List[Fingerprint], 
                           min_matches: int, top_k: int) -> List[Dict[str, Any]]:
        """2段階判定: ヒストグラム分析で候補絞り→多面的スコアリング精査"""
        
        # 1段階目: 複数のスケールでヒストグラム候補抽出
        candidate_scores = {}
        
        # 高速化のため限定的なスケールで候補を抽出
        for time_scale in self.hybrid_fast_scales:
            scaled_fingerprints = self._scale_fingerprints(query_fingerprints, time_scale, 1.0)
            matches = self.database.search_fingerprints(scaled_fingerprints)
            
            for song_id, match_pairs in matches.items():
                if len(match_pairs) >= min_matches:
                    # ヒストグラム信頼度計算
                    histogram_confidence = self._calculate_hybrid_histogram_confidence(
                        match_pairs, time_scale
                    )
                    
                    # 既存の候補よりも良いスコアの場合のみ更新
                    if (song_id not in candidate_scores or 
                        histogram_confidence > candidate_scores[song_id][0]):
                        candidate_scores[song_id] = (histogram_confidence, time_scale, match_pairs)
        
        # 上位候補を抽出（histogram信頼度順）
        top_candidates = sorted(candidate_scores.items(), 
                              key=lambda x: x[1][0], reverse=True)[:top_k]
        
        # 2段階目: 多面的スコアリングで精査（改善版）
        best_results = {}
        for song_id, (hist_confidence, time_scale, match_pairs) in top_candidates:
            # 重要: match_pairsではなく、新しくスケール探索を実行
            song_best_result = {}
            
            # Detailed方式と同じ包括的探索
            for test_time_scale in self.time_scale_factors:
                for test_freq_scale in self.freq_scale_factors:
                    # 新しくスケール調整してフィンガープリント検索
                    scaled_fingerprints = self._scale_fingerprints(
                        query_fingerprints, test_time_scale, test_freq_scale
                    )
                    test_matches = self.database.search_fingerprints(scaled_fingerprints)
                    
                    if song_id in test_matches and len(test_matches[song_id]) >= min_matches:
                        test_confidence = self._calculate_confidence_score_with_scaling(
                            test_matches[song_id], test_time_scale, test_freq_scale
                        )
                        
                        # より良い結果の場合のみ更新
                        if (not song_best_result or 
                            test_confidence > song_best_result['confidence']):
                            
                            song_best_result = {
                                'confidence': test_confidence,
                                'match_pairs': test_matches[song_id],
                                'time_scale': test_time_scale,
                                'freq_scale': test_freq_scale
                            }
            
            # 詳細探索結果を取得
            if song_best_result:
                best_detailed_confidence = song_best_result['confidence']
                best_detailed_scale = song_best_result['time_scale']
                best_detailed_freq_scale = song_best_result['freq_scale']
                best_match_pairs = song_best_result['match_pairs']
            else:
                # 詳細探索で結果がない場合はhistogram結果を使用
                best_detailed_confidence = 0.0
                best_detailed_scale = time_scale
                best_detailed_freq_scale = 1.0
                best_match_pairs = match_pairs
            
            # 詳細スケール探索の結果を最終信頼度として使用
            final_confidence = best_detailed_confidence
            
            if final_confidence >= self.min_confidence:
                time_offset = self._calculate_time_offset(best_match_pairs)
                
                # 拡張指標を計算
                alignment_ratio = self._calculate_alignment_ratio(best_match_pairs)
                match_density = self._calculate_match_density(best_match_pairs)
                
                best_results[song_id] = {
                    'song_id': song_id,
                    'confidence': final_confidence,
                    'match_count': len(best_match_pairs),
                    'match_pairs': best_match_pairs,  # ソート時に使用
                    'time_offset': time_offset,
                    'time_scale': best_detailed_scale,  # 最適化されたスケールを使用
                    'freq_scale': best_detailed_freq_scale,  # 最適化された周波数スケールを使用
                    'alignment_ratio': alignment_ratio,  # 新指標
                    'match_density': match_density,      # 新指標
                    'histogram_confidence': hist_confidence,
                    'detailed_confidence': best_detailed_confidence
                }
        
        return self._sort_and_limit_results(best_results)

    def _find_matches_hybrid_new(self, query_fingerprints: List[Fingerprint], min_matches: int, top_k: int) -> List[Dict[str, Any]]:
        """
        高速化版hybrid: 1段階目で全スケール・ピッチのマッチペアを集約し、2段階目はDBアクセスせずグルーピング＆スコア計算のみ
        """
        import time
        t_all = time.perf_counter()
        # 1段階目: 全スケール・ピッチでfingerprintを生成し、DB検索
        t0 = time.perf_counter()
        all_match_info = {}  # song_id -> List[(query_time, db_time, time_scale, freq_scale)]
        db_query_count = 0
        for time_scale in self.hybrid_fast_scales:
            for freq_scale in self.freq_scale_factors:
                t_db0 = time.perf_counter()
                scaled_fingerprints = self._scale_fingerprints(query_fingerprints, time_scale, freq_scale)
                matches = self.database.search_fingerprints(scaled_fingerprints)
                t_db1 = time.perf_counter()
                db_query_count += 1
                self.logger.debug(f"[BENCHMARK-HYBRID-NEW] DB search (scale={time_scale}, freq={freq_scale}): {t_db1-t_db0:.4f}s, matches: {sum(len(p) for p in matches.values())}")
                for song_id, match_pairs in matches.items():
                    if song_id not in all_match_info:
                        all_match_info[song_id] = []
                    # 各マッチペアにスケール情報を付与
                    for q_time, db_time in match_pairs:
                        all_match_info[song_id].append((q_time, db_time, time_scale, freq_scale))
        t1 = time.perf_counter()
        self.logger.debug(f"[BENCHMARK-HYBRID-NEW] 1st stage (all DB search): {t1-t0:.4f}s, total DB queries: {db_query_count}")

        # 2段階目: song_idごとにスケール・ピッチでグループ化し、最良スコアを採用
        t2 = time.perf_counter()
        best_results = {}
        for song_id, match_info_list in all_match_info.items():
            # スケール・ピッチごとにグループ化
            group_dict = {}
            for q_time, db_time, t_scale, f_scale in match_info_list:
                key = (t_scale, f_scale)
                group_dict.setdefault(key, []).append((q_time, db_time))
            # 各グループでスコア計算し、最良のものを採用
            best_group = None
            best_conf = 0.0
            best_group_info = None
            for (t_scale, f_scale), pairs in group_dict.items():
                if len(pairs) < min_matches:
                    continue
                t_score0 = time.perf_counter()
                conf = self._calculate_confidence_score_with_scaling(pairs, t_scale, f_scale)
                t_score1 = time.perf_counter()
                self.logger.debug(f"[BENCHMARK-HYBRID-NEW] Score calc (song={song_id}, scale={t_scale}, freq={f_scale}, n={len(pairs)}): {t_score1-t_score0:.4f}s")
                if conf > best_conf:
                    best_conf = conf
                    best_group = pairs
                    best_group_info = (t_scale, f_scale)
            if best_group and best_conf >= self.min_confidence:
                time_offset = self._calculate_time_offset(best_group)
                alignment_ratio = self._calculate_alignment_ratio(best_group)
                match_density = self._calculate_match_density(best_group)
                best_results[song_id] = {
                    'song_id': song_id,
                    'confidence': best_conf,
                    'match_count': len(best_group),
                    'match_pairs': best_group,
                    'time_offset': time_offset,
                    'time_scale': best_group_info[0],
                    'freq_scale': best_group_info[1],
                    'alignment_ratio': alignment_ratio,
                    'match_density': match_density
                }
        t3 = time.perf_counter()
        self.logger.debug(f"[BENCHMARK-HYBRID-NEW] 2nd stage (grouping & scoring): {t3-t2:.4f}s")
        results = self._sort_and_limit_results(best_results)[:top_k]
        t_all2 = time.perf_counter()
        self.logger.debug(f"[BENCHMARK-HYBRID-NEW] total: {t_all2-t_all:.4f}s")
        return results
    

    def _find_matches_histogram(self, query_fingerprints: List[Fingerprint], 
                              min_matches: int, top_k: int = 10) -> List[Dict[str, Any]]:
        """ヒストグラム方式のみ（スケール対応版）- 複数速度でDB検索"""
        
        # 複数のスケールでクエリフィンガープリントを検索
        all_results = {}
        
        for time_scale in self.histogram_scales:
            self._process_scale_for_histogram(
                query_fingerprints, time_scale, min_matches, all_results
            )
            
        self.logger.debug(f"Histogram method: found {len(all_results)} candidates")
        
        # 信頼度フィルタリング
        filtered_results = {k: v for k, v in all_results.items() 
                           if v['confidence'] >= self.min_confidence}
        
        self.logger.debug(f"Histogram method: {len(filtered_results)} items after confidence filter")
        
        # マルチクライテリアソートを適用
        return self._sort_and_limit_results(filtered_results)[:top_k]
    
    def _process_scale_for_histogram(self, query_fingerprints: List[Fingerprint],
                                   time_scale: float, min_matches: int,
                                   all_results: Dict[str, Dict[str, Any]]) -> None:
        """ヒストグラム方式で特定のスケールを処理"""
        
        scaled_fingerprints = self._scale_fingerprints(query_fingerprints, time_scale, 1.0)
        matches = self.database.search_fingerprints(scaled_fingerprints)
        
        self.logger.debug(f"Scale {time_scale}: {len(matches)} songs found, "
                         f"total matches: {sum(len(pairs) for pairs in matches.values())}")
        
        for song_id, match_pairs in matches.items():
            if len(match_pairs) < min_matches:
                continue
            
            self.logger.debug(f"Processing song {song_id} with {len(match_pairs)} matches at scale {time_scale}")
            
            self._process_histogram_for_song(
                match_pairs, time_scale, all_results, song_id
            )
    
    def _process_histogram_for_song(self, match_pairs: List[Tuple[float, float]],
                                      time_scale: float, all_results: Dict[str, Dict[str, Any]],
                                      song_id: str) -> None:
        """ヒストグラム信頼度を計算して結果を更新"""
        
        # 時間差を計算（スケール調整済み）
        offsets = [(db_time - query_time)/time_scale for query_time, db_time in match_pairs]
        
        if len(offsets) < 5:  # ヒストグラム方式の最小閾値
            self.logger.debug(f"Song {song_id}: {len(offsets)} offsets < 5, skipping")
            return
        
        offsets = np.array(offsets)
        
        # ヒストグラム方式: 動的なビン幅計算（Freedman-Diaconis rule）
        q75, q25 = np.percentile(offsets, [75, 25])
        iqr = q75 - q25
        bin_width = 2 * iqr / (len(offsets) ** (1/3)) if iqr > 0 else 0.1
        bin_width = max(0.05, min(bin_width, 1.0))  # 0.05-1.0秒の範囲で制限
        
        # 適応的レンジ設定
        offset_range = max(10, np.std(offsets) * 4)
        offset_mean = np.mean(offsets)
        
        bins = int((2 * offset_range) / bin_width)
        bins = max(20, min(bins, 200))  # ビン数を制限
        
        hist, bin_edges = np.histogram(offsets, 
                                     bins=bins, 
                                     range=(offset_mean - offset_range, 
                                           offset_mean + offset_range))
        
        # ピーク検出とノイズ除去
        max_count = int(np.max(hist))
        max_bin_idx = int(np.argmax(hist))
        
        # ヒストグラム方式: 統計的有意性検査
        if max_count < 3:
            return
            
        # 周辺ビンとの比較でピークの明確さを評価
        peak_prominence = self._calculate_peak_prominence(hist, max_bin_idx)
        
        # 最適なオフセット計算（ピーク周辺の重心）
        offset = self._calculate_weighted_offset(hist, bin_edges, max_bin_idx)
        
        # ヒストグラム信頼度計算
        confidence = self._calculate_histogram_confidence(
            max_count, len(offsets), peak_prominence, time_scale
        )
        
        self.logger.debug(f"Song {song_id}: confidence={confidence:.3f}, max_count={max_count}, "
                         f"prominence={peak_prominence:.2f}, scale={time_scale}, offset={offset:.2f}")
        
        # より良いスコアの場合のみ更新
        if song_id not in all_results or confidence > all_results[song_id]['confidence']:
            # 拡張指標を計算
            alignment_ratio = self._calculate_alignment_ratio(match_pairs)
            match_density = self._calculate_match_density(match_pairs)
            
            all_results[song_id] = {
                'song_id': song_id,
                'confidence': confidence,
                'match_count': len(match_pairs),     # 実際のマッチ数を使用
                'histogram_peak': max_count,         # ヒストグラムピーク値は別途保存
                'match_pairs': match_pairs,          # ソート時に使用
                'time_offset': offset,
                'time_scale': time_scale,
                'freq_scale': 1.0,
                'alignment_ratio': alignment_ratio,  # 新指標
                'match_density': match_density,      # 新指標
                'peak_prominence': peak_prominence
            }
            self.logger.debug(f"Song {song_id}: Updated as best result")
    
    def _find_matches_detailed(self, query_fingerprints: List[Fingerprint], 
                             min_matches: int, top_k: int = 10) -> List[Dict[str, Any]]:
        """多面的スコアリングのみ（従来方式）"""
        best_results = self._find_scaled_matches(query_fingerprints, min_matches)
        return self._sort_and_limit_results(best_results)[:top_k]
    
    def _find_scaled_matches(self, query_fingerprints: List[Fingerprint], 
                           min_matches: int) -> Dict[str, Dict[str, Any]]:
        """異なるスケールでマッチを検索"""
        best_results = {}
        
        for time_scale in self.time_scale_factors:
            for freq_scale in self.freq_scale_factors:
                self._process_scale_combination(
                    query_fingerprints, time_scale, freq_scale, 
                    min_matches, best_results
                )
        
        return best_results
    
    def _process_scale_combination(self, query_fingerprints: List[Fingerprint],
                                 time_scale: float, freq_scale: float,
                                 min_matches: int, best_results: Dict[str, Dict[str, Any]], song_id: str = None):
        """
        特定のスケール組み合わせを処理
        
        song_idを指定した場合、その曲のみを対象にする
        """
        if song_id is not None:
            song_ids = [song_id]
        else:
            song_ids = [song.id for song in self.database.list_songs()]
        scaled_fingerprints = self._scale_fingerprints(query_fingerprints, time_scale, freq_scale)
        matches = self.database.search_fingerprints(scaled_fingerprints)
        for sid in song_ids:
            if sid not in matches:
                continue
            match_pairs = matches[sid]
            if len(match_pairs) < min_matches:
                continue
            confidence = self._calculate_confidence_score_with_scaling(
                match_pairs, time_scale, freq_scale
            )
            if confidence >= self.min_confidence:
                self._update_best_result(
                    best_results, sid, match_pairs, 
                    confidence, time_scale, freq_scale
                )
    
    def _update_best_result(self, best_results: Dict[str, Dict[str, Any]], 
                          song_id: str, match_pairs: List[Tuple[float, float]],
                          confidence: float, time_scale: float, freq_scale: float):
        """最良の結果を更新（拡張指標付き）"""
        if song_id not in best_results or confidence > best_results[song_id]['confidence']:
            time_offset = self._calculate_time_offset(match_pairs)
            
            # アライメント比率を計算（時間的整列の品質指標）
            alignment_ratio = self._calculate_alignment_ratio(match_pairs)
            
            # マッチ密度を計算（マッチ数 / 時間範囲）
            match_density = self._calculate_match_density(match_pairs)
            
            best_results[song_id] = {
                'song_id': song_id,
                'confidence': confidence,
                'match_count': len(match_pairs),
                'match_pairs': match_pairs,  # ソート時に使用
                'time_offset': time_offset,
                'time_scale': time_scale,
                'freq_scale': freq_scale,
                'alignment_ratio': alignment_ratio,  # 新指標
                'match_density': match_density       # 新指標
            }
    
    def _sort_and_limit_results(self, best_results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        結果を多面的にソートして制限
        
        ソート優先度:
        1. 信頼度 (confidence)
        2. マッチ数 (match_count or len(match_pairs))
        3. 時間的整列率 (alignment_ratio)
        4. 時間スケールの正確性 (1.0に近いほど良い)
        """
        results = list(best_results.values())
        
        # 多面的ソート
        results.sort(key=lambda x: (
            -x['confidence'],                                    # 信頼度（降順）
            -x.get('match_count', len(x.get('match_pairs', []))), # マッチ数（降順）
            -x.get('alignment_ratio', 0.0),                     # 時間的整列率（降順）
            abs(x.get('time_scale', 1.0) - 1.0)                 # 時間スケールの正確性（1.0に近いほど良い）
        ))
        
        return results[:self.max_results]
    
    def get_song_info(self, song_id: str) -> Dict[str, str]:
        """
        楽曲情報を辞書として取得
        
        Args:
            song_id: 楽曲識別子
            
        Returns:
            楽曲情報を含む辞書
        """
        song = self.database.get_song(song_id)
        if song:
            return {
                'id': song.id,
                'title': song.title,
                'artist': song.artist,
                'file_path': song.file_path
            }
        return {
            'id': song_id,
            'title': '不明',
            'artist': '不明',
            'file_path': '不明'
        }
    
    def _calculate_time_offset(self, match_pairs: List[Tuple[float, float]]) -> float:
        """
        クエリとデータベース音声間の最も可能性の高い時間オフセットを計算
        
        Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト
            
        Returns:
            時間オフセット（秒）
        """
        if not match_pairs:
            return 0.0
        
        # 時間差を計算
        time_diffs = [query_time - db_time for query_time, db_time in match_pairs]
        
        # オフセットとして中央値の時間差を返す
        time_diffs.sort()
        n = len(time_diffs)
        if n % 2 == 0:
            return (time_diffs[n//2 - 1] + time_diffs[n//2]) / 2
        else:
            return time_diffs[n//2]
    
    def identify_audio(self, query_fingerprints: List[Fingerprint], 
                      confidence_threshold: float = 0.1) -> Optional[Tuple[Song, float]]:
        """
        クエリフィンガープリントから音声を識別
        
        Args:
            query_fingerprints: クエリフィンガープリントのリスト
            confidence_threshold: 一致の最小信頼度スコア
            
        Returns:
            一致が見つかった場合は(Song, confidence_score)のタプル、そうでなければNone
        """
        matches = self.find_matches(query_fingerprints)
        
        if not matches:
            return None
        
        # 最良の一致を取得
        best_match = matches[0]
        if best_match['confidence'] >= confidence_threshold:
            song = self.database.get_song(best_match['song_id'])
            if song:
                return song, best_match['confidence']
        
        return None
    
    def _calculate_confidence_score(self, match_pairs: List[Tuple[float, float]]) -> float:
        """
        一致の時間アライメントに基づいて信頼度スコアを計算

       Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト

        スコア計算の詳細:
        - 入力: (query_time_offset, db_time_offset) のペアリスト
        - まず、各ペアの時間差（query_time - db_time）を計算し、
          類似の時間差を持つ一致を「アライメントされたグループ」としてまとめる（tolerance=0.3秒）
        - 最大のアライメントグループのサイズをmax_aligned_matches、全一致数をtotal_matchesとし、
          base_confidence = max_aligned_matches / total_matches とする
        - アライメント数が多い場合はボーナス（20件以上:*1.3, 10件以上:*1.2, 5件以上:*1.1）
        - アライメントグループが多すぎる場合はペナルティ（グループ数>3:*0.9）
        - 複数の中規模グループがあればボーナス（3件以上のグループ数*0.1, 最大+0.3）
        - 最終スコアは1.0でクリップ

        例: 30件中25件が同じ時間差で揃っていれば高スコア、
        一致がバラバラなら低スコア。

        Returns:
            0と1の間の信頼度スコア
        """
        if len(match_pairs) < 2:
            return 0.0
        
        # 改良された許容度で時間アライメントされたグループを検索
        aligned_groups = self._find_time_aligned_matches(match_pairs, self.time_tolerance)
        
        if not aligned_groups:
            return 0.0
        
        # 最大のアライメントされたグループを取得
        largest_group = max(aligned_groups, key=len)
        max_aligned_matches = len(largest_group)
        total_matches = len(match_pairs)
        
        # ベース信頼度：アライメントされた一致の比率
        base_confidence = max_aligned_matches / total_matches
        
        # 強いシグナルに対するボーナスを適用
        if max_aligned_matches >= 20:
            base_confidence *= 1.3
        elif max_aligned_matches >= 10:
            base_confidence *= 1.2
        elif max_aligned_matches >= 5:
            base_confidence *= 1.1
        
        # 散在する一致に対するペナルティ
        if len(aligned_groups) > 3:
            base_confidence *= 0.9
        
        # 複数の小さなアライメントされたグループがある場合のボーナス（冗長な証拠）
        secondary_groups = [g for g in aligned_groups if len(g) >= 3 and g != largest_group]
        if secondary_groups:
            secondary_bonus = min(0.1 * len(secondary_groups), 0.3)
            base_confidence += secondary_bonus
        
        return min(base_confidence, 1.0)  # 1.0でキャップ
    
    def _scale_fingerprints(self, fingerprints: List[Fingerprint], 
                           time_scale: float, freq_scale: float) -> List[Fingerprint]:
        """
        速度/ピッチ変化テスト用のフィンガープリントをスケール変更（0.5倍-2倍速度範囲に最適化）
        
        Args:
            fingerprints: 元のフィンガープリント
            time_scale: 時間スケール係数（0.5-2.0範囲）
            freq_scale: 周波数スケール係数（0.9-1.1範囲） - 将来の使用のために予約
            
        Returns:
            スケール変更されたフィンガープリントのリスト
        """
        scaled_fingerprints = []
        
        # freq_scaleは将来の周波数領域スケーリング用に予約
        _ = freq_scale
        
        # 極端な速度に対して改良された精度で時間スケーリングを適用
        for fp in fingerprints:
            try:
                # 0.5倍-2倍範囲に対してより高い精度で時間オフセットをスケーリング
                scaled_time = fp.time_offset * time_scale
                
                # 量子化境界をカバーするため複数のスケール版を作成
                scaled_fp = Fingerprint(
                    hash_value=fp.hash_value,
                    time_offset=scaled_time,
                    song_id=fp.song_id
                )
                scaled_fingerprints.append(scaled_fp)
                
                # 極端なスケーリング（0.5倍または2倍）の場合オフセット版を追加
                if time_scale <= 0.6 or time_scale >= 1.8:
                    # 境界交差を改善するため時間オフセットを追加
                    for offset in [-0.02, 0.02]:  # ±20msオフセット
                        offset_fp = Fingerprint(
                            hash_value=fp.hash_value,
                            time_offset=scaled_time + offset,
                            song_id=fp.song_id
                        )
                        scaled_fingerprints.append(offset_fp)
                        
            except Exception:
                # スケーリングが失敗した場合、元のものを使用
                scaled_fingerprints.append(fp)
        
        return scaled_fingerprints
    
    def _calculate_confidence_score_with_scaling(self, match_pairs: List[Tuple[float, float]], 
                                               time_scale: float, freq_scale: float) -> float:
        """
        スケーリング係数を考慮した信頼度スコアを計算（0.5倍-2倍速度範囲に最適化）

        Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト
            time_scale: 使用された時間スケール係数
            freq_scale: 使用された周波数スケール係数

        スコア計算の詳細:
        - ベースは _calculate_confidence_score の結果
        - 時間スケール(time_scale)が大きく逸脱（0.5倍～0.7倍や1.5倍～2倍）していればペナルティ（*0.8や*0.85）
        - 中程度の速度変化も緩やかにペナルティ（1.0 - |time_scale-1.0|*0.2）
        - ピッチスケール(freq_scale)も逸脱が大きいとペナルティ（1.0 - |freq_scale-1.0|*0.3）
        - 極端なスケーリングで一致数が多ければボーナス（20件以上:*1.15, 10件以上:*1.1）
        - 最終スコアは1.0でクリップ

        例: 2倍速や0.5倍速でも十分な一致があれば高スコア、
        速度・ピッチが大きく異なる場合はスコアが下がる。

        Returns:
            0と1の間の信頼度スコア
        """
        if len(match_pairs) < 2:
            return 0.0
        
        # ベース信頼度計算
        base_confidence = self._calculate_confidence_score(match_pairs)
        
        # 非標準スケーリングに対するペナルティを適用 - 0.5倍-2倍範囲に調整
        scale_penalty = 1.0
        
        # より緩やかな極端速度のカーブを持つ時間スケールペナルティ
        time_deviation = abs(time_scale - 1.0)
        if time_scale <= 0.7:  # 非常に遅い（0.5倍-0.7倍）
            scale_penalty *= 0.8  # 非常に遅い再生に対する中程度のペナルティ
        elif time_scale >= 1.5:  # 非常に速い（1.5倍-2倍）
            scale_penalty *= 0.85  # 非常に速い再生に対する中程度のペナルティ
        elif time_deviation > 0.1:  # 中程度の速度変化
            scale_penalty *= (1.0 - time_deviation * 0.2)  # より緩やかなペナルティ
        
        # 周波数スケールペナルティ - より控えめ
        freq_deviation = abs(freq_scale - 1.0)
        if freq_deviation > 0.03:
            scale_penalty *= (1.0 - freq_deviation * 0.3)
        
        # 極端なスケーリングで多くの一致がある場合にボーナスを適用
        if len(match_pairs) >= 20 and (time_scale <= 0.7 or time_scale >= 1.5):
            base_confidence *= 1.15  # 極端な速度で多数の一致があるボーナス
        elif len(match_pairs) >= 10 and (abs(time_scale - 1.0) > 0.01 or abs(freq_scale - 1.0) > 0.01):
            base_confidence *= 1.1
        
        return min(base_confidence * scale_penalty, 1.0)
    
    def _find_time_aligned_matches(self, match_pairs: List[Tuple[float, float]], 
                                  tolerance: float = 0.2) -> List[List[Tuple[float, float]]]:
        """
        指定された許容度で時間アライメントによる一致をグループ化
        
        Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト
            tolerance: 時間許容度（秒）
            
        Returns:
            時間アライメントされた一致を含む各グループのリスト
        """
        if not match_pairs:
            return []
        
        # 各一致の時間差を計算
        time_diffs = [(query_time - db_time, (query_time, db_time)) 
                     for query_time, db_time in match_pairs]
        
        # 時間差でソート
        time_diffs.sort(key=lambda x: x[0])
        
        # 類似の時間差を持つ一致をグループ化
        groups = []
        current_group = []
        current_time_diff = None
        
        for time_diff, match_pair in time_diffs:
            if current_time_diff is None or abs(time_diff - current_time_diff) <= tolerance:
                current_group.append(match_pair)
                if current_time_diff is None:
                    current_time_diff = time_diff
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [match_pair]
                current_time_diff = time_diff
        
        if current_group:
            groups.append(current_group)
        
        return groups
    
    # マルチクライテリア用の品質指標計算メソッド
    def _calculate_alignment_ratio(self, match_pairs: List[Tuple[float, float]]) -> float:
        """
        時間的一貫性を計算（0.5秒以内の時間差を持つマッチの比率）
        
        Args:
            match_pairs: (query_time, db_time)のマッチペアリスト
            
        Returns:
            時間的一貫性比率（0.0-1.0）
        """
        if not match_pairs:
            return 0.0
        
        # 時間差を計算
        time_diffs = [abs(query_time - db_time) for query_time, db_time in match_pairs]
        median_offset = np.median(time_diffs)
        
        # 0.5秒以内の許容範囲
        tolerance = 0.5
        
        # 許容範囲内のマッチ数を計算
        aligned_matches = sum(1 for diff in time_diffs if abs(diff - median_offset) <= tolerance)
        
        return aligned_matches / len(match_pairs)
    
    def _calculate_match_density(self, match_pairs: List[Tuple[float, float]]) -> float:
        """
        マッチ密度を計算（単位時間あたりのマッチ数）
        
        Args:
            match_pairs: (query_time, db_time)のマッチペアリスト
            
        Returns:
            マッチ密度（matches per second）
        """
        if not match_pairs or len(match_pairs) < 2:
            return 0.0
        
        # 時間範囲を計算
        query_times = [query_time for query_time, _ in match_pairs]
        time_span = max(query_times) - min(query_times)
        
        # 時間範囲が非常に小さい場合の処理
        if time_span < 0.1:  # 0.1秒未満
            return float(len(match_pairs))  # 短時間に集中したマッチ
        
        return len(match_pairs) / time_span

    def get_detailed_match_info(self, query_fingerprints: List[Fingerprint], 
                               song_id: str) -> Dict[str, Any]:
        """
        特定の楽曲の詳細なマッチ情報を取得
        
        Args:
            query_fingerprints: クエリフィンガープリントのリスト
            song_id: 詳細を取得する楽曲識別子
            
        Returns:
            詳細なマッチ情報を含む辞書
        """
        # この楽曲のすべての一致を取得
        all_matches = self.database.search_fingerprints(query_fingerprints)
        
        if song_id not in all_matches:
            return {
                'match_positions': [],
                'statistics': {
                    'total_matches': 0,
                    'aligned_matches': 0,
                    'alignment_ratio': 0.0,
                    'best_offset': 0.0,
                    'query_time_range': (0.0, 0.0),
                    'db_time_range': (0.0, 0.0)
                }
            }
        
        match_pairs = all_matches[song_id]
        
        # 詳細なマッチ位置を作成
        match_positions = []
        for query_time, db_time in match_pairs:
            match_positions.append({
                'query_time': query_time,
                'db_time': db_time,
                'time_diff': query_time - db_time
            })
        
        # 統計を計算
        if match_pairs:
            # 時間アライメントされたグループを検索
            aligned_groups = self._find_time_aligned_matches(match_pairs, self.time_tolerance)
            largest_group = max(aligned_groups, key=len) if aligned_groups else []
            
            query_times = [pos['query_time'] for pos in match_positions]
            db_times = [pos['db_time'] for pos in match_positions]
            
            statistics = {
                'total_matches': len(match_pairs),
                'aligned_matches': len(largest_group),
                'alignment_ratio': len(largest_group) / len(match_pairs) if match_pairs else 0.0,
                'best_offset': self._calculate_time_offset(match_pairs),
                'query_time_range': (min(query_times), max(query_times)) if query_times else (0.0, 0.0),
                'db_time_range': (min(db_times), max(db_times)) if db_times else (0.0, 0.0)
            }
        else:
            statistics = {
                'total_matches': 0,
                'aligned_matches': 0,
                'alignment_ratio': 0.0,
                'best_offset': 0.0,
                'query_time_range': (0.0, 0.0),
                'db_time_range': (0.0, 0.0)
            }
        
        return {
            'match_positions': match_positions,
            'statistics': statistics
        }
    
    def _calculate_peak_prominence(self, hist, peak_idx: int) -> float:
        """ピークの突出度を計算（ヒストグラム方式）"""
        
        if peak_idx == 0 or peak_idx == len(hist) - 1:
            return 0.0
            
        peak_value = hist[peak_idx]
        if peak_value <= 1:
            return 0.0
        
        # 左右の最小値を探索
        left_min = min(hist[:peak_idx]) if peak_idx > 0 else peak_value
        right_min = min(hist[peak_idx+1:]) if peak_idx < len(hist)-1 else peak_value
        
        # 突出度計算: (ピーク - 周辺最小値) / ピーク
        baseline = min(left_min, right_min)
        prominence = (peak_value - baseline) / peak_value if peak_value > 0 else 0.0
        
        return max(0.0, prominence)
    
    def _calculate_weighted_offset(self, hist, bin_edges, peak_idx: int) -> float:
        """重み付きオフセット計算（ピーク周辺の重心）"""
        
        # ピーク周辺のビンを取得（±2ビン）
        start_idx = max(0, peak_idx - 2)
        end_idx = min(len(hist), peak_idx + 3)
        
        weights = hist[start_idx:end_idx]
        positions = (bin_edges[start_idx:end_idx] + bin_edges[start_idx+1:end_idx+1]) / 2
        
        if np.sum(weights) == 0:
            return (bin_edges[peak_idx] + bin_edges[peak_idx + 1]) / 2
        
        # 重心計算
        weighted_offset = np.average(positions, weights=weights)
        return weighted_offset

    def _calculate_histogram_confidence(self, max_count: int, total_matches: int, 
                                       prominence: float, time_scale: float) -> float:
        """ヒストグラム信頼度計算"""
        
        # 基本スコア：最大ビンの相対頻度
        base_score = max_count / total_matches if total_matches > 0 else 0.0
        
        # ヒストグラム方式: ピークの突出度を重視
        prominence_boost = 1.0 + (prominence * 2.0)  # 突出度による強化
        
        # 一致数による重み付け（対数スケール）
        match_weight = min(1.0, np.log(max_count + 1) / np.log(20))  # 20一致で最大重み
        
        # 時間スケールペナルティ（ヒストグラム方式）
        scale_penalty = 1.0
        if abs(time_scale - 1.0) > 0.01:
            # より緩やかなペナルティ
            scale_deviation = abs(time_scale - 1.0)
            scale_penalty = np.exp(-scale_deviation * 0.5)  # 指数的減衰
        
        # 最終信頼度
        confidence = base_score * prominence_boost * match_weight * scale_penalty
        
        # ヒストグラム方式: 統計的閾値による正規化
        if max_count >= 5 and prominence > 0.3:
            confidence = min(1.0, confidence * 1.5)  # 高品質マッチのブースト
        
        return min(1.0, confidence)
    
    def _calculate_hybrid_histogram_confidence(self, match_pairs: List[Tuple[float, float]], 
                                             time_scale: float) -> float:
        """Hybrid方式用の軽量化ヒストグラム信頼度計算"""
        
        if len(match_pairs) < 5:
            return 0.0
        
        # 時間差を計算（スケール調整済み）
        offsets = [(db_time - query_time)/time_scale for query_time, db_time in match_pairs]
        offsets = np.array(offsets)
        
        # 軽量化されたビン幅計算
        std_dev = np.std(offsets)
        bin_width = max(0.1, min(std_dev / 2, 0.5))  # 0.1-0.5秒の範囲
        
        # 適応的レンジ（軽量版）
        offset_range = max(5, std_dev * 3)
        offset_mean = np.mean(offsets)
        
        bins = int((2 * offset_range) / bin_width)
        bins = max(10, min(bins, 50))  # ビン数を制限（軽量化）
        
        hist, _ = np.histogram(offsets, 
                                     bins=bins, 
                                     range=(offset_mean - offset_range, 
                                           offset_mean + offset_range))
        
        max_count = int(np.max(hist))
        max_bin_idx = int(np.argmax(hist))
        
        if max_count < 3:
            return 0.0
        
        # 軽量化されたピーク突出度計算
        peak_prominence = self._calculate_peak_prominence(hist, max_bin_idx)
        
        # 基本信頼度計算
        base_score = max_count / len(offsets)
        
        # hybrid用の簡略化された信頼度計算
        prominence_boost = 1.0 + (peak_prominence * 1.5)  # histogram方式より控えめ
        match_weight = min(1.0, np.log(max_count + 1) / np.log(15))  # 15一致で最大重み
        
        # 軽量化されたスケールペナルティ
        scale_penalty = 1.0
        if abs(time_scale - 1.0) > 0.05:
            scale_deviation = abs(time_scale - 1.0)
            scale_penalty = np.exp(-scale_deviation * 0.3)  # より軽いペナルティ
        
        confidence = base_score * prominence_boost * match_weight * scale_penalty
        
        # hybrid用の控えめなブースト
        if max_count >= 5 and peak_prominence > 0.2:
            confidence = min(1.0, confidence * 1.2)
        
        return min(1.0, confidence)


def create_sqlite_config(db_path: str = "fingerprints.db") -> DatabaseConfig:
    """SQLite設定を作成"""
    return DatabaseConfig(backend='sqlite', file_path=db_path)


def create_mysql_config(host: str, database: str, username: str, password: str, 
                       port: int = 3306) -> DatabaseConfig:
    """MySQL設定を作成"""
    return DatabaseConfig(
        backend='mysql',
        host=host,
        port=port,
        database=database,
        username=username,
        password=password
    )


def create_postgresql_config(host: str, database: str, username: str, password: str, 
                           port: int = 5432) -> DatabaseConfig:
    """PostgreSQL設定を作成"""
    return DatabaseConfig(
        backend='postgresql',
        host=host,
        port=port,
        database=database,
        username=username,
        password=password
    )


def create_elasticsearch_config(host: str, index_name: str = "fingerprints", 
                               port: int = 9200, username: Optional[str] = None,
                               password: Optional[str] = None) -> DatabaseConfig:
    """Elasticsearch設定を作成"""
    return DatabaseConfig(
        backend='elasticsearch',
        host=host,
        port=port,
        index_name=index_name,
        username=username,
        password=password
    )
