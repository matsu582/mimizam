"""ハッシュの作りだけを比べる: 特徴点を検出し直さず、座標だけ縦横比を変えて、元のハッシュが残る割合を数える"""
import os, numpy as np
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_b2.py")).read().split("t0 = time.perf_counter()")[0]
H = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp")); rng = np.random.default_rng(1)
res = {}
for mode, wb in [("sim", 6), ("aff", 5)]:
    os.environ.update(MODE=mode, WBITS=str(wb)); g = {"__name__": "x"}; exec(src, g)
    z = {n: np.load(f"{H}/cache/{n}.npz") for n in ["sintel", "bbb", "tos"]}
    fr = [f for n in z for f in g["frames"](z[n], "full_")]
    fr = [fr[i] for i in rng.choice(len(fr), 150, replace=False)]
    samp = np.vstack([f[1][:200] for f in fr[:60]])
    from sklearn.cluster import MiniBatchKMeans
    g["km"] = MiniBatchKMeans(1 << wb, random_state=0, n_init=3).fit(np.unpackbits(samp, axis=1).astype(np.float32))
    for sx, sy, noise in [(1, 1, 0), (1, 1, 1), (1, 1.33, 0), (1, 1.33, 1), (1, 1.8, 0), (1, 1.8, 1)]:
        kept = []
        for ts, d, kp in fr:
            q0 = g["quads"](g["km"], d, kp)
            if q0 is None: continue
            kp2 = kp.copy(); kp2[:, 0] *= sx; kp2[:, 1] *= sy
            kp2[:, :2] += rng.normal(0, noise, kp2[:, :2].shape) if noise else 0
            q1 = g["quads"](g["km"], d, kp2)
            h0 = g["hard"](q0); h1 = np.concatenate(g["soft"](q1))
            kept.append(np.isin(h0, h1).mean())
        res[(mode, sy, noise)] = np.mean(kept)
        print(f"{'B（3点・相似）' if mode=='sim' else 'B2（4点・アフィン）'} 縦方向×{sy} 座標の揺れ{noise}px: 元のハッシュが残る割合 {np.mean(kept):.2f}", flush=True)
