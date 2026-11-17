"""全映像（DB映画・クエリ）のキーフレーム AKAZE をキャッシュする（全方式で共通に使う）"""
import json, os, sys, glob
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))  # mimizam の親
from mimizam.src.video_fingerprinter import (VideoFingerprintConfig, FrameSelector, normalize_frame, _create_akaze)
from mimizam.src.pip_detector import detect_pip_regions, sample_frames_from_video
C = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/cache"); os.makedirs(C, exist_ok=True)

def akaze_frame(akaze, img, gray=False):
    g = img if gray else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = normalize_frame(g, 1280, allow_upscale=True)
    kps, desc = akaze.detectAndCompute(g, None)
    if desc is None or len(desc) == 0:
        return None
    kp = np.array([[k.pt[0], k.pt[1], k.size, k.angle, k.response] for k in kps], np.float32)
    return desc, kp

def pack(items):
    fidx, ts, descs, kps, offs = [], [], [], [], [0]
    for f, t, (d, k) in items:
        fidx.append(f); ts.append(t); descs.append(d); kps.append(k); offs.append(offs[-1] + len(d))
    if not descs:
        return dict(fidx=np.zeros(0, np.int64), ts=np.zeros(0), desc=np.zeros((0, 61), np.uint8), kp=np.zeros((0, 5), np.float32), off=np.zeros(1, np.int64))
    return dict(fidx=np.array(fidx), ts=np.array(ts), desc=np.vstack(descs), kp=np.vstack(kps), off=np.array(offs))

def job(args):
    path, name, do_pip = args
    out = f"{C}/{name}.npz"
    if os.path.exists(out):
        return name
    cv2.setNumThreads(1)
    akaze = _create_akaze()
    frames = FrameSelector(VideoFingerprintConfig()).select_keyframes(path)
    items = []
    for f, t, img in frames:
        r = akaze_frame(akaze, img)
        if r is not None:
            items.append((f, t, r))
    d = {"full_" + k: v for k, v in pack(items).items()}
    region = np.zeros(5)
    if do_pip:  # VideoFingerprinter.fingerprint_pip_regions と同じ手順
        regions = detect_pip_regions(sample_frames_from_video(path, 30))
        regions = sorted(regions, key=lambda r: r.pip_score, reverse=True)[:1]
        pitems = []
        if regions:
            rg = regions[0]; region = np.array([rg.x, rg.y, rg.w, rg.h, rg.pip_score])
            cap = cv2.VideoCapture(path); total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            idxs = list(range(0, total, max(1, int(fps * 2))))
            if len(idxs) > 60:
                idxs = idxs[::len(idxs) // 60][:60]
            for fi in idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, fi); ok, fr = cap.read()
                if not ok: continue
                fh, fw = fr.shape[:2]
                x1, y1 = max(0, min(rg.x, fw - 1)), max(0, min(rg.y, fh - 1)); x2, y2 = min(rg.x + rg.w, fw), min(rg.y + rg.h, fh)
                if x2 - x1 < 30 or y2 - y1 < 30: continue
                r = akaze_frame(akaze, fr[y1:y2, x1:x2])
                if r is not None and len(r[0]) >= 5:
                    pitems.append((fi, fi / fps, r))
            cap.release()
        d.update({"pip_" + k: v for k, v in pack(pitems).items()})
    np.savez(out, region=region, **d)
    return name

if __name__ == "__main__":
    DBF = os.environ.get("DBF", "src/bbb.mp4,src/ed.mp4,src/sintel.mp4,src/tos.mov,src/sprite.mp4,src/agent327.mp4").split(",")
    jobs = [(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + f"/{f}"), os.path.basename(f).split(".")[0], False) for f in DBF]
    if sys.argv[1:] != ["db"]:
      jobs += [(m["file"], os.path.basename(m["file"])[:-4], True) for m in json.load(open(os.path.expanduser(os.environ.get("META", os.environ.get("VFEXP_DIR", "~/vfexp") + "/q/meta.json"))))]
    with ProcessPoolExecutor(8) as ex:
        for n in ex.map(job, jobs):
            print("done", n, flush=True)
