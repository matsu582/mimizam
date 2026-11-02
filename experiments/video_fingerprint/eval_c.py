"""現状(V0/V1)と C 案（bit VLAD / 2値指紋）を mimizam の実経路（ANN投票→RANSAC→区間）で評価する"""
import json, logging, math, os, sys, time
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")))  # mimizam の親
from mimizam.src.video_fingerprinter import VLADEncoder, VideoFingerprintConfig
from mimizam.src.video_database import VideoFingerprintDatabase
from mimizam.src.database_base import Video
from mimizam.src.mimizam import Mimizam
logging.basicConfig(level=logging.WARNING)
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp")); C = f"{H}/cache"
DBV = os.environ.get("DBV", "bbb,ed,sintel,tos,sprite,agent327").split(",")
variant = sys.argv[1]  # V0 / V1 / C1 / C2 / C2b
BIN = variant in ("C2", "C2b")
BITS = variant in ("C1", "C2b")

def frames(z, pre):
    off = z[pre + "off"]; d = z[pre + "desc"]; k = z[pre + "kp"]
    return [(int(z[pre + "fidx"][i]), float(z[pre + "ts"][i]), d[off[i]:off[i + 1]], k[off[i]:off[i + 1], :2])
            for i in range(len(off) - 1)]

def feat(d):
    return np.unpackbits(d, axis=1).astype(np.float32) if BITS else d.astype(np.float32)

enc = VLADEncoder(VideoFingerprintConfig())
t0 = time.perf_counter()
caches = {n: np.load(f"{C}/{n}.npz") for n in DBV}
if variant in ("V0", "C2"):
    enc.load_model(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../model/codebook_model.npz"))
else:  # 登録映像で学習（add_video の自動学習と同じ前提）。V1 と C1 は同じフレームで学習
    rnd = np.random.default_rng(0); train = []
    for n in DBV:
        fr = frames(caches[n], "full_")
        for i in rnd.choice(len(fr), min(400, len(fr)), replace=False):
            train.append(feat(fr[i][2]))
    enc.train(train)
train_s = time.perf_counter() - t0

def encode(d):
    v = enc.encode_frame(feat(d))
    if BIN:  # PCA 出力の符号だけを残す 512bit 指紋。±1/√D にすればコサイン=1-2·Hamming/D
        v = np.where(v >= 0, 1.0, -1.0).astype(np.float32) / math.sqrt(len(v))
    return v

def fp(fr):
    fps = [(f, t, encode(d)) for f, t, d, k in fr if len(d) >= 5]
    raw = [(f, t, np.hstack([k.astype(np.float32), d.astype(np.float32)])) for f, t, d, k in fr if len(d) >= 5]
    return fps, raw

os.makedirs(f"{H}/db", exist_ok=True)
dbp = f"{H}/db/{os.environ.get('TAG', variant)}.db"
if os.path.exists(dbp): os.remove(dbp)
vdb = VideoFingerprintDatabase(db_path=dbp)
if BIN:  # 連続値コサインの閾値 t を符号一致率の期待値 1-2·acos(t)/π に換算
    conv = lambda t: 1 - 2 * math.acos(t) / math.pi
    vdb._frame_match_cand_threshold = conv(vdb._frame_match_cand_threshold)
    orig_c, orig_m = vdb.search_frame_candidates, vdb.search_video_with_frame_matching
    vdb.search_frame_candidates = lambda q, top_k=10, k_per_query=10, sim_threshold=0.4: orig_c(q, top_k, k_per_query, conv(sim_threshold))
    vdb.search_video_with_frame_matching = lambda q, ids, threshold=0.5, query_raw=None: orig_m(q, ids, conv(threshold), query_raw)
t0 = time.perf_counter(); n_frames = 0
for n in DBV:
    fps, raw = fp(frames(caches[n], "full_")); n_frames += len(fps)
    vdb.add_video(Video(id=n, title=n, file_path=n, duration=None, frame_count=len(fps)))
    vdb.add_frame_fingerprints(n, fps)
    vdb.add_frame_descriptors(n, raw)
index_s = time.perf_counter() - t0
dim = len(fps[0][2])
m = Mimizam.__new__(Mimizam); m.logger = logging.getLogger("eval")

out = []
for q in json.load(open(os.path.expanduser(os.environ.get("META", f"{H}/q/meta.json")))):
    name = os.path.basename(q["file"])[:-4]
    z = np.load(f"{C}/{name}.npz")
    qf, qr = fp(frames(z, "full_"))
    t0 = time.perf_counter()
    res = m._match_and_rank(vdb, qf, qr, 5)[:5] if qf else []
    t1 = time.perf_counter()
    ann = vdb.search_frame_candidates(qf, top_k=10) if qf else []
    ann_s = time.perf_counter() - t1
    if len(z["pip_off"]) > 1:
        pf, pr = fp(frames(z, "pip_"))
        if pf:
            pres = m._match_and_rank(vdb, pf, pr, 5)
            res = Mimizam._merge_pip_results(res, pres, 5) if pres else res
    qs = time.perf_counter() - t0 - ann_s
    top = res[0] if res else None
    regs = top.get("match_details", {}).get("regions", []) if top else []
    out.append(dict(q, name=name, sec=qs, top=top["video_id"] if top else None, score=top["similarity"] if top else 0.0,
                    pos_ok=any(r["db_start"] <= q["start"] + 35 and r["db_end"] >= q["start"] - 5 for r in regs),
                    ann_top=ann[0]["video_id"] if ann else None,
                    ann_score=(ann[0]["votes"] / len(qf)) if ann else 0.0,
                    ann_sim=ann[0]["similarity"] if ann else 0.0, ann_sec=ann_s))
size = os.path.getsize(dbp)
json.dump(dict(variant=variant, train_s=train_s, index_s=index_s, db_bytes=size, n_frames=n_frames, dim=dim,
               fp_bytes_per_frame=(dim // 8 if BIN else dim * 4), results=out), open(f"{H}/res_{os.environ.get('TAG', variant)}.json", "w"))
print(variant, "done", size)
