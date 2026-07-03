"""
映像指紋の生成

PySceneDetect + AKAZE + VLAD + PCA を組み合わせた映像指紋パイプライン。
フレーム選定、特徴量抽出、VLAD集約、PCA圧縮、L2正規化を実装。
"""

import os
import logging
import io
import pickle
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# モジュールパスの再マッピング（pickle互換性のため）
_MODULE_REMAP = {
    "src.video_fingerprinter": "mimizam.src.video_fingerprinter",
    "src.pip_detector": "mimizam.src.pip_detector",
}


class _ModuleRemapUnpickler(pickle.Unpickler):
    """pickleのモジュールパスを再マッピングするUnpickler

    学習スクリプトが `from src.video_fingerprinter import ...` で
    保存したモデルを、パッケージインストール環境（mimizam.src.）
    でも読み込めるようにする。逆方向の変換も対応。
    """

    def find_class(self, module: str, name: str):
        remapped = _MODULE_REMAP.get(module)
        if remapped is None:
            for old, new in _MODULE_REMAP.items():
                if module == new:
                    remapped = old
                    break
        if remapped:
            try:
                return super().find_class(remapped, name)
            except (ModuleNotFoundError, ImportError):
                pass
        return super().find_class(module, name)


def _safe_pickle_load(f: io.IOBase):
    """モジュールパス互換性を考慮したpickle読み込み"""
    try:
        return _ModuleRemapUnpickler(f).load()
    except (ModuleNotFoundError, ImportError):
        f.seek(0)
        return pickle.load(f)


# フレーム正規化のデフォルト長辺ピクセル数
DEFAULT_NORMALIZE_LONG_SIDE = 1280


def _create_akaze():
    """OpenCV 4.x / 5.x 両対応のAKAZE生成"""
    if hasattr(cv2, 'AKAZE_create'):
        return cv2.AKAZE_create()
    if hasattr(cv2, 'xfeatures2d_AKAZE'):
        return cv2.xfeatures2d_AKAZE.create()
    raise RuntimeError(
        "AKAZEが利用できません。"
        "opencv-contrib-python をインストールしてください"
    )


def normalize_frame(
    frame: np.ndarray,
    target_long_side: int = DEFAULT_NORMALIZE_LONG_SIDE,
    allow_upscale: bool = False,
) -> np.ndarray:
    """
    フレームを正規化解像度にリサイズ（アスペクト比維持）

    比較するフレーム同士のスケールを統一するため、
    長辺を target_long_side ピクセルに正規化する。
    縦横比は維持されるため、異なるアスペクト比の映像にも対応。

    Args:
        frame: 入力フレーム（BGR or グレースケール）
        target_long_side: 正規化後の長辺ピクセル数
        allow_upscale: Trueなら小さい画像も拡大して正規化する
                       （PiP矩形切り出し等で使用）

    Returns:
        リサイズされたフレーム
    """
    if frame.ndim == 3:
        h, w = frame.shape[:2]
    else:
        h, w = frame.shape

    long_side = max(h, w)
    if long_side == target_long_side:
        return frame
    if long_side < target_long_side and not allow_upscale:
        return frame

    scale = target_long_side / long_side
    new_w = int(w * scale)
    new_h = int(h * scale)
    interp = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
    return cv2.resize(frame, (new_w, new_h), interpolation=interp)


@dataclass
class VideoFingerprintConfig:
    """映像指紋の設定パラメータ"""

    # フレーム選定
    scene_threshold: float = 27.0
    sample_interval: float = 1.0
    redundancy_threshold: float = 0.4

    # フレーム正規化（長辺ピクセル数、0で無効）
    normalize_long_side: int = DEFAULT_NORMALIZE_LONG_SIDE

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
    raw_descriptors: Optional[
        List[Tuple[int, float, np.ndarray]]
    ] = field(default=None)


