#!/usr/bin/env python3
"""音声マッチのオフセット分布を診断するツール

目的:
    短いクリップを長い全編音声で検索したとき、報告される時間位置が
    「全マッチ時間差の中央値」でずれる問題（例: 実際はED=22:28なのに
    16:41と表示される）を切り分ける。

    指定楽曲について、全マッチペア (query_time, db_time) を取り出し、
      - DB時刻ヒストグラム（マッチがどこに集中しているか）
      - オフセット(query-db)の中央値 と 最頻ピーク の比較
      - 最大整列クラスタ（時間的に一貫した最大グループ）のDB時刻範囲
    を表示する。中央値ピークと最大整列クラスタが食い違えば、
    「音声は正しく整列しているが、中央値ベースの位置推定でズレて表示
    されている」ことが確認できる。

使い方:
    uv run ./examples/diagnose_audio_offset.py \
        ~/path/to/DADAN_S2_ED.mp4 \
        --database ./movie_fingerprints.db \
        [--song <song_id>] [-k 10] [--bin 5.0]

    入力は動画でも .wav でも可（動画はffmpegで音声抽出）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mimizam.src.mimizam import create_mimizam_sqlite  # noqa: E402


def _extract_audio(video_path: str, temp_dir: str) -> str:
    """ffmpegで動画から音声(wav)を抽出する"""
    out = os.path.join(temp_dir, f"{Path(video_path).stem}.wav")
    cmd = [
        "ffmpeg", "-i", video_path, "-vn",
        "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
        "-y", out,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out


def _fmt(seconds: float) -> str:
    """秒を mm:ss に整形"""
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _ascii_hist(counts: List[int], width: int = 50) -> List[str]:
    """整数配列を横棒のASCIIヒストグラム行に変換"""
    peak = max(counts) if counts else 0
    lines = []
    for c in counts:
        n = int(round(c / peak * width)) if peak > 0 else 0
        lines.append("\u2588" * n)
    return lines


def _peak_offset(
    diffs: np.ndarray, bin_width: float = 0.5
) -> Tuple[float, int]:
    """オフセットの最頻ビン中心と、その近傍(±bin_width)の件数を返す"""
    if diffs.size == 0:
        return 0.0, 0
    lo, hi = float(diffs.min()), float(diffs.max())
    if hi - lo < bin_width:
        return float(np.median(diffs)), int(diffs.size)
    n_bins = max(1, int((hi - lo) / bin_width))
    hist, edges = np.histogram(diffs, bins=n_bins, range=(lo, hi))
    k = int(np.argmax(hist))
    center = (edges[k] + edges[k + 1]) / 2.0
    near = int(np.sum(np.abs(diffs - center) <= bin_width))
    return float(center), near


def diagnose(
    query_path: str, database: str,
    song_id: Optional[str], top_k: int, bin_sec: float,
) -> None:
    mimizam = create_mimizam_sqlite(db_path=database)
    try:
        # 音声の準備（動画なら抽出）
        tmp = None
        if query_path.lower().endswith((".wav", ".mp3", ".m4a", ".flac")):
            audio_path = query_path
        else:
            tmp = tempfile.mkdtemp(prefix="diag_audio_")
            audio_path = _extract_audio(query_path, tmp)

        qfps = mimizam.fingerprinter.fingerprint_file(audio_path)
        print(f"クエリ指紋数: {len(qfps)}")

        matches = mimizam.matcher.find_matches(qfps, top_k=top_k)
        if not matches:
            print("マッチなし")
            return

        print("\n=== 上位マッチ（現行スコア） ===")
        for i, m in enumerate(matches[:top_k], 1):
            sid = m["song_id"]
            song = mimizam.database.get_song(sid)
            title = song.title if song else sid
            print(f" {i}. {title} [{sid}] "
                  f"conf={m['confidence']:.3f} "
                  f"match={m['match_count']} "
                  f"offset={_fmt(abs(m['time_offset']))} "
                  f"scale={m.get('time_scale')} "
                  f"freq={m.get('freq_scale')}")

        target = song_id or matches[0]["song_id"]
        t_scale = matches[0].get("time_scale", 1.0)
        f_scale = matches[0].get("freq_scale", 1.0)
        song = mimizam.database.get_song(target)
        title = song.title if song else target
        duration = getattr(song, "duration", 0.0) or 0.0

        print(f"\n=== 診断対象: {title} [{target}] ===")
        print(f"DB長: {_fmt(duration) if duration else '不明'} / "
              f"適用スケール time={t_scale}, freq={f_scale}")

        # 上位マッチと同じスケールで全マッチペアを取得
        scaled = mimizam.matcher._scale_fingerprints(qfps, t_scale, f_scale)
        info = mimizam.matcher.get_detailed_match_info(scaled, target)
        positions = info["match_positions"]
        if not positions:
            print("該当楽曲のマッチペアなし")
            return

        q_times = np.array([p["query_time"] for p in positions], dtype=float)
        db_times = np.array([p["db_time"] for p in positions], dtype=float)
        diffs = q_times - db_times  # offset = query - db

        total = len(positions)
        median_off = float(np.median(diffs))
        peak_off, peak_near = _peak_offset(diffs, bin_width=0.5)

        # 中央値クラスタ（movie_searchの表示と同じ ±2s）
        med_mask = np.abs(diffs - median_off) <= 2.0
        med_db = db_times[med_mask]
        # 最頻ピーククラスタ（±0.5s）
        peak_mask = np.abs(diffs - peak_off) <= 0.5
        peak_db = db_times[peak_mask]

        # 最大整列クラスタ（matcher実装）
        pairs = [(p["query_time"], p["db_time"]) for p in positions]
        groups = mimizam.matcher._find_time_aligned_matches(
            pairs, mimizam.matcher.time_tolerance
        )
        largest = max(groups, key=len) if groups else []
        lg_db = np.array([db for _, db in largest], dtype=float)

        print(f"\n総マッチ: {total}")
        print(f"[中央値オフセット] {median_off:+.2f}s "
              f"→ DB {_fmt(median_off*-1 if median_off<0 else 0)} 付近, "
              f"クラスタ件数={int(med_mask.sum())}")
        if med_db.size:
            print(f"    中央値クラスタ DB時刻: "
                  f"{_fmt(med_db.min())} - {_fmt(med_db.max())}")
        print(f"[最頻ピークオフセット] {peak_off:+.2f}s, "
              f"近傍件数(±0.5s)={peak_near}")
        if peak_db.size:
            print(f"    ピーククラスタ DB時刻: "
                  f"{_fmt(peak_db.min())} - {_fmt(peak_db.max())}")
        print(f"[最大整列クラスタ] 件数={len(largest)}"
              f"({len(largest)/total:.1%})")
        if lg_db.size:
            print(f"    最大整列クラスタ DB時刻: "
                  f"{_fmt(lg_db.min())} - {_fmt(lg_db.max())} "
                  f"(中央 {_fmt(float(np.median(lg_db)))})")

        # DB時刻ヒストグラム
        print(f"\n=== DB時刻ヒストグラム (bin={bin_sec:.0f}s) ===")
        span = duration if duration > 0 else float(db_times.max()) + bin_sec
        n_bins = max(1, int(span / bin_sec))
        counts, edges = np.histogram(
            db_times, bins=n_bins, range=(0.0, n_bins * bin_sec)
        )
        bars = _ascii_hist(list(counts))
        for c, e0, bar in zip(counts, edges[:-1], bars):
            if c == 0:
                continue
            print(f" {_fmt(e0):>6} | {bar} {int(c)}")

        print("\n判定の見方:")
        print(" - 最大整列クラスタのDB時刻が真の一致位置。")
        print(" - それが中央値クラスタと食い違う場合、位置推定が"
              "中央値でノイズに引かれてズレている（＝表示バグ）。")
    finally:
        mimizam.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="音声オフセット分布の診断")
    ap.add_argument("query", help="クエリ動画/音声ファイル")
    ap.add_argument("--database", required=True, help="音声指紋DBパス")
    ap.add_argument("--song", default=None, help="診断対象song_id(既定=上位)")
    ap.add_argument("-k", "--top-k", type=int, default=10)
    ap.add_argument("--bin", type=float, default=5.0,
                    help="DB時刻ヒストグラムのビン幅(秒)")
    args = ap.parse_args()
    diagnose(args.query, args.database, args.song, args.top_k, args.bin)


if __name__ == "__main__":
    main()
