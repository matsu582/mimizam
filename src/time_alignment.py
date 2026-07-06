"""時間整合ユーティリティ

クエリとDBの一致ペアから得られる時間差（オフセット）の代表値を求める。

短いクリップを長い全編で照合すると、全編に散る偶発一致（ノイズ）が多数を
占め、単純な中央値はノイズの重心へ引かれて誤った位置を示す。最頻ビン
（＝最大整列クラスタ）の中心を採ることでノイズに強い代表オフセットを得る。
"""

from collections import Counter
from typing import List


def dominant_time_offset(
    time_diffs: List[float], bin_width: float = 0.5
) -> float:
    """時間差の最頻ビン中心（最大整列クラスタ）を代表オフセットとして返す

    Args:
        time_diffs: 各一致ペアの時間差（query_time - db_time）のリスト
        bin_width: ビン幅（秒）

    Returns:
        代表オフセット（秒）。time_diffs が空なら 0.0
    """
    if not time_diffs:
        return 0.0
    counts = Counter(round(d / bin_width) for d in time_diffs)
    best_bin = max(counts.items(), key=lambda kv: kv[1])[0]
    center = best_bin * bin_width
    near = [d for d in time_diffs if abs(d - center) <= bin_width]
    return sum(near) / len(near) if near else center
