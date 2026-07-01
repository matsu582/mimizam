"""
映像指紋の生成

PySceneDetect + AKAZE + VLAD + PCA を組み合わせた映像指紋パイプライン。
フレーム選定、特徴量抽出、VLAD集約、PCA圧縮、L2正規化を実装。
"""

import os
import logging
import pickle
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoFingerprintConfig:
    """映像指紋の設定パラメータ"""

    # フレーム選定
    scene_threshold: float = 27.0
    sample_interval: float = 1.0
    redundancy_threshold: float = 0.4

    # VLAD
    codebook_size: int = 64
    codebook_batch_size: int = 10000

    # PCA
    pca_dimensions: int = 128

    # 検索閾値
    similarity_threshold: float = 0.5


@dataclass
class VideoFrameInfo:
    """選定されたフレームの情報"""
    frame_index: int
    timestamp: float
    label: str
    scene_num: int


@dataclass
class VideoFingerprint:
    """映像指紋データ"""
    video_fingerprint: np.ndarray
    frame_fingerprints: List[Tuple[int, float, np.ndarray]] = field(
        default_factory=list
    )
    frame_count: int = 0
    descriptor_count: int = 0


class FrameSelector:
    """映像からキーフレームを選定するクラス"""

    def __init__(self, config: Optional[VideoFingerprintConfig] = None):
        """
        フレーム選定器を初期化

        Args:
            config: 映像指紋設定。Noneの場合はデフォルト値を使用
        """
        self.config = config or VideoFingerprintConfig()
        self._akaze = cv2.AKAZE_create()
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    def select_keyframes(
        self, video_path: str
    ) -> List[Tuple[int, float, np.ndarray]]:
        """
        映像からキーフレームを選定

        ハイブリッド方式: シーン境界 + 1fpsサンプリング + AKAZE冗長除去

        Args:
            video_path: 映像ファイルパス

        Returns:
            [(フレームインデックス, タイムスタンプ, フレーム画像), ...]
        """
        scenes = self._detect_scenes(video_path)
        return self._hybrid_selection(video_path, scenes)

    def _detect_scenes(self, video_path: str) -> list:
        """
        シーンチェンジを検出

        ContentDetector → AdaptiveDetector → 全体1シーン のフォールバック
        """
        try:
            from scenedetect import detect, ContentDetector
            scene_list = detect(
                video_path,
                ContentDetector(threshold=self.config.scene_threshold),
            )
            if scene_list:
                logger.info(
                    f"ContentDetector: {len(scene_list)}シーン検出"
                )
                return scene_list
        except Exception as exc:
            logger.warning(f"ContentDetector失敗: {exc}")

        try:
            from scenedetect import detect, AdaptiveDetector
            scene_list = detect(video_path, AdaptiveDetector())
            if scene_list:
                logger.info(
                    f"AdaptiveDetector: {len(scene_list)}シーン検出"
                )
                return scene_list
        except Exception as exc:
            logger.warning(f"AdaptiveDetector失敗: {exc}")

        # 全体を1シーンとして扱う
        return self._fallback_single_scene(video_path)

    def _fallback_single_scene(self, video_path: str) -> list:
        """全体を1シーンとするフォールバック"""
        from scenedetect import FrameTimecode
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        logger.info("フォールバック: 全体を1シーンとして処理")
        return [
            (FrameTimecode(0, fps=fps), FrameTimecode(total, fps=fps))
        ]

    def _hybrid_selection(
        self, video_path: str, scene_list: list
    ) -> List[Tuple[int, float, np.ndarray]]:
        """
        シーン境界 + シーン内1fpsサンプリング + AKAZE冗長除去
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        interval = self.config.sample_interval
        thresh = self.config.redundancy_threshold

        # 候補フレームを列挙
        candidates = []
        for idx, scene in enumerate(scene_list):
            s_start = scene[0].get_seconds()
            s_end = scene[1].get_seconds()
            scene_num = idx + 1

            candidates.append(
                (int(s_start * fps), s_start, "boundary", scene_num)
            )

            if s_end - s_start > interval:
                t = s_start + interval
                while t < s_end - 0.1:
                    candidates.append(
                        (int(t * fps), t, "sample", scene_num)
                    )
                    t += interval

        if not candidates:
            cap.release()
            return []

        # 近接フレーム除去
        deduped = [candidates[0]]
        for c in candidates[1:]:
            if c[1] - deduped[-1][1] >= 0.3:
                deduped.append(c)

        # AKAZE冗長除去
        accepted = []
        prev_frame = None

        for fidx, ts, label, snum in deduped:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
            ret, frame = cap.read()
            if not ret:
                continue

            if label == "boundary":
                accepted.append((fidx, ts, frame))
                prev_frame = frame.copy()
                continue

            if prev_frame is not None:
                ratio = self._compute_match_ratio(prev_frame, frame)
                if ratio >= thresh:
                    continue

            accepted.append((fidx, ts, frame))
            prev_frame = frame.copy()

        cap.release()
        logger.info(
            f"フレーム選定: {len(deduped)}候補 → {len(accepted)}フレーム採用"
        )
        return accepted

    def _compute_match_ratio(
        self, frame_a: np.ndarray, frame_b: np.ndarray
    ) -> float:
        """2フレーム間のAKAZEマッチ率を計算"""
        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

        kp_a, desc_a = self._akaze.detectAndCompute(gray_a, None)
        kp_b, desc_b = self._akaze.detectAndCompute(gray_b, None)

        if (
            desc_a is None
            or desc_b is None
            or len(kp_a) < 2
            or len(kp_b) < 2
        ):
            return 0.0

        matches = self._matcher.knnMatch(desc_a, desc_b, k=2)
        good_count = 0
        for pair in matches:
            if len(pair) == 2:
                if pair[0].distance < 0.75 * pair[1].distance:
                    good_count += 1

        return good_count / max(len(kp_a), len(kp_b))


class VLADEncoder:
    """VLAD（Vector of Locally Aggregated Descriptors）エンコーダ"""

    def __init__(self, config: Optional[VideoFingerprintConfig] = None):
        """
        VLADエンコーダを初期化

        Args:
            config: 映像指紋設定
        """
        self.config = config or VideoFingerprintConfig()
        self._akaze = cv2.AKAZE_create()
        self._codebook = None
        self._pca = None
        self._descriptor_dim = None

    @property
    def is_trained(self) -> bool:
        """モデルが学習済みかどうか"""
        return self._codebook is not None and self._pca is not None

    def extract_descriptors(
        self, frames: List[Tuple[int, float, np.ndarray]]
    ) -> Tuple[List[np.ndarray], List[Tuple[int, float, np.ndarray]]]:
        """
        フレーム群からAKAZE記述子を抽出

        Args:
            frames: [(フレームインデックス, タイムスタンプ, 画像), ...]

        Returns:
            (全記述子リスト, [(インデックス, タイムスタンプ, 記述子), ...])
        """
        all_descriptors = []
        per_frame = []

        for fidx, ts, img in frames:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, desc = self._akaze.detectAndCompute(gray, None)
            if desc is not None and len(desc) > 0:
                all_descriptors.append(desc)
                per_frame.append((fidx, ts, desc))

        return all_descriptors, per_frame

    def train(
        self, descriptor_list: List[np.ndarray]
    ) -> None:
        """
        コードブックとPCAモデルを学習

        Args:
            descriptor_list: 全映像から収集した記述子のリスト
        """
        from sklearn.cluster import MiniBatchKMeans
        from sklearn.decomposition import PCA

        all_desc = np.vstack(descriptor_list).astype(np.float32)
        self._descriptor_dim = all_desc.shape[1]
        n_samples = all_desc.shape[0]

        logger.info(
            f"コードブック学習: {n_samples}記述子, "
            f"{self._descriptor_dim}次元"
        )

        # K-Meansコードブック構築
        k = self.config.codebook_size
        batch = min(self.config.codebook_batch_size, n_samples)
        self._codebook = MiniBatchKMeans(
            n_clusters=k, batch_size=batch,
            random_state=42, n_init=3
        )
        self._codebook.fit(all_desc)

        # VLAD次元数
        vlad_dim = k * self._descriptor_dim
        logger.info(f"VLAD次元: {vlad_dim}")

        # VLADベクトルのサンプルを作成してPCA学習
        # 学習データからサンプルVLADを生成
        sample_size = min(5000, n_samples)
        rng = np.random.default_rng(42)
        indices = rng.choice(n_samples, size=sample_size, replace=False)
        sample_desc = all_desc[indices]

        # フレームサイズ程度の記述子群に分割してVLAD生成
        chunk_size = max(20, sample_size // 200)
        vlad_samples = []
        for start in range(0, sample_size, chunk_size):
            end = min(start + chunk_size, sample_size)
            chunk = sample_desc[start:end]
            vlad_vec = self._compute_vlad_vector(chunk)
            vlad_samples.append(vlad_vec)

        vlad_matrix = np.array(vlad_samples)
        target_dim = min(
            self.config.pca_dimensions,
            vlad_matrix.shape[0],
            vlad_matrix.shape[1],
        )

        self._pca = PCA(n_components=target_dim, random_state=42)
        self._pca.fit(vlad_matrix)

        variance = np.sum(self._pca.explained_variance_ratio_) * 100
        logger.info(
            f"PCA: {vlad_dim}→{target_dim}次元 "
            f"(分散保持率: {variance:.1f}%)"
        )

    def encode_frame(self, descriptors: np.ndarray) -> Optional[np.ndarray]:
        """
        単一フレームの記述子群からL2正規化済み指紋ベクトルを生成

        Args:
            descriptors: フレームのAKAZE記述子

        Returns:
            L2正規化済み指紋ベクトル（128次元）。生成不可の場合None
        """
        if not self.is_trained:
            raise RuntimeError("モデルが未学習です。先にtrain()を呼んでください")

        vlad_vec = self._compute_vlad_vector(descriptors)
        compressed = self._pca.transform(vlad_vec.reshape(1, -1)).flatten()
        return self._l2_normalize(compressed)

    def encode_video(
        self,
        per_frame_desc: List[Tuple[int, float, np.ndarray]],
    ) -> VideoFingerprint:
        """
        映像全体の指紋を生成

        全フレームのVLADベクトルを平均し、PCA圧縮してL2正規化。
        フレーム単位指紋も同時に生成（PiP対策用）。

        Args:
            per_frame_desc: [(インデックス, タイムスタンプ, 記述子), ...]

        Returns:
            VideoFingerprint: 映像全体指紋 + フレーム単位指紋
        """
        if not self.is_trained:
            raise RuntimeError("モデルが未学習です。先にtrain()を呼んでください")

        frame_vlads = []
        frame_fingerprints = []
        total_desc = 0

        for fidx, ts, desc in per_frame_desc:
            vlad_vec = self._compute_vlad_vector(desc)
            frame_vlads.append(vlad_vec)
            total_desc += desc.shape[0]

            # フレーム単位指紋
            compressed = self._pca.transform(
                vlad_vec.reshape(1, -1)
            ).flatten()
            frame_fp = self._l2_normalize(compressed)
            frame_fingerprints.append((fidx, ts, frame_fp))

        # 映像全体指紋 = 全フレームVLADの平均 → PCA → L2正規化
        agg_vlad = np.mean(frame_vlads, axis=0)
        compressed = self._pca.transform(agg_vlad.reshape(1, -1)).flatten()
        video_fp = self._l2_normalize(compressed)

        return VideoFingerprint(
            video_fingerprint=video_fp,
            frame_fingerprints=frame_fingerprints,
            frame_count=len(per_frame_desc),
            descriptor_count=total_desc,
        )

    def _compute_vlad_vector(self, descriptors: np.ndarray) -> np.ndarray:
        """
        記述子群からVLADベクトルを計算

        Intra-normalization適用済み。

        Args:
            descriptors: AKAZE記述子の配列

        Returns:
            VLADベクトル（k * d 次元）
        """
        k = self._codebook.n_clusters
        d = self._codebook.cluster_centers_.shape[1]
        centers = self._codebook.cluster_centers_

        desc_f = descriptors.astype(np.float32)
        labels = self._codebook.predict(desc_f)

        vlad = np.zeros((k, d), dtype=np.float32)
        for i, lbl in enumerate(labels):
            vlad[lbl] += desc_f[i] - centers[lbl]

        # Intra-normalization
        for j in range(k):
            norm_val = np.linalg.norm(vlad[j])
            if norm_val > 1e-6:
                vlad[j] /= norm_val

        return vlad.flatten()

    def save_model(self, path: str) -> None:
        """学習済みモデルをファイルに保存"""
        model_data = {
            "codebook": self._codebook,
            "pca": self._pca,
            "descriptor_dim": self._descriptor_dim,
            "config": self.config,
        }
        with open(path, "wb") as f:
            pickle.dump(model_data, f)
        logger.info(f"モデル保存: {path}")

    def load_model(self, path: str) -> None:
        """保存済みモデルをファイルから読み込み"""
        with open(path, "rb") as f:
            model_data = pickle.load(f)
        self._codebook = model_data["codebook"]
        self._pca = model_data["pca"]
        self._descriptor_dim = model_data["descriptor_dim"]
        if "config" in model_data:
            self.config = model_data["config"]
        logger.info(f"モデル読み込み: {path}")

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        """L2正規化"""
        norm_val = np.linalg.norm(vec)
        if norm_val > 1e-6:
            return vec / norm_val
        return vec


class VideoFingerprinter:
    """
    映像指紋システムのメインクラス

    フレーム選定 → AKAZE特徴量抽出 → VLAD集約 → PCA圧縮 → L2正規化
    の一連のパイプラインを統合。
    """

    def __init__(self, config: Optional[VideoFingerprintConfig] = None):
        """
        映像指紋システムを初期化

        Args:
            config: 映像指紋設定。Noneの場合はデフォルト値を使用
        """
        self.config = config or VideoFingerprintConfig()
        self.frame_selector = FrameSelector(self.config)
        self.encoder = VLADEncoder(self.config)

    @property
    def is_trained(self) -> bool:
        """エンコーダが学習済みかどうか"""
        return self.encoder.is_trained

    def train_from_videos(
        self, video_paths: List[str]
    ) -> Dict[str, Any]:
        """
        複数映像からモデルを学習

        全映像の記述子を収集してコードブックとPCAを学習する。

        Args:
            video_paths: 映像ファイルパスのリスト

        Returns:
            学習統計情報の辞書
        """
        all_descriptors = []
        stats = {"videos": 0, "frames": 0, "descriptors": 0}

        for vpath in video_paths:
            if not os.path.exists(vpath):
                logger.warning(f"映像が見つかりません: {vpath}")
                continue

            frames = self.frame_selector.select_keyframes(vpath)
            desc_list, _ = self.encoder.extract_descriptors(frames)
            all_descriptors.extend(desc_list)

            n_desc = sum(d.shape[0] for d in desc_list)
            stats["videos"] += 1
            stats["frames"] += len(frames)
            stats["descriptors"] += n_desc
            logger.info(
                f"  {os.path.basename(vpath)}: "
                f"{len(frames)}フレーム, {n_desc}記述子"
            )

        if not all_descriptors:
            raise ValueError("記述子が抽出できませんでした")

        self.encoder.train(all_descriptors)
        return stats

    def fingerprint_video(
        self, video_path: str
    ) -> Optional[VideoFingerprint]:
        """
        映像ファイルから指紋を生成

        Args:
            video_path: 映像ファイルパス

        Returns:
            VideoFingerprint。生成不可の場合None
        """
        if not self.is_trained:
            raise RuntimeError(
                "モデルが未学習です。"
                "先にtrain_from_videos()を呼んでください"
            )

        if not os.path.exists(video_path):
            logger.error(f"映像が見つかりません: {video_path}")
            return None

        frames = self.frame_selector.select_keyframes(video_path)
        if not frames:
            logger.warning(f"フレームを選定できませんでした: {video_path}")
            return None

        _, per_frame = self.encoder.extract_descriptors(frames)
        if not per_frame:
            logger.warning(f"記述子を抽出できませんでした: {video_path}")
            return None

        fp = self.encoder.encode_video(per_frame)
        logger.info(
            f"映像指紋生成: {os.path.basename(video_path)} "
            f"({fp.frame_count}フレーム, "
            f"{fp.descriptor_count}記述子, "
            f"{fp.video_fingerprint.shape[0]}次元)"
        )
        return fp

    def compute_similarity(
        self,
        fp_a: VideoFingerprint,
        fp_b: VideoFingerprint,
        use_frame_matching: bool = False,
    ) -> float:
        """
        2つの映像指紋の類似度を計算

        Args:
            fp_a: 映像指紋A
            fp_b: 映像指紋B
            use_frame_matching: フレーム単位マッチング（PiP対策）を使用するか

        Returns:
            類似度スコア（ドット積、-1.0〜1.0）
        """
        if not use_frame_matching:
            return float(np.dot(fp_a.video_fingerprint, fp_b.video_fingerprint))

        # フレーム単位マッチング: 各クエリフレームの最高一致スコアのmaxを採用
        if not fp_a.frame_fingerprints or not fp_b.frame_fingerprints:
            return float(
                np.dot(fp_a.video_fingerprint, fp_b.video_fingerprint)
            )

        best_scores = []
        for _, _, q_fp in fp_a.frame_fingerprints:
            frame_best = max(
                float(np.dot(q_fp, d_fp))
                for _, _, d_fp in fp_b.frame_fingerprints
            )
            best_scores.append(frame_best)

        return float(np.max(best_scores))

    def save_model(self, path: str) -> None:
        """学習済みモデルを保存"""
        self.encoder.save_model(path)

    def load_model(self, path: str) -> None:
        """保存済みモデルを読み込み"""
        self.encoder.load_model(path)
