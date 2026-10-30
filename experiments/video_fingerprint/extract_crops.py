"""クエリの一部（幅・高さ 1/2 の窓）を切り出して拡大し、AKAZE をかけ直したキャッシュを作る（PiP を検出せずに探す）
窓の左上は幅・高さの 0, 1/4, 1/2 の 3×3 = 9 通り。キーフレームの選び方は extract.py と同じ。"""
import json, os, sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from extract import akaze_frame, pack, C
from mimizam.src.video_fingerprinter import VideoFingerprintConfig, FrameSelector, _create_akaze
POS = [(ix, iy) for iy in range(3) for ix in range(3)]

def job(args):
    path, name = args
    outs = {p: f"{C}/{name}__c{p[0]}{p[1]}.npz" for p in POS}
    if all(os.path.exists(o) for o in outs.values()): return name
    cv2.setNumThreads(1); akaze = _create_akaze()
    frames = FrameSelector(VideoFingerprintConfig()).select_keyframes(path)
    for (ix, iy), out in outs.items():
        items = []
        for f, t, img in frames:
            h, w = img.shape[:2]; x0, y0 = ix * w // 4, iy * h // 4
            r = akaze_frame(akaze, img[y0:y0 + h // 2, x0:x0 + w // 2])
            if r is not None: items.append((f, t, r))
        np.savez(out, **{"full_" + k: v for k, v in pack(items).items()})
    return name

if __name__ == "__main__":
    jobs = [(m["file"], os.path.basename(m["file"])[:-4]) for m in json.load(open(os.path.expanduser(os.environ.get("META", os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json"))))]
    with ProcessPoolExecutor(8) as ex:
        for i, n in enumerate(ex.map(job, jobs)):
            if i % 20 == 0: print("done", i, n, flush=True)
