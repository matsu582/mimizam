"""
音声指紋のデータベース管理
複数のデータベースバックエンド（SQLite、MySQL、PostgreSQL、Elasticsearch）をサポート
"""

from typing import List, Optional, Tuple, Dict, Any
import logging
import math
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
            logging.warning("Failed to disconnect from database in destructor", exc_info=True)
    
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

    def get_songs(self, song_ids: List[str]) -> Dict[str, Optional[Song]]:
        """複数の楽曲情報をまとめて取得（バックエンドの一括取得へ委譲）

        Args:
            song_ids: 取得する楽曲IDのリスト

        Returns:
            song_id -> Song(見つからない場合None) のマッピング辞書
        """
        return self.backend.get_songs(song_ids)

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
        
        # スコアリング方式の選択。尺度不変ハッシュへ移行したため time_scale/
        # freq_scale のブルートフォース列挙は廃止し、いずれの方式も単一検索＋
        # 頑健直線回帰の同一経路へ委譲する（名称は後方互換のため保持）。
        self.scoring_method = "hybrid"  # "hybrid", "histogram", "detailed"

        # 整列許容度（秒）。傾きで速度変化を吸収した後のオフセット残差の許容幅。
        # 大きすぎると無関係曲の偶発整列が増えるため、ピーク時間分解能(約23ms)に
        # 見合う狭さにする。
        self.time_tolerance = 0.05

        # 信頼度算出の飽和パラメータ。整列インライアが confidence_full_matches 件
        # かつ整列割合が confidence_full_ratio に達したら信頼度1.0とみなす。
        # 無関係曲は整列"数"が桁違いに少ないため、数と割合の積で明確に分離できる。
        self.confidence_full_matches = 80
        self.confidence_full_ratio = 0.12
        # 純度項の下限。整列割合がこの値を超えた分だけ純度信頼度に寄与する。
        # 無関係曲の整列割合（概ね0.1〜0.2）では0となり、クリーン一致でのみ効く。
        self.confidence_purity_floor = 0.5

        # 頑健直線回帰（ハフ投票）の傾き（＝time_scale）の妥当域と各種パラメータ。
        self.slope_range = (0.25, 4.0)
        self.line_fit_sample_size = 150      # ペア傾き算出のサンプル点上限（O(K^2)抑制）
        self.slope_log2_bin = 0.03           # 傾きヒストグラムのビン幅（log2空間）
        self.slope_min_dq = 1.0              # 傾き算出に使う query 時間差の下限（秒）
        self.slope_top_candidates = 5        # インライア評価に回す傾き候補ビン数
    
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
            results = self._find_matches_hybrid(query_fingerprints, adjusted_min_matches, top_k)
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
            # 楽曲情報はまとめて取得（結果ごとの個別取得によるN+1を回避）
            song_ids = [result['song_id'] for result in results]
            song_map = self._get_songs_batch(song_ids)
            for result in results:
                song_id = result['song_id']
                song = song_map.get(song_id)
                
                # song（Songオブジェクト）と song_info（辞書）を追加。
                # 呼び出し側が再取得しないよう、Songオブジェクトも保持する。
                result['song'] = song
                result['song_info'] = (
                    self._song_to_info(song) if song else self._empty_song_info(song_id)
                )
                
                # 詳細情報を追加（1段階目で取得済みの match_pairs から算出。DB再検索しない）
                if include_details:
                    result['detailed_info'] = self._build_detailed_match_info(
                        result.get('match_pairs', []),
                        result.get('time_scale', 1.0)
                    )
        
        return results
    
    def _find_matches_scale_invariant(self, query_fingerprints: List[Fingerprint],
                                      min_matches: int, top_k: int) -> List[Dict[str, Any]]:
        """尺度不変ハッシュ前提の単一検索マッチング（速度・ピッチ変化に頑健）

        ハッシュ自体が時間伸縮・ピッチ変化に不変なため、time_scale/freq_scale の
        ブルートフォース列挙もDB再検索の多重発行も行わない（DB検索は1回のみ）。
        マッチした (query_time, db_time) を頑健直線回帰 db≈s·query+c にフィットし、
        傾き s を time_scale、切片 c を offset として復元する。曲ごとの信頼度は、
        傾きで正規化したペア (s·query, db) の時間整列から算出する（速度変化しても
        オフセットが一定になるため、既存の整列ベース信頼度をそのまま再利用できる）。
        """
        # 単一検索: 尺度不変ハッシュなので候補集合はこれで完結する
        all_matches = self.database.search_fingerprints(query_fingerprints)

        best_results: Dict[str, Dict[str, Any]] = {}
        for song_id, pairs in all_matches.items():
            if len(pairs) < min_matches:
                continue

            # (query_time, db_time) の支配的な直線 db≈slope·query+offset を
            # ハフ投票（傾きの最頻値→オフセットの最頻値）で頑健に推定する。
            # 尺度不変ハッシュは粗量子化で偶発衝突が増えるため、外れ値が過半でも
            # 壊れない最頻値ベースを用いる（中央値だと汚染される）。
            slope, offset, inlier_pairs = self._fit_scale_offset(pairs)
            aligned = len(inlier_pairs)
            if aligned < min_matches:
                continue

            confidence = self._confidence_from_inliers(aligned, len(pairs))
            if confidence < self.min_confidence:
                continue

            best_results[song_id] = {
                'song_id': song_id,
                'confidence': confidence,
                'match_count': aligned,
                'match_pairs': inlier_pairs,
                # 支配直線の切片（速度補正後のオフセット）
                'time_offset': offset,
                'time_scale': slope,
                # ピッチ不変はハッシュ側で吸収済みのため freq_scale は常に 1.0
                'freq_scale': 1.0,
                'alignment_ratio': aligned / len(pairs) if pairs else 0.0,
                'match_density': self._calculate_match_density(inlier_pairs),
            }

        return self._sort_and_limit_results(best_results)[:top_k]

    # 後方互換: scoring_method は挙動を変えず、いずれも尺度不変の単一検索経路へ委譲する。
    def _find_matches_hybrid(self, query_fingerprints: List[Fingerprint],
                             min_matches: int, top_k: int) -> List[Dict[str, Any]]:
        return self._find_matches_scale_invariant(query_fingerprints, min_matches, top_k)

    def _find_matches_histogram(self, query_fingerprints: List[Fingerprint],
                                min_matches: int, top_k: int = 10) -> List[Dict[str, Any]]:
        return self._find_matches_scale_invariant(query_fingerprints, min_matches, top_k)

    def _find_matches_detailed(self, query_fingerprints: List[Fingerprint],
                               min_matches: int, top_k: int = 10) -> List[Dict[str, Any]]:
        return self._find_matches_scale_invariant(query_fingerprints, min_matches, top_k)

    def _estimate_slope_candidates(self, pairs: List[Tuple[float, float]]) -> List[float]:
        """支配傾き（=time_scale）の候補を投票数上位順に返す（ハフ投票）

        ペア間傾き (dj-di)/(qj-qi) を log2 空間でヒストグラム投票し、得票の多い
        ビンの傾き中央値を候補として複数返す。時間量子化の影響を抑えるため
        query 側の時間差が十分大きいペアのみを使う。単一の最頻ビンだと、粗量子化で
        偶発的に別倍率のビンが競り勝つ場合に取り違えるため、上位複数を後段の
        インライア評価に渡して真の倍率を選び直せるようにする。
        """
        n = len(pairs)
        if n < 2:
            return [1.0]

        # O(K^2) に制限するための等間隔サンプリング（決定的）
        k = self.line_fit_sample_size
        if n > k:
            stride = n / k
            sample = [pairs[int(i * stride)] for i in range(k)]
        else:
            sample = pairs

        lo, hi = self.slope_range
        log_lo = math.log2(lo)
        bin_w = self.slope_log2_bin
        # 傾き精度確保のため query 時間差がこの秒数以上のペアを優先採用する
        min_dq = self.slope_min_dq

        def collect(min_gap: float) -> List[float]:
            out = []
            m = len(sample)
            for i in range(m):
                qi, di = sample[i]
                for j in range(i + 1, m):
                    qj, dj = sample[j]
                    dq = qj - qi
                    if abs(dq) < min_gap:
                        continue
                    s = (dj - di) / dq
                    if lo <= s <= hi:
                        out.append(s)
            return out

        slopes = collect(min_dq)
        if not slopes:  # 短いクエリ等でペアが集まらない場合は制約を緩める
            slopes = collect(1e-6)
        if not slopes:
            return [1.0]

        # log2 空間でヒストグラム投票。得票上位ビンの中央値を候補にする。
        votes: Dict[int, List[float]] = {}
        for s in slopes:
            b = int((math.log2(s) - log_lo) / bin_w)
            votes.setdefault(b, []).append(s)
        ranked = sorted(votes.values(), key=len, reverse=True)
        candidates = [float(np.median(v)) for v in ranked[: self.slope_top_candidates]]
        # 恒等倍率(1.0)は変換なしの基準として常に評価対象へ含める
        if all(abs(c - 1.0) > bin_w for c in candidates):
            candidates.append(1.0)
        return candidates

    def _inliers_for_slope(self, pairs: List[Tuple[float, float]], slope: float
                           ) -> Tuple[float, List[Tuple[float, float]]]:
        """与えた傾きに対しオフセット最頻ビンを求め、整合インライアを返す"""
        offsets = [db_time - slope * q_time for q_time, db_time in pairs]
        tol = self.time_tolerance
        offset_votes: Dict[int, List[float]] = {}
        for off in offsets:
            b = int(round(off / tol))
            offset_votes.setdefault(b, []).append(off)
        best_offsets = max(offset_votes.values(), key=len)
        offset = float(np.median(best_offsets))
        inliers = [
            pair for pair, off in zip(pairs, offsets)
            if abs(off - offset) <= tol
        ]
        return offset, inliers

    def _fit_scale_offset(self, pairs: List[Tuple[float, float]]
                          ) -> Tuple[float, float, List[Tuple[float, float]]]:
        """支配直線 db≈slope·query+offset を推定し、整合するインライアを返す

        1. _estimate_slope_candidates で傾き候補（=time_scale）を得票上位から複数得る。
        2. 各候補についてオフセット最頻ビン近傍（±time_tolerance）のインライアを数え、
           インライアが最大になる傾きを採用する。粗量子化で偶発的に別倍率のビンが
           競り勝っても、真の倍率が最も整合するため取り違えを是正できる。

        Returns:
            (slope, offset, inlier_pairs)
        """
        if not pairs:
            return 1.0, 0.0, []

        lo, hi = self.slope_range
        best = (1.0, 0.0, [])
        for cand in self._estimate_slope_candidates(pairs):
            slope = min(max(cand, lo), hi)
            offset, inliers = self._inliers_for_slope(pairs, slope)
            if len(inliers) > len(best[2]):
                best = (slope, offset, inliers)
        return best

    def _confidence_from_inliers(self, aligned: int, total: int) -> float:
        """支配直線に整合したインライア数と割合から信頼度[0,1]を算出する

        速度・ピッチ変化した実音源では、候補ペアに偶発衝突が多く混じるため整列
        "割合"は低くなる（数%）。一方 無関係曲も割合が同程度に低いので、両者は主に
        整列"絶対数"で分離する（真の一致は数十〜数千、無関係曲は数件）。よって
        数の飽和×割合の飽和を基本信頼度とする（どちらか一方が低いだけで抑制）。

        ただしノイズの少ないクリーンな一致では整列割合が1.0近くまで上がる。この
        「ほぼ全ペアが単一直線に乗る」純度は無関係曲では起こらないため、高純度時は
        絶対数が少なくても高信頼度とみなす純度項を併用し、両者の大きい方を採る。
        """
        if total <= 0 or aligned < 2:
            return 0.0
        ratio = aligned / total
        count_term = min(1.0, aligned / self.confidence_full_matches)
        ratio_term = min(1.0, ratio / self.confidence_full_ratio)
        count_conf = count_term * ratio_term
        # 純度項: 整列割合が purity_floor を超えた分を [0,1] に線形写像する。
        # 無関係曲の割合（〜0.1）では0、クリーン一致（〜1.0）で1に近づく。
        purity_conf = max(0.0, (ratio - self.confidence_purity_floor)
                          / (1.0 - self.confidence_purity_floor))
        return min(max(count_conf, purity_conf), 1.0)

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
            return self._song_to_info(song)
        return self._empty_song_info(song_id)

    @staticmethod
    def _song_to_info(song: Song) -> Dict[str, str]:
        """Songオブジェクトをinfo辞書へ変換"""
        return {
            'id': song.id,
            'title': song.title,
            'artist': song.artist,
            'file_path': song.file_path
        }

    @staticmethod
    def _empty_song_info(song_id: str) -> Dict[str, str]:
        """楽曲が見つからない場合のプレースホルダ情報"""
        return {
            'id': song_id,
            'title': '不明',
            'artist': '不明',
            'file_path': '不明'
        }

    def _get_songs_batch(self, song_ids: List[str]) -> Dict[str, Optional[Song]]:
        """複数楽曲をまとめて取得する

        バックエンドの ``get_songs``（IN/ANY/_mget による真の一括取得）へ委譲し、
        結果ごとの個別取得によるN+1を1回の問い合わせに集約する。
        ``FingerprintDatabase.get_songs`` が無い場合は get_song ループへフォールバック。
        """
        if not song_ids:
            return {}
        get_songs = getattr(self.database, 'get_songs', None)
        if callable(get_songs):
            return get_songs(song_ids)
        # フォールバック（後方互換）
        song_map: Dict[str, Optional[Song]] = {}
        for song_id in dict.fromkeys(song_ids):  # 重複排除・順序保持
            song_map[song_id] = self.database.get_song(song_id)
        return song_map
    
    def _calculate_time_offset(self, match_pairs: List[Tuple[float, float]],
                               time_scale: float = 1.0) -> float:
        """
        クエリとデータベース音声間の最も可能性の高い時間オフセットを計算
        
        Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト
            time_scale: 速度変化倍率（db≈time_scale·query）。速度変化した一致では
                query_time - db_time は一定にならないため、傾きで正規化した残差
                query_time - db_time/time_scale を一定量として集計する。既定1.0で
                従来の query_time - db_time と一致する（後方互換）。
            
        Returns:
            時間オフセット（秒）
        """
        if not match_pairs:
            return 0.0

        # 全ペアの中央値は、短いクエリを長い全編で照合した際に全編へ散る
        # 偶発一致（ノイズ）に引かれて誤位置を示す。時間的に一貫した最大
        # クラスタ（最大整列グループ）の中央値を代表オフセットとして採る。
        aligned_groups = self._find_time_aligned_matches(
            match_pairs, self.time_tolerance, time_scale
        )
        target = max(aligned_groups, key=len) if aligned_groups else match_pairs

        time_diffs = sorted(
            query_time - db_time / time_scale for query_time, db_time in target
        )
        n = len(time_diffs)
        if n % 2 == 0:
            return (time_diffs[n // 2 - 1] + time_diffs[n // 2]) / 2
        return time_diffs[n // 2]
    
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
            # find_matches が付与した Song を再利用し、再取得を避ける
            song = best_match.get('song') or self.database.get_song(best_match['song_id'])
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
    
    def _find_time_aligned_matches(self, match_pairs: List[Tuple[float, float]], 
                                  tolerance: float = 0.2,
                                  time_scale: float = 1.0) -> List[List[Tuple[float, float]]]:
        """
        指定された許容度で時間アライメントによる一致をグループ化
        
        Args:
            match_pairs: (query_time_offset, db_time_offset)タプルのリスト
            tolerance: 時間許容度（秒）
            time_scale: 速度変化倍率（db≈time_scale·query）。速度変化した一致では
                query_time - db_time は一定にならないため、傾きで正規化した残差
                query_time - db_time/time_scale でグループ化する。既定1.0で従来と一致。
            
        Returns:
            時間アライメントされた一致を含む各グループのリスト
        """
        if not match_pairs:
            return []
        
        # 各一致の時間差（速度補正後の残差）を計算
        time_diffs = [(query_time - db_time / time_scale, (query_time, db_time)) 
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
        
        # 時間差は符号付きで計算する。abs()で符号を捨てると +3s と -3s が
        # 同一視され、鏡像的なズレでも「整列している」と誤評価するため。
        time_diffs = [query_time - db_time for query_time, db_time in match_pairs]
        median_offset = np.median(time_diffs)
        
        # 0.5秒以内の許容範囲
        tolerance = 0.5
        
        # 符号付きオフセットの中央値からの偏差が許容範囲内のマッチ数を計算
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

    def detailed_match_info(self,
                            match_pairs: List[Tuple[float, float]],
                            time_scale: Optional[float] = None) -> Dict[str, Any]:
        """マッチペアから詳細なマッチ情報を取得する（match_pairs主導の公開API）

        find_matches / search_fingerprints で既に取得済みの
        (query_time, db_time) ペアを直接受け取り、DB再検索を行わずに詳細情報を
        構築する。これが詳細取得の主経路であり、query_fingerprints から
        DB再検索する get_detailed_match_info は補助（後方互換）に位置付ける。

        Args:
            match_pairs: (query_time, db_time) ペアのリスト
            time_scale: 速度変化倍率（db≈time_scale·query）。未指定(None)のときは
                ペアから頑健直線回帰で自動推定する。速度変化した一致では
                query_time - db_time が一定にならないため、傾きで正規化してから
                整列・オフセットを算出する（未指定でも正しく集計できる）。

        Returns:
            詳細なマッチ情報を含む辞書
        """
        pairs = match_pairs or []
        if time_scale is None:
            # 呼び出し側が倍率を渡さなくても速度変化一致を正しく扱えるよう自動推定する
            time_scale = self._fit_scale_offset(pairs)[0] if pairs else 1.0
        return self._build_detailed_match_info(pairs, time_scale)

    def get_detailed_match_info(self, query_fingerprints: List[Fingerprint], 
                               song_id: str,
                               match_pairs: Optional[List[Tuple[float, float]]] = None) -> Dict[str, Any]:
        """
        特定の楽曲の詳細なマッチ情報を取得（後方互換API）

        match_pairs 主導の :meth:`detailed_match_info` を推奨する。本メソッドは
        match_pairs が未指定のとき query_fingerprints から DB を再検索する補助経路で、
        その再検索経路は非推奨（将来的に削除予定）。

        Args:
            query_fingerprints: クエリフィンガープリントのリスト（再検索経路でのみ使用）
            song_id: 詳細を取得する楽曲識別子
            match_pairs: 取得済みの (query_time, db_time) ペア。指定された場合は
                DB再検索を行わずこれを使う（推奨経路）。
            
        Returns:
            詳細なマッチ情報を含む辞書
        """
        # 取得済みペアがあれば再検索せずそのまま使う（推奨経路）
        if match_pairs is not None:
            return self.detailed_match_info(match_pairs)

        # 補助（後方互換）: query_fingerprints から DB を再検索する。非推奨。
        import warnings
        warnings.warn(
            "get_detailed_match_info() の query_fingerprints からの再検索経路は非推奨です。"
            "取得済みの match_pairs を detailed_match_info(match_pairs) に渡してください。",
            DeprecationWarning,
            stacklevel=2,
        )
        all_matches = self.database.search_fingerprints(query_fingerprints)
        return self.detailed_match_info(all_matches.get(song_id, []))

    def _build_detailed_match_info(self, match_pairs: List[Tuple[float, float]],
                                   time_scale: float = 1.0) -> Dict[str, Any]:
        """マッチペアから詳細なマッチ情報を構築する

        1段階目で取得済みの match_pairs をそのまま使い、DB再検索を行わない
        （④のN+1クエリ回避）。time_scale は速度変化倍率で、query_time-db_time が
        一定にならない速度変化一致でも、傾きで正規化した残差で整列・オフセットを
        正しく集計するために用いる（既定1.0で従来挙動）。
        """
        if not match_pairs:
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

        # 詳細なマッチ位置を作成（time_diff は速度補正後の残差 query - db/time_scale）
        match_positions = []
        for query_time, db_time in match_pairs:
            match_positions.append({
                'query_time': query_time,
                'db_time': db_time,
                'time_diff': query_time - db_time / time_scale
            })

        # 時間アライメントされたグループを検索（傾きで正規化して集計）
        aligned_groups = self._find_time_aligned_matches(
            match_pairs, self.time_tolerance, time_scale
        )
        largest_group = max(aligned_groups, key=len) if aligned_groups else []

        query_times = [pos['query_time'] for pos in match_positions]
        db_times = [pos['db_time'] for pos in match_positions]

        statistics = {
            'total_matches': len(match_pairs),
            'aligned_matches': len(largest_group),
            'alignment_ratio': len(largest_group) / len(match_pairs),
            'best_offset': self._calculate_time_offset(match_pairs, time_scale),
            'query_time_range': (min(query_times), max(query_times)) if query_times else (0.0, 0.0),
            'db_time_range': (min(db_times), max(db_times)) if db_times else (0.0, 0.0)
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
        bin_width = max(0.1, min(float(std_dev) / 2, 0.5))  # 0.1-0.5秒の範囲
        
        # 適応的レンジ（軽量版）
        offset_range = max(5.0, float(std_dev) * 3)
        offset_mean = np.mean(offsets)
        
        bins = int((2 * offset_range) / bin_width)
        bins = max(10, min(bins, 50))  # ビン数を制限（軽量化）
        
        hist, _ = np.histogram(offsets, 
                                     bins=bins, 
                                     range=(float(offset_mean - offset_range), 
                                           float(offset_mean + offset_range)))
        
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
