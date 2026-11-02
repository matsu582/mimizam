"""DB 映像のキーフレームを横に縮めて AKAZE をかけ直したキャッシュを作る（4:3 に押し縮められたクエリに合わせて DB 側に登録する版）
キーフレームの選び方は extract.py と同じ。出力は {name}__s75.npz（横 ×1/1.33）と {name}__s56.npz（横 ×1/1.78）。登録の時間も 1 本ずつ出す"""
import glob, json, os, sys, time
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from extract import akaze_frame, pack, C
from mimizam.src.video_fingerprinter import VideoFingerprintConfig, FrameSelector, _create_akaze
SQ = {"s75": 1 / 1.33, "s56": 1 / 1.78}

def job(name):
    path = [p for p in glob.glob(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + f"/src*/{name}.*")) if not p.endswith((".log", ".done"))][0]
    cv2.setNumThreads(1); akaze = _create_akaze()
    t0 = time.perf_counter(); frames = FrameSelector(VideoFingerprintConfig()).select_keyframes(path); t1 = time.perf_counter()
    for f, t, img in frames: akaze_frame(akaze, img)
    t2 = time.perf_counter()
    for k, s in SQ.items():
        out = f"{C}/{name}__{k}.npz"; items = []
        for f, t, img in frames:
            h, w = img.shape[:2]
            r = akaze_frame(akaze, cv2.resize(img, (int(round(w * s)), h), interpolation=cv2.INTER_AREA))
            if r is not None: items.append((f, t, r))
        np.savez(out, **{"full_" + kk: v for kk, v in pack(items).items()})
    t3 = time.perf_counter()
    return name, len(frames), t1 - t0, t2 - t1, t3 - t2

if __name__ == "__main__":
    names = os.environ.get("DBV", "bbb,ed,sintel,tos,sprite,agent327,hero,coffee,spring,cosmos").split(",")
    with ProcessPoolExecutor(4) as ex:
        for r in ex.map(job, names):
            print("%s キーフレーム %d 枚  選択 %.1fs  AKAZE 全面 %.1fs  縮めた 2 通り %.1fs" % r, flush=True)
