"""クエリを横に伸ばしてから AKAZE をかけ直したキャッシュを作る（キーフレームの選び方は extract.py と同じ）"""
import json, os, sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from extract import akaze_frame, pack, C
from mimizam.src.video_fingerprinter import VideoFingerprintConfig, FrameSelector, _create_akaze
STRETCH = [float(x) for x in os.environ.get("STRETCH", "1.33,1.78").split(",")]

def job(args):
    path, name = args
    outs = {s: f"{C}/{name}__x{int(round(s * 100))}.npz" for s in STRETCH}
    if all(os.path.exists(o) for o in outs.values()): return name
    cv2.setNumThreads(1); akaze = _create_akaze()
    frames = FrameSelector(VideoFingerprintConfig()).select_keyframes(path)
    for s, out in outs.items():
        items = []
        for f, t, img in frames:
            h, w = img.shape[:2]
            r = akaze_frame(akaze, cv2.resize(img, (int(round(w * s)), h), interpolation=cv2.INTER_LINEAR))
            if r is not None: items.append((f, t, r))
        np.savez(out, **{"full_" + k: v for k, v in pack(items).items()})
    return name

if __name__ == "__main__":
    jobs = [(m["file"], os.path.basename(m["file"])[:-4]) for m in json.load(open(os.path.expanduser(os.environ.get("META", os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json"))))]
    with ProcessPoolExecutor(8) as ex:
        for i, n in enumerate(ex.map(job, jobs)):
            if i % 20 == 0: print("done", i, n, flush=True)
