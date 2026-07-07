"""
映像指紋の生成

PySceneDetect + AKAZE + VLAD + PCA を組み合わせた映像指紋パイプライン。
フレーム選定、特徴量抽出、VLAD集約、PCA圧縮、L2正規化を実装。
"""

import os
import logging
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# フレーム正規化のデフォルト長辺ピクセル数
DEFAULT_NORMALIZE_LONG_SIDE = 1280


def _create_akaze():
    """OpenCV 4.x / 5.x 両対応のAKAZE生成

    4.x: AKAZEはfeatures2d(本体)に含まれ ``cv2.AKAZE_create`` として露出する。
    5.x: AKAZEはxfeatures2d(contrib)へ移動し
    ``cv2.xfeatures2d.AKAZE_create`` として露出する。
    いずれもopencv-contrib-pythonが必要。
    """
    if hasattr(cv2, 'AKAZE_create'):
        return cv2.AKAZE_create()
    xfeatures2d = getattr(cv2, 'xfeatures2d', None)
    if xfeatures2d is not None and hasattr(xfeatures2d, 'AKAZE_create'):
        return xfeatures2d.AKAZE_create()
    raise RuntimeError(
        "AKAZE is not available. "
        "Install opencv-contrib-python"
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


# 幾何検証用にキーポイント座標(x,y)を記述子の先頭に結合する際の列数
KEYPOINT_COLS = 2


def pack_raw_descriptors(
    per_frame: List[Tuple[int, float, np.ndarray]],
    per_frame_kpts: List[Tuple[int, float, np.ndarray]],
) -> List[Tuple[int, float, np.ndarray]]:
    """記述子(N×D)とキーポイント座標(N×2)を1配列(N×(2+D))へ結合する

    幾何検証(RANSAC)で対応点座標が必要になるため、キーポイント座標を先頭2列へ
    結合し、生記述子と同じ経路で永続化する。保存レイヤ(add_frame_descriptors)は
    列数を問わず ``reshape(count, -1)`` で復元するため列追加をそのまま扱える。
    フレーム順・行数は両リストで一致している前提（同一のdetectAndCompute由来）。

    Args:
        per_frame: [(fidx, ts, 記述子(N×D)), ...]
        per_frame_kpts: [(fidx, ts, キーポイント座標(N×2)), ...]

    Returns:
        [(fidx, ts, 結合配列(N×(2+D)) float32), ...]
    """
    packed: List[Tuple[int, float, np.ndarray]] = []
    for (fidx, ts, desc), (_, _, kpts) in zip(per_frame, per_frame_kpts):
        desc_f = desc.astype(np.float32)
        kpts_f = kpts.astype(np.float32).reshape(-1, KEYPOINT_COLS)
        packed.append((fidx, ts, np.hstack([kpts_f, desc_f])))
    return packed


def split_raw_descriptor(
    arr: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """結合配列(N×(2+D))をキーポイント座標(N×2)と記述子(N×D)へ分離する

    先頭2列がキーポイント座標、残りがAKAZE記述子。

    Args:
        arr: 保存済みの結合記述子配列(N×(2+D))

    Returns:
        (キーポイント座標(N×2), 記述子(N×D))
    """
    return arr[:, :KEYPOINT_COLS], arr[:, KEYPOINT_COLS:]


def to_hamming_uint8(desc: np.ndarray) -> np.ndarray:
    """AKAZE記述子をBF(Hamming)照合用のC連続uint8配列へ変換する

    既にuint8かつC連続なら再変換せずそのまま返す（幾何検証の反復呼び出しで
    同一DB記述子を毎回丸め直す無駄を省くための高速パス）。

    Args:
        desc: AKAZE記述子(N×D)

    Returns:
        C連続uint8のN×D配列
    """
    if desc.dtype == np.uint8 and desc.flags["C_CONTIGUOUS"]:
        return desc
    return np.ascontiguousarray(np.rint(desc), dtype=np.uint8)


# ホモグラフィ推定の既定手法。USAC_MAGSAC はRANSACより頑健かつ高速（実測で
# findHomographyが約2.5倍速）なため、利用可能なら既定に使う。古いOpenCVで
# 未対応の場合は通常のRANSACへフォールバックする。
DEFAULT_HOMOGRAPHY_METHOD = getattr(cv2, "USAC_MAGSAC", cv2.RANSAC)


def geometric_match(
    desc_q: np.ndarray,
    kpt_q: np.ndarray,
    desc_d: np.ndarray,
    kpt_d: np.ndarray,
    ratio: float = 0.75,
    ransac_thresh: float = 5.0,
    matcher: Optional["cv2.BFMatcher"] = None,
    min_good: int = 4,
    homography_method: int = DEFAULT_HOMOGRAPHY_METHOD,
) -> Tuple[int, int]:
    """2フレームのAKAZE記述子を突き合わせ、良マッチ数と幾何インライア数を返す

    BF(Hamming)最近傍→Loweの比率検定で良マッチを選び、RANSACでホモグラフィを
    推定して幾何的に整合するインライアを数える。OpenCVの標準APIのみを用いた
    独自実装。

    Args:
        desc_q, desc_d: AKAZE記述子(N×D)。float32でもuint8に丸めて突き合わせる。
            事前にuint8化(C連続)しておくと丸め処理を省いて高速化できる。
        kpt_q, kpt_d: キーポイント座標(N×2)
        ratio: Loweの比率検定のしきい値
        ransac_thresh: RANSACのインライア許容画素
        matcher: 再利用するBFMatcher（Noneなら都度生成）。多数フレームを
            突き合わせる際に生成コストを省くため共有インスタンスを渡せる。
        min_good: RANSACを実行する最小良マッチ数。インライア数は良マッチ数を
            超えないため、必要インライア数を渡せば見込みの無いペアの
            findHomography計算を省ける（既定4はホモグラフィ推定の下限）。

    Returns:
        (良マッチ数, 幾何インライア数)
    """
    if len(desc_q) < 2 or len(desc_d) < 2:
        return 0, 0

    q8 = to_hamming_uint8(desc_q)
    d8 = to_hamming_uint8(desc_d)

    bf = matcher if matcher is not None else cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = bf.knnMatch(q8, d8, k=2)
    good = [
        pair[0] for pair in knn
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance
    ]
    if len(good) < max(4, min_good):
        return len(good), 0

    src = np.float32(
        [kpt_q[m.queryIdx] for m in good]
    ).reshape(-1, 1, 2)
    dst = np.float32(
        [kpt_d[m.trainIdx] for m in good]
    ).reshape(-1, 1, 2)
    try:
        _, mask = cv2.findHomography(
            src, dst, homography_method, ransac_thresh
        )
    except cv2.error:
        # 指定手法が未対応の環境では通常のRANSACへフォールバック
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, ransac_thresh)
    inliers = int(mask.sum()) if mask is not None else 0
    return len(good), inliers


@dataclass
class VideoFingerprintConfig:
    """映像指紋の設定パラメータ"""

    # フレーム選定
    scene_threshold: float = 27.0
    sample_interval: float = 1.0
    redundancy_threshold: float = 0.4
    # シーン検出の評価fps（この間隔でフレームを取り出して評価する）
    # 4fpsでも検出シーン数・採用フレームは8fpsとほぼ一致し、retrieve(色変換)
    # 回数が減って高速化するため既定を4.0とする。
    scene_eval_fps: float = 4.0

    # Trueにするとフレーム選定・VLAD等の処理時間内訳をログ出力する
    profile_frames: bool = False

    # フレーム正規化（長辺ピクセル数、0で無効）
    normalize_long_side: int = DEFAULT_NORMALIZE_LONG_SIDE

    # VLAD
    codebook_size: int = 64
    codebook_batch_size: int = 10000

    # AKAZE記述子抽出の並列ワーカー数（0で自動: min(CPU数, 8)）
    num_workers: int = 0

    # PCA
    pca_dimensions: int = 128

    # 検索閾値
    similarity_threshold: float = 0.5

    # 生AKAZE記述子(raw_descriptors)を指紋に保持するか
    # Trueにすると元映像なしでの指紋再生成(rebuild_from_descriptors)が
    # 可能になるが、フレーム毎に多数×61次元の記述子をDB保存するため容量が
    # 肥大化する。既定Falseで保持しない。
    store_raw_descriptors: bool = False


@dataclass
class VideoFrameInfo:
    """選定されたフレームの情報"""
    frame_index: int
    timestamp: float
    label: str
    scene_num: int


@dataclass
class VideoFingerprint:
    """映像指紋データ

    キーフレームごとのVLAD→PCA→L2正規化ベクトル（frame_fingerprints）
    の集合で映像を表現する。検索・照合はこのフレーム単位指紋の
    近傍検索（ANN）と映像別の得票集計で行う。
    """
    frame_fingerprints: List[Tuple[int, float, np.ndarray]] = field(
        default_factory=list
    )
    frame_count: int = 0
    descriptor_count: int = 0
    raw_descriptors: Optional[
        List[Tuple[int, float, np.ndarray]]
    ] = field(default=None)


class FrameSelector:
    """映像からキーフレームを選定するクラス

    1回の映像走査でシーン検出とフレーム選定を同時に行う。
    シーン検出はPySceneDetectのContentDetector、冗長除去はHSVヒストグラム
    相関で判定する。
    """

    # シーン検出用の縮小解像度
    _SCENE_W = 160
    _SCENE_H = 90

    # ヒストグラム設定
    _HIST_H_BINS = 50
    _HIST_S_BINS = 60
    _HIST_DOWNSCALE_W = 320

    def __init__(self, config: Optional[VideoFingerprintConfig] = None):
        """
        フレーム選定器を初期化

        Args:
            config: 映像指紋設定。Noneの場合はデフォルト値を使用
        """
        self.config = config or VideoFingerprintConfig()

    def select_keyframes(
        self, video_path: str
    ) -> List[Tuple[int, float, np.ndarray]]:
        """
        映像からキーフレームを選定（1回走査）

        1回の映像読み込み（単一デコードパス）でシーン検出とフレーム選定を
        同時に実行。シーン境界はPySceneDetectのContentDetectorで検出し
        （フレームを自前ループから逐次投入するため二重デコードは発生しない）、
        冗長除去はHSVヒストグラム相関で高速に判定する。

        Args:
            video_path: 映像ファイルパス

        Returns:
            [(フレームインデックス, タイムスタンプ, フレーム画像), ...]
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        interval_frames = max(1, int(self.config.sample_interval * fps))

        # 評価間隔: scene_eval_fps でフレームを評価（精度と速度のバランス）
        eval_fps = self.config.scene_eval_fps or 8.0
        eval_stride = max(1, int(round(fps / eval_fps)))

        detector = self._create_scene_detector()
        accepted: List[Tuple[int, float, np.ndarray]] = []
        prev_accepted_hist: Optional[np.ndarray] = None
        last_accepted_idx = -interval_frames
        scene_count = 0
        evaluated = 0
        first_eval = True

        # config.profile_frames が True のときのみ各処理の所要時間を集計
        prof_on = self.config.profile_frames
        prof = {
            "decode": 0.0, "resize": 0.0,
            "scene": 0.0, "dedup": 0.0, "accept": 0.0,
        }
        n_dedup = 0

        frame_idx = 0
        while True:
            # 全フレームを復号する。ContentDetectorは連続フレーム前提で
            # フレーム間差分を評価するため、間引くとscene_thresholdの実効
            # 感度がfpsに依存してぶれる。シーン検出は全フレームを投入し、
            # eval_strideはキーフレーム候補の間引きにのみ用いる。
            _t = time.perf_counter() if prof_on else 0.0
            ret, frame = cap.read()
            if prof_on:
                prof["decode"] += time.perf_counter() - _t
            if not ret:
                break

            ts = frame_idx / fps

            # シーン変化検出（全フレーム投入）
            _t = time.perf_counter() if prof_on else 0.0
            small = cv2.resize(
                frame, (self._SCENE_W, self._SCENE_H),
                interpolation=cv2.INTER_LINEAR,
            )
            if prof_on:
                prof["resize"] += time.perf_counter() - _t

            _t = time.perf_counter() if prof_on else 0.0
            is_scene_change = False
            if first_eval:
                # 最初のフレームは常にシーン開始として採用
                is_scene_change = True
                first_eval = False
                detector.process_frame(frame_idx, small)
            elif detector.process_frame(frame_idx, small):
                is_scene_change = True
            if prof_on:
                prof["scene"] += time.perf_counter() - _t

            if is_scene_change:
                scene_count += 1

            # キーフレーム候補の評価はeval_strideで間引く
            # （シーン変化フレームは常に評価・採用対象）
            is_eval = (frame_idx % eval_stride == 0)
            if not (is_eval or is_scene_change):
                frame_idx += 1
                continue

            evaluated += 1

            # フレーム採用判定
            should_accept = False
            if is_scene_change:
                should_accept = True
            elif frame_idx - last_accepted_idx >= interval_frames:
                # サンプリング間隔到達 → ヒストグラム冗長チェック
                _t = time.perf_counter() if prof_on else 0.0
                if prev_accepted_hist is not None:
                    hist = self._compute_histogram(frame)
                    corr = cv2.compareHist(
                        prev_accepted_hist, hist,
                        cv2.HISTCMP_CORREL,
                    )
                    should_accept = corr < 0.95
                else:
                    should_accept = True
                if prof_on:
                    prof["dedup"] += time.perf_counter() - _t
                    n_dedup += 1

            if should_accept:
                _t = time.perf_counter() if prof_on else 0.0
                accepted.append((frame_idx, ts, frame.copy()))
                prev_accepted_hist = self._compute_histogram(frame)
                last_accepted_idx = frame_idx
                if prof_on:
                    prof["accept"] += time.perf_counter() - _t

            frame_idx += 1

        cap.release()
        logger.info(
            f"Frame selection: {scene_count} scenes, "
            f"{len(accepted)} frames accepted "
            f"({evaluated} frames evaluated)"
        )
        if prof_on:
            logger.info(
                "Frame selection breakdown[s]: "
                f"decode(all)={prof['decode']:.1f} "
                f"resize={prof['resize']:.1f} "
                f"scene(ContentDetector)={prof['scene']:.1f} "
                f"dedup(hist×{n_dedup})={prof['dedup']:.1f} "
                f"accept(hist×{len(accepted)})={prof['accept']:.1f}"
            )
        return accepted

    def _create_scene_detector(self):
        """PySceneDetectのContentDetectorを生成

        カットは自前のデコードループから process_frame() へフレームを
        逐次投入して検出するため、PySceneDetect側での追加デコードは発生しない。
        """
        from scenedetect.detectors import ContentDetector
        return ContentDetector(threshold=self.config.scene_threshold)

    def _compute_histogram(self, frame: np.ndarray) -> np.ndarray:
        """HSVヒストグラムを計算（冗長判定用）

        ヒストグラムは色の分布なので解像度にほぼ非依存。
        フル解像度で計算するとcvtColor/calcHistが重いため、
        中間サイズに縮小してから計算する（判定結果は同等）。
        """
        h, w = frame.shape[:2]
        if w > self._HIST_DOWNSCALE_W:
            nh = max(1, int(h * self._HIST_DOWNSCALE_W / w))
            frame = cv2.resize(
                frame, (self._HIST_DOWNSCALE_W, nh),
                interpolation=cv2.INTER_LINEAR,
            )
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv], [0, 1], None,
            [self._HIST_H_BINS, self._HIST_S_BINS],
            [0, 180, 0, 256],
        )
        cv2.normalize(hist, hist)
        return hist


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
        self._thread_local = threading.local()
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
    ) -> Tuple[
        List[np.ndarray],
        List[Tuple[int, float, np.ndarray]],
        List[Tuple[int, float, np.ndarray]],
    ]:
        """
        フレーム群からAKAZE記述子を抽出

        フレームは正規化解像度（長辺1280px）にリサイズしてから
        AKAZE記述子を抽出する。これにより、異なる解像度の映像間でも
        codebook量子化の結果が安定する。

        Args:
            frames: [(フレームインデックス, タイムスタンプ, 画像), ...]

        Returns:
            (全記述子リスト,
             [(インデックス, タイムスタンプ, 記述子), ...],
             [(インデックス, タイムスタンプ, キーポイント座標(N×2)), ...])
            3つ目は幾何検証(RANSAC)用のキーポイント画素座標。
        """
        workers = self._resolve_workers(len(frames))
        if workers <= 1:
            results = [self._extract_frame_descriptor(f) for f in frames]
        else:
            # OpenCVはdetectAndCompute実行中にGILを解放するため、
            # スレッド並列でマルチコアを活用できる（順序は保持）
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(
                    executor.map(self._extract_frame_descriptor, frames)
                )

        all_descriptors = []
        per_frame = []
        per_frame_kpts = []
        for res in results:
            if res is not None:
                fidx, ts, desc, kpts = res
                all_descriptors.append(desc)
                per_frame.append((fidx, ts, desc))
                per_frame_kpts.append((fidx, ts, kpts))

        return all_descriptors, per_frame, per_frame_kpts

    def _resolve_workers(self, num_frames: int) -> int:
        """並列ワーカー数を決定（0指定時はCPU数から自動算出）"""
        n = self.config.num_workers
        if n <= 0:
            n = min(os.cpu_count() or 1, 8)
        return max(1, min(n, num_frames))

    def _get_thread_akaze(self):
        """スレッドローカルなAKAZEインスタンスを取得（スレッド安全化）"""
        akaze = getattr(self._thread_local, "akaze", None)
        if akaze is None:
            akaze = _create_akaze()
            self._thread_local.akaze = akaze
        return akaze

    def _extract_frame_descriptor(
        self, frame: Tuple[int, float, np.ndarray]
    ) -> Optional[Tuple[int, float, np.ndarray, np.ndarray]]:
        """1フレームからAKAZE記述子とキーポイント座標を抽出

        キーポイント座標(N×2)は幾何検証(RANSAC)で使う。正規化後の画素座標なので
        DB側と同一の正規化長辺で抽出すれば、そのまま対応点の座標として使える。
        """
        fidx, ts, img = frame
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.config.normalize_long_side > 0:
            # 低解像度映像も含め全フレームの長辺を統一する。
            # 縮小のみ(allow_upscale=False)だと小さい映像だけスケールが
            # 揃わず、コードブック量子化の安定性が損なわれるため拡大も許可。
            gray = normalize_frame(
                gray, self.config.normalize_long_side, allow_upscale=True
            )
        kps, desc = self._get_thread_akaze().detectAndCompute(gray, None)
        if desc is not None and len(desc) > 0:
            kpts = np.array(
                [kp.pt for kp in kps], dtype=np.float32
            ).reshape(-1, 2)
            return (fidx, ts, desc, kpts)
        return None

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
            f"Codebook training: {n_samples} descriptors, "
            f"{self._descriptor_dim} dimensions"
        )

        # K-Meansコードブック構築（Collapse対策付き）
        k = self.config.codebook_size
        batch = min(self.config.codebook_batch_size, n_samples)
        codebook = self._train_codebook(
            all_desc, k, batch
        )
        self._codebook_centers = codebook.cluster_centers_.copy()

        vlad_dim = k * self._descriptor_dim
        logger.info(f"VLAD dimensions: {vlad_dim}")

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
            f"PCA: {vlad_dim}→{target_dim} dimensions "
            f"({len(vlad_samples)} samples, "
            f"variance retained: {variance:.1f}%)"
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
                    f"Codebook training complete: "
                    f"assignments min={counts.min()} "
                    f"max={counts.max()} "
                    f"(max ratio {max_ratio:.1%})"
                )
                return codebook

            logger.warning(
                f"Codebook imbalance detected (attempt {attempt + 1}): "
                f"empty clusters={empty_count}, "
                f"max ratio={max_ratio:.1%}"
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
                        f"Empty cluster repair complete: "
                        f"assignments min={counts.min()} "
                        f"max={counts.max()}"
                    )
                    return codebook

        logger.warning("Exceeded codebook repair retry limit; using last result")
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
        with np.errstate(all="ignore"):
            result = centered @ comp.T
        np.nan_to_num(result, copy=False)
        return result.flatten()

    def _codebook_predict(self, descriptors: np.ndarray) -> np.ndarray:
        """
        K-Means最近傍クラスタ割り当て（numpyのみ、sklearn非依存）

        ||x - c||^2 = ||x||^2 - 2*x*c^T + ||c||^2
        """
        x = descriptors.astype(np.float64)
        centers = self._codebook_centers.astype(np.float64)
        x_sq = np.sum(x ** 2, axis=1, keepdims=True)
        c_sq = np.sum(centers ** 2, axis=1, keepdims=True).T
        with np.errstate(all="ignore"):
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
            raise RuntimeError("Model is not trained. Call train() first")

        vlad_vec = self._compute_vlad_vector(descriptors)
        compressed = self._pca_transform(vlad_vec)
        return self._l2_normalize(compressed)

    def encode_video(
        self,
        per_frame_desc: List[Tuple[int, float, np.ndarray]],
    ) -> VideoFingerprint:
        """
        フレーム単位指紋を生成

        キーフレームごとにVLADベクトルを計算し、PCA圧縮してL2正規化した
        フレーム指紋群を生成する（ANN検索の対象）。

        Args:
            per_frame_desc: [(インデックス, タイムスタンプ, 記述子), ...]

        Returns:
            VideoFingerprint: フレーム単位指紋の集合
        """
        if not self.is_trained:
            raise RuntimeError("Model is not trained. Call train() first")

        frame_fingerprints = []
        total_desc = 0

        # config.profile_frames が True のときのみ内訳を集計
        prof_on = self.config.profile_frames
        t_vlad = 0.0
        t_pca = 0.0

        for fidx, ts, desc in per_frame_desc:
            _t = time.perf_counter() if prof_on else 0.0
            vlad_vec = self._compute_vlad_vector(desc)
            if prof_on:
                t_vlad += time.perf_counter() - _t
            total_desc += desc.shape[0]

            # フレーム単位指紋
            _t = time.perf_counter() if prof_on else 0.0
            compressed = self._pca_transform(vlad_vec)
            frame_fp = self._l2_normalize(compressed)
            if prof_on:
                t_pca += time.perf_counter() - _t
            frame_fingerprints.append((fidx, ts, frame_fp))

        if prof_on:
            logger.info(
                f"Fingerprint aggregation breakdown[s]: vlad(quantize+residual×{len(per_frame_desc)})"
                f"={t_vlad:.1f} pca(compress×{len(per_frame_desc)})={t_pca:.1f}"
            )

        return VideoFingerprint(
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
        # 保存済みraw記述子はキーポイント座標を先頭2列に結合している場合がある。
        # VLADは記述子本体のみで計算するため末尾d列（記述子次元）へ切り出す。
        if desc_f.ndim == 2 and desc_f.shape[1] > d:
            desc_f = desc_f[:, -d:]
        labels = self._codebook_predict(desc_f)

        # 各記述子の残差（desc - 割当クラスタ中心）をクラスタ単位で集約
        # np.add.at で同一ラベルの重複加算を正しく処理（Pythonループを排除）
        vlad = np.zeros((k, d), dtype=np.float32)
        residuals = desc_f - centers[labels]
        np.add.at(vlad, labels, residuals)

        # Intra-normalization（クラスタごとにL2正規化）
        norms = np.linalg.norm(vlad, axis=1, keepdims=True)
        np.divide(vlad, norms, out=vlad, where=norms > 1e-6)

        return vlad.flatten()

    def save_model(self, path: str) -> None:
        """学習済みモデルをファイルに保存

        pickleは任意コード実行のリスクがあるため使用せず、numpy配列と
        JSONメタデータのみをnpz(zip)形式で保存する（format_version:3）。
        設定はJSON文字列としてnumpy配列に格納し、読み込み時に
        allow_pickle=False で安全に復元できるようにする。
        """
        meta = {
            "format_version": 3,
            "descriptor_dim": self._descriptor_dim,
            "config_dict": asdict(self.config),
        }
        # np.savez はファイル名に .npz を付加するため、ファイルオブジェクトへ書く
        with open(path, "wb") as f:
            np.savez(
                f,
                codebook_centers=self._codebook_centers,
                pca_components=self._pca_components,
                pca_mean=self._pca_mean,
                meta_json=np.array(json.dumps(meta)),
            )
        logger.info(f"Model saved: {path}")

    def load_model(self, path: str) -> None:
        """保存済みモデルをファイルから読み込み（npz形式のみ対応）

        セキュリティ上の理由からpickle形式は読み込まない。npz以外の
        ファイルを渡した場合はエラーとする（旧pickleモデルはnpz形式へ
        再保存が必要）。
        """
        with open(path, "rb") as f:
            head = f.read(4)

        # npz(zip)はマジックバイト "PK\x03\x04" で始まる
        if head[:2] != b"PK":
            raise ValueError(
                "Model file is not in npz format. For security reasons "
                "pickle format is not loaded. Re-save it in npz format."
            )
        with open(path, "rb") as f:
            data = np.load(f, allow_pickle=False)
            self._codebook_centers = data["codebook_centers"]
            self._pca_components = data["pca_components"]
            self._pca_mean = data["pca_mean"]
            meta = json.loads(str(data["meta_json"]))
        self._descriptor_dim = meta["descriptor_dim"]
        if "config_dict" in meta:
            self.config = VideoFingerprintConfig(**meta["config_dict"])
        logger.info(f"Model loaded: {path}")

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
                logger.warning(f"Video not found: {vpath}")
                continue

            frames = self.frame_selector.select_keyframes(vpath)
            desc_list, _, _ = self.encoder.extract_descriptors(frames)
            all_descriptors.extend(desc_list)

            n_desc = sum(d.shape[0] for d in desc_list)
            stats["videos"] += 1
            stats["frames"] += len(frames)
            stats["descriptors"] += n_desc
            logger.info(
                f"  {os.path.basename(vpath)}: "
                f"{len(frames)} frames, {n_desc} descriptors"
            )

        if not all_descriptors:
            raise ValueError("Failed to extract descriptors")

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
                "Model is not trained. "
                "Call train_from_videos() first"
            )

        if not os.path.exists(video_path):
            logger.error(f"Video not found: {video_path}")
            return None

        frames = self.frame_selector.select_keyframes(video_path)
        if not frames:
            logger.warning(f"Failed to select frames: {video_path}")
            return None

        prof_on = self.config.profile_frames
        _t = time.perf_counter() if prof_on else 0.0
        _, per_frame, per_frame_kpts = self.encoder.extract_descriptors(
            frames
        )
        if prof_on:
            logger.info(
                f"Fingerprint aggregation breakdown[s]: akaze(descriptor extraction×{len(frames)}"
                f" frames)={time.perf_counter() - _t:.1f}"
            )
        if not per_frame:
            logger.warning(f"Failed to extract descriptors: {video_path}")
            return None

        fp = self.encoder.encode_video(per_frame)
        if self.config.store_raw_descriptors:
            # 幾何検証用にキーポイント座標を記述子の先頭2列へ結合して保持する
            # （N×(2+D)）。保存レイヤは列数を問わないため後方互換。
            fp.raw_descriptors = pack_raw_descriptors(
                per_frame, per_frame_kpts
            )
        dims = (
            fp.frame_fingerprints[0][2].shape[0]
            if fp.frame_fingerprints else 0
        )
        logger.info(
            f"Video fingerprint generated: {os.path.basename(video_path)} "
            f"({fp.frame_count} frames, "
            f"{fp.descriptor_count} descriptors, "
            f"{dims} dimensions)"
        )
        return fp

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
                "Model is not trained. "
                "Call load_model() first"
            )
        if not per_frame_desc:
            return None

        fp = self.encoder.encode_video(per_frame_desc)
        if self.config.store_raw_descriptors:
            fp.raw_descriptors = per_frame_desc
        return fp

    def fingerprint_pip_regions(
        self, video_path: str
    ) -> List[Tuple['PipRegion', VideoFingerprint]]:
        """
        PiP矩形を検出し、各矩形内を切り出して指紋化

        PiP映像ではフレーム全体の指紋が背景に引きずられるため、
        矩形内を切り出してアップスケール後に指紋化することで、
        DB側のフレーム指紋との類似度を向上させる。

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
                "Model is not trained. "
                "Call load_model() first"
            )

        if not os.path.exists(video_path):
            logger.error(f"Video not found: {video_path}")
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
            if self.config.store_raw_descriptors:
                fp.raw_descriptors = per_frame_desc
            results.append((region, fp))

            logger.info(
                f"PiP rectangle fingerprint generated: "
                f"({region.x},{region.y}) {region.w}x{region.h} "
                f"pip_score={region.pip_score:.2f} "
                f"({fp.frame_count} frames, "
                f"{fp.descriptor_count} descriptors)"
            )

        cap.release()
        return results

    def save_model(self, path: str) -> None:
        """学習済みモデルを保存"""
        self.encoder.save_model(path)

    def load_model(self, path: str) -> None:
        """保存済みモデルを読み込み（npz形式のみ対応）

        モデルには学習時の構造パラメータ（コードブック/PCA次元等）が保存されるが、
        scene_eval_fps・profile_frames・store_raw_descriptors といった実行時設定は
        現在のconfigを維持する（モデル読込で上書きしない）。
        読み込み後は3クラスで同一のconfigインスタンスを共有する。
        """
        runtime_scene_eval_fps = self.config.scene_eval_fps
        runtime_profile_frames = self.config.profile_frames
        runtime_store_raw_descriptors = self.config.store_raw_descriptors
        self.encoder.load_model(path)
        self.encoder.config.scene_eval_fps = runtime_scene_eval_fps
        self.encoder.config.profile_frames = runtime_profile_frames
        self.encoder.config.store_raw_descriptors = runtime_store_raw_descriptors
        self.config = self.encoder.config
        self.frame_selector.config = self.encoder.config