class FrameSelector:
    """映像からキーフレームを選定するクラス"""

    def __init__(self, config: Optional[VideoFingerprintConfig] = None):
        """
        フレーム選定器を初期化

        Args:
            config: 映像指紋設定。Noneの場合はデフォルト値を使用
        """
        self.config = config or VideoFingerprintConfig()
        self._akaze = _create_akaze()
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
        self._akaze = _create_akaze()
        self._codebook_centers = None
        self._pca_components = None
        self._pca_mean = None
        self._descriptor_dim = None

    @property
    def is_trained(self) -> bool:
        """モデルが学習済みかどうか"""
        return (
            self._codebook_centers is not None
            and self._pca_components is not None
        )

    def extract_descriptors(
        self, frames: List[Tuple[int, float, np.ndarray]]
    ) -> Tuple[List[np.ndarray], List[Tuple[int, float, np.ndarray]]]:
        """
        フレーム群からAKAZE記述子を抽出

        フレームは正規化解像度（長辺1280px）にリサイズしてから
        AKAZE記述子を抽出する。これにより、異なる解像度の映像間でも
        codebook量子化の結果が安定する。

        Args:
            frames: [(フレームインデックス, タイムスタンプ, 画像), ...]

        Returns:
            (全記述子リスト, [(インデックス, タイムスタンプ, 記述子), ...])
        """
        all_descriptors = []
        per_frame = []
        target = self.config.normalize_long_side

        for fidx, ts, img in frames:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if target > 0:
                gray = normalize_frame(gray, target)
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

        descriptor_list の各要素は1フレーム/1画像分の記述子配列。
        K-Meansは全記述子で学習し、PCAはフレーム単位のVLADで学習する。

        Args:
            descriptor_list: フレーム/画像ごとの記述子配列のリスト
        """
        from sklearn.decomposition import PCA

        all_desc = np.vstack(descriptor_list).astype(np.float32)
        self._descriptor_dim = all_desc.shape[1]
        n_samples = all_desc.shape[0]

        logger.info(
            f"コードブック学習: {n_samples}記述子, "
            f"{self._descriptor_dim}次元"
        )

        # K-Meansコードブック構築（Collapse対策付き）
        k = self.config.codebook_size
        batch = min(self.config.codebook_batch_size, n_samples)
        codebook = self._train_codebook(
            all_desc, k, batch
        )
        self._codebook_centers = codebook.cluster_centers_.copy()

        vlad_dim = k * self._descriptor_dim
        logger.info(f"VLAD次元: {vlad_dim}")

        # フレーム/画像ごとのVLADベクトルを生成してPCA学習
        vlad_samples = []
        for desc in descriptor_list:
            if len(desc) >= 5:
                vlad_vec = self._compute_vlad_vector(desc)
                vlad_samples.append(vlad_vec)

        vlad_matrix = np.array(vlad_samples)
        target_dim = min(
            self.config.pca_dimensions,
            vlad_matrix.shape[0],
            vlad_matrix.shape[1],
        )

        pca = PCA(n_components=target_dim, random_state=42)
        pca.fit(vlad_matrix)
        self._pca_components = pca.components_.copy()
        self._pca_mean = pca.mean_.copy()

        variance = np.sum(pca.explained_variance_ratio_) * 100
        logger.info(
            f"PCA: {vlad_dim}→{target_dim}次元 "
            f"({len(vlad_samples)}サンプル, "
            f"分散保持率: {variance:.1f}%)"
        )

    def _train_codebook(
        self,
        descriptors: np.ndarray,
        k: int,
        batch_size: int,
        max_retries: int = 3,
    ):
        """
        Codebook Collapse対策付きK-Means学習

        空クラスタや極端な偏りを検出し、自動修復を試みる。
        - KMeans++初期化で均等な初期配置
        - reassign_ratioで学習中の空クラスタを再配置
        - 学習後に空クラスタがあれば最大クラスタを分割して補填
        """
        from sklearn.cluster import MiniBatchKMeans

        for attempt in range(max_retries):
            seed = 42 + attempt * 7
            n_init = 3 + attempt * 2

            codebook = MiniBatchKMeans(
                n_clusters=k,
                batch_size=batch_size,
                init="k-means++",
                reassignment_ratio=0.01,
                random_state=seed,
                n_init=n_init,
            )
            codebook.fit(descriptors)

            # クラスタ割り当て数を検査
            labels = codebook.predict(descriptors)
            counts = np.bincount(labels, minlength=k)
            empty_count = int(np.sum(counts == 0))
            max_ratio = float(counts.max()) / float(counts.sum())

            if empty_count == 0 and max_ratio < 0.5:
                logger.info(
                    f"codebook学習完了: "
                    f"割り当て min={counts.min()} "
                    f"max={counts.max()} "
                    f"(最大比率{max_ratio:.1%})"
                )
                return codebook

            logger.warning(
                f"codebook偏り検出 (試行{attempt + 1}): "
                f"空クラスタ={empty_count}, "
                f"最大比率={max_ratio:.1%}"
            )

            if empty_count > 0:
                codebook = self._repair_empty_clusters(
                    codebook, descriptors, counts
                )
                labels = codebook.predict(descriptors)
                counts = np.bincount(labels, minlength=k)
                empty_after = int(np.sum(counts == 0))
                if empty_after == 0:
                    logger.info(
                        f"空クラスタ修復完了: "
                        f"割り当て min={counts.min()} "
                        f"max={counts.max()}"
                    )
                    return codebook

        logger.warning("codebook修復の試行回数超過。最後の結果を使用")
        return codebook

    @staticmethod
    def _repair_empty_clusters(
        codebook, descriptors: np.ndarray, counts: np.ndarray
    ):
        """
        空クラスタを最大クラスタの分割で修復

        最も割り当ての多いクラスタ内の記述子にノイズを加えた
        新しい中心点を空クラスタに配置する。
        """
        centers = codebook.cluster_centers_.copy()
        labels = codebook.predict(descriptors)
        empty_ids = np.where(counts == 0)[0]

        for eid in empty_ids:
            largest = int(np.argmax(counts))
            mask = labels == largest
            cluster_desc = descriptors[mask]

            # 最大クラスタの分散方向に沿ってずらす
            std_vec = np.std(cluster_desc, axis=0)
            std_vec = np.where(std_vec < 1e-8, 1.0, std_vec)
            offset = std_vec * 0.5
            centers[eid] = centers[largest] + offset
            centers[largest] = centers[largest] - offset

            counts[eid] = counts[largest] // 2
            counts[largest] = counts[largest] - counts[eid]

        codebook.cluster_centers_ = centers
        return codebook

    def _pca_transform(self, vec: np.ndarray) -> np.ndarray:
        """
        PCA変換（numpyのみ、sklearn非依存）

        X_transformed = (X - mean) @ components.T
        """
        x = vec.reshape(1, -1).astype(np.float64)
        mean = self._pca_mean.astype(np.float64)
        comp = self._pca_components.astype(np.float64)
        centered = x - mean
        np.nan_to_num(centered, copy=False)
        result = centered @ comp.T
        np.nan_to_num(result, copy=False)
        return result.flatten()

    def _codebook_predict(self, descriptors: np.ndarray) -> np.ndarray:
        """
        K-Means最近働クラスタ割り当て（numpyのみ、sklearn非依存）

        ||x - c||^2 = ||x||^2 - 2*x*c^T + ||c||^2
        """
        x = descriptors.astype(np.float64)
        centers = self._codebook_centers.astype(np.float64)
        x_sq = np.sum(x ** 2, axis=1, keepdims=True)
        c_sq = np.sum(centers ** 2, axis=1, keepdims=True).T
        dot = x @ centers.T
        np.nan_to_num(dot, copy=False)
        dists = x_sq - 2.0 * dot + c_sq
        np.nan_to_num(dists, copy=False, nan=np.inf)
        return np.argmin(dists, axis=1)

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
        compressed = self._pca_transform(vlad_vec)
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
            compressed = self._pca_transform(vlad_vec)
            frame_fp = self._l2_normalize(compressed)
            frame_fingerprints.append((fidx, ts, frame_fp))

        # 映像全体指紋 = 全フレームVLADの平均 → PCA → L2正規化
        agg_vlad = np.mean(frame_vlads, axis=0)
        compressed = self._pca_transform(agg_vlad)
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
        k = self._codebook_centers.shape[0]
        d = self._codebook_centers.shape[1]
        centers = self._codebook_centers

        desc_f = descriptors.astype(np.float32)
        labels = self._codebook_predict(desc_f)

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
        """学習済みモデルをファイルに保存（sklearn非依存形式）"""
        model_data = {
            "format_version": 2,
            "codebook_centers": self._codebook_centers,
            "pca_components": self._pca_components,
            "pca_mean": self._pca_mean,
            "descriptor_dim": self._descriptor_dim,
            "config_dict": asdict(self.config),
        }
        with open(path, "wb") as f:
            pickle.dump(model_data, f)
        logger.info(f"モデル保存: {path}")

    def load_model(self, path: str) -> None:
        """保存済みモデルをファイルから読み込み"""
        with open(path, "rb") as f:
            model_data = _safe_pickle_load(f)

        if model_data.get("format_version") == 2:
            # 新形式: numpy配列のみ（sklearn非依存）
            self._codebook_centers = model_data["codebook_centers"]
            self._pca_components = model_data["pca_components"]
            self._pca_mean = model_data["pca_mean"]
        else:
            # 旧形式: sklearnオブジェクトからnumpy配列を抽出
            codebook = model_data["codebook"]
            pca = model_data["pca"]
            self._codebook_centers = codebook.cluster_centers_.copy()
            self._pca_components = pca.components_.copy()
            self._pca_mean = pca.mean_.copy()

        self._descriptor_dim = model_data["descriptor_dim"]
        if "config_dict" in model_data:
            self.config = VideoFingerprintConfig(
                **model_data["config_dict"]
            )
        elif "config" in model_data:
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
        fp.raw_descriptors = per_frame
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

    def rebuild_from_descriptors(
        self,
        per_frame_desc: List[Tuple[int, float, np.ndarray]],
    ) -> Optional[VideoFingerprint]:
        """
        保存済みAKAZE記述子から指紋を再生成

        モデル更新後に元映像なしで指紋を再計算する。

        Args:
            per_frame_desc: [(フレームインデックス, タイムスタンプ,
                              記述子配列), ...]

        Returns:
            VideoFingerprint。生成不可の場合None
        """
        if not self.is_trained:
            raise RuntimeError(
                "モデルが未学習です。"
                "先にload_model()を呼んでください"
            )
        if not per_frame_desc:
            return None

        fp = self.encoder.encode_video(per_frame_desc)
        fp.raw_descriptors = per_frame_desc
        return fp

    def fingerprint_pip_regions(
        self, video_path: str
    ) -> List[Tuple['PipRegion', VideoFingerprint]]:
        """
        PiP矩形を検出し、各矩形内を切り出して指紋化

        PiP映像では全体指紋が背景に引きずられるため、
        矩形内を切り出してアップスケール後に指紋化することで
        DB側の全体指紋との類似度を向上させる。

        Args:
            video_path: 映像ファイルパス

        Returns:
            [(PipRegion, VideoFingerprint), ...]
            PiP未検出の場合は空リスト
        """
        from .pip_detector import (
            detect_pip_regions, sample_frames_from_video,
        )

        if not self.is_trained:
            raise RuntimeError(
                "モデルが未学習です。"
                "先にload_model()を呼んでください"
            )

        if not os.path.exists(video_path):
            logger.error(f"映像が見つかりません: {video_path}")
            return []

        # PiP矩形を検出
        detect_frames = sample_frames_from_video(video_path, 30)
        pip_regions = detect_pip_regions(detect_frames)

        if not pip_regions:
            return []

        results = []
        target = self.config.normalize_long_side
        akaze = _create_akaze()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 24.0

        interval = max(1, int(fps * 2))
        sample_indices = list(range(0, total, interval))
        if len(sample_indices) > 60:
            step = len(sample_indices) // 60
            sample_indices = sample_indices[::step][:60]

        for region in pip_regions:
            per_frame_desc = []

            for fidx in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
                ret, frame = cap.read()
                if not ret:
                    continue

                fh, fw = frame.shape[:2]
                cx1 = max(0, min(region.x, fw - 1))
                cy1 = max(0, min(region.y, fh - 1))
                cx2 = min(region.x + region.w, fw)
                cy2 = min(region.y + region.h, fh)

                if cx2 - cx1 < 30 or cy2 - cy1 < 30:
                    continue

                crop = frame[cy1:cy2, cx1:cx2]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

                # 正規化解像度にアップスケール
                if target > 0:
                    gray = normalize_frame(
                        gray, target, allow_upscale=True
                    )

                kps, desc = akaze.detectAndCompute(gray, None)
                if desc is not None and len(desc) >= 5:
                    ts = fidx / fps
                    per_frame_desc.append(
                        (fidx, ts, desc.astype(np.float32))
                    )

            if not per_frame_desc:
                continue

            fp = self.encoder.encode_video(per_frame_desc)
            fp.raw_descriptors = per_frame_desc
            results.append((region, fp))

            logger.info(
                f"PiP矩形指紋生成: "
                f"({region.x},{region.y}) {region.w}x{region.h} "
                f"pip_score={region.pip_score:.2f} "
                f"({fp.frame_count}フレーム, "
                f"{fp.descriptor_count}記述子)"
            )

        cap.release()
        return results

    def save_model(self, path: str) -> None:
        """学習済みモデルを保存"""
        self.encoder.save_model(path)

    def load_model(self, path: str) -> None:
        """保存済みモデルを読み込み"""
        self.encoder.load_model(path)
