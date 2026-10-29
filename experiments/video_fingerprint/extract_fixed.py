"""決まった間隔（STEP 秒ごと）で取ったフレームの AKAZE キャッシュを作る（キーフレームの選び方に頼らない時間ハッシュ用）
出力は cache_fx/{name}.npz（full_*）。LONG を指定すると AKAZE にかける長辺を変え、cache_fx{LONG}/ に出す。DB 映像は横に縮めた 2 版（__s75・__s56）も作る（extract_dbstretch.py と同じ倍率）"""
import json, os, sys, time
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))
from extract import pack
from mimizam.src.video_fingerprinter import _create_akaze, normalize_frame
STEP = float(os.environ.get("STEP", 0.5))
LONG = int(os.environ.get("LONG", 1280))
CF = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/cache_fx" + ("" if LONG == 1280 else str(LONG))); os.makedirs(CF, exist_ok=True)
def akaze_frame(akaze, img):
    """extract.py と同じ（長辺だけ LONG に変える）"""
    g = normalize_frame(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), LONG, allow_upscale=True)
    kps, desc = akaze.detectAndCompute(g, None)
    if desc is None or len(desc) == 0: return None
    return desc, np.array([[k.pt[0], k.pt[1], k.size, k.angle, k.response] for k in kps], np.float32)

SQ = {"s75": 1 / 1.33, "s56": 1 / 1.78}

def job(args):
    path, name, stretch = args
    if os.path.exists(f"{CF}/{name}.npz"): return name, 0, 0.0
    cv2.setNumThreads(1); akaze = _create_akaze()
    cap = cv2.VideoCapture(path); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    vers = {"": []} | ({k: [] for k in SQ} if stretch else {}); fi = 0; nxt = 0.0; t0 = time.perf_counter(); n = 0
    while cap.grab():
        t = fi / fps
        if t + 1e-6 >= nxt:
            ok, img = cap.retrieve()
            if ok:
                n += 1; nxt += STEP
                for k in vers:
                    im = img if not k else cv2.resize(img, (int(round(img.shape[1] * SQ[k])), img.shape[0]), interpolation=cv2.INTER_AREA)
                    r = akaze_frame(akaze, im)
                    if r is not None: vers[k].append((fi, t, r))
        fi += 1
    cap.release()
    for k, items in vers.items():
        np.savez(f"{CF}/{name}{'__' + k if k else ''}.npz", **{"full_" + kk: v for kk, v in pack(items).items()})
    return name, n, time.perf_counter() - t0

if __name__ == "__main__":
    db = [(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + f"/{f}"), os.path.basename(f).split(".")[0], True) for f in
          "src/bbb.mp4,src/ed.mp4,src/sintel.mp4,src/tos.mov,src/sprite.mp4,src/agent327.mp4,src2/hero.mp4,src2/coffee.mp4,src2/spring.mp4,src2/cosmos.mp4".split(",")]
    qs = [(m["file"], os.path.basename(m["file"])[:-4], False) for mf in ("q", "q2") for m in json.load(open(os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + f"/{mf}/meta.json")))]
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(job, db + qs):
            print("%s %d 枚 %.1fs" % r, flush=True)
