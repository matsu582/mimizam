"""MariaDBデータベースバックエンド実装

MariaDB 11.7+ のネイティブベクトル機能（VECTOR型 + VECTOR INDEX(HNSW) +
VEC_DISTANCE_COSINE）を用いてフレーム指紋の近傍検索（ANN投票）を行う。
コミュニティ版MySQLと異なりMariaDBはOSS版でベクトルANN索引が使えるため、
pgvector/Elasticsearch同等の高速なフレーム候補検索を提供する。

接続・音声指紋・全体映像指紋などの基本機能はMySQLBackendを継承して再利用し、
フレームANNに関わる部分のみMariaDB固有の構文で上書きする。
"""

from typing import List, Dict, Tuple
import numpy as np

from .mysql_backend import MySQLBackend, MySQLError
from ..exceptions import DatabaseError


class MariaDBBackend(MySQLBackend):
    """MariaDBデータベースバックエンド（ネイティブベクトルANN対応）"""

    def __init__(self, config):
        super().__init__(config)
        # MariaDBネイティブベクトル(VECTOR型/VEC_DISTANCE_COSINE)の利用可否
        self._mariadb_vector_available = False

    def connect(self) -> bool:
        """MariaDBへ接続し、ベクトル機能の有無を判定する"""
        if not super().connect():
            return False
        # 親クラスのMySQL VECTOR判定(STRING_TO_VECTOR)はMariaDBでは通らないため、
        # MariaDB固有の関数で改めて判定する
        self._mariadb_vector_available = False
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT VEC_DISTANCE_COSINE("
                "VEC_FromText('[1,2,3]'), VEC_FromText('[1,2,3]'))"
            )
            cursor.fetchall()
            cursor.close()
            self._mariadb_vector_available = True
            self.logger.info("Detected MariaDB native vector support")
        except MySQLError:
            self.logger.info(
                "MariaDB vector support unavailable (falling back to brute-force)"
            )
        return True

    @staticmethod
    def _vec_text(fp_blob: bytes) -> str:
        """float32バイト列を VEC_FromText 用の '[x1,x2,...]' 文字列へ変換"""
        arr = np.frombuffer(fp_blob, dtype=np.float32)
        return "[" + ",".join(repr(float(x)) for x in arr) + "]"

    def _create_frame_vector_table(self, dimensions: int) -> None:
        """embedding VECTOR列とcosineのVECTOR INDEXを持つフレーム表を作成"""
        cursor = self.connection.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS frame_fingerprints (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                video_id VARCHAR(255) NOT NULL,
                frame_index INT NOT NULL,
                timestamp DOUBLE NOT NULL,
                fingerprint MEDIUMBLOB NOT NULL,
                embedding VECTOR({dimensions}) NOT NULL,
                INDEX idx_frame_fp_video (video_id),
                VECTOR INDEX (embedding) DISTANCE=cosine,
                FOREIGN KEY (video_id) REFERENCES videos (id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB CHARACTER SET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.close()

    def _ensure_frame_vector_table(self, dimensions: int) -> bool:
        """フレーム表がembedding VECTOR列を持つよう準備する

        既存表がembeddingを持たない場合、空なら作り直し、行があれば
        （NOT NULLなVECTOR列を後付けできないため）Falseを返して総当りへ委ねる。
        """
        if not self._mariadb_vector_available:
            return False
        try:
            # 参照先のvideos表など基本表を用意（frame表もここで作られ得る）
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'frame_fingerprints' "
                "AND column_name = 'embedding'"
            )
            has_embedding = cursor.fetchone()[0] > 0
            if not has_embedding:
                cursor.execute("SELECT COUNT(*) FROM frame_fingerprints")
                if cursor.fetchone()[0] > 0:
                    cursor.close()
                    return False
                cursor.execute("DROP TABLE frame_fingerprints")
                cursor.close()
                self._create_frame_vector_table(dimensions)
            else:
                cursor.close()
            return True
        except MySQLError as e:
            self.logger.warning(f"MariaDB frame vector table setup error: {e}")
            return False

    def _frame_vector_ready(self) -> bool:
        """フレーム表がembedding VECTOR列を持つか確認する"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'frame_fingerprints' "
                "AND column_name = 'embedding'"
            )
            ok = cursor.fetchone()[0] > 0
            cursor.close()
            return ok
        except MySQLError:
            return False

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> bool:
        """MariaDBにフレーム単位指紋を一括保存（embeddingはVEC_FromTextで投入）"""
        if not self._mariadb_vector_available or not frames:
            return super().add_frame_fingerprints(video_id, frames)
        dims = len(frames[0][2]) // 4  # float32バイト列 → 次元数
        if not self._ensure_frame_vector_table(dims):
            return super().add_frame_fingerprints(video_id, frames)
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = %s",
                (video_id,),
            )
            rows = [
                (video_id, fidx, float(ts), fp_blob, self._vec_text(fp_blob))
                for fidx, ts, fp_blob in frames
            ]
            cursor.executemany(
                """INSERT INTO frame_fingerprints
                    (video_id, frame_index, timestamp,
                     fingerprint, embedding)
                VALUES (%s, %s, %s, %s, VEC_FromText(%s))""",
                rows,
            )
            cursor.close()
            return True
        except MySQLError as e:
            self.logger.error(f"MariaDB frame fingerprint save error: {e}")
            raise DatabaseError(
                "Failed to add frame fingerprints", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4,
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームのANN近傍を引き、映像別に得票/類似度を集計

        VECTOR INDEX(cosine)経由のKNNをクエリフレームごとに発行する。
        索引を使わせるため内側クエリは素の VEC_DISTANCE_COSINE で昇順+LIMIT、
        外側で 1-距離 の類似度に変換する（MariaDB推奨パターン）。

        戻り値: {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        agg: Dict[str, Dict[str, float]] = {}
        if not query_fps:
            return agg
        if not self._mariadb_vector_available or not self._frame_vector_ready():
            return super().search_frame_candidates(
                query_fps, dimensions, k_per_query, sim_threshold
            )
        try:
            cursor = self.connection.cursor()
            for q_blob in query_fps:
                cursor.execute(
                    "SET @q = VEC_FromText(%s)", (self._vec_text(q_blob),)
                )
                cursor.execute(
                    """SELECT t.video_id, 1 - t.dist AS sim FROM (
                        SELECT video_id,
                               VEC_DISTANCE_COSINE(embedding, @q) AS dist
                        FROM frame_fingerprints
                        ORDER BY dist
                        LIMIT %s
                    ) AS t""",
                    (k_per_query,),
                )
                for vid_id, sim in cursor.fetchall():
                    sim = float(sim)
                    if sim < sim_threshold:
                        continue
                    slot = agg.setdefault(
                        vid_id, {"votes": 0.0, "score_sum": 0.0}
                    )
                    slot["votes"] += 1.0
                    slot["score_sum"] += sim
            cursor.close()
            return agg
        except MySQLError as e:
            self.logger.debug(f"MariaDB frame ANN search fallback: {e}")
            return super().search_frame_candidates(
                query_fps, dimensions, k_per_query, sim_threshold
            )
