"""票の出どころを調べる: eval_b2.py を DIAG=1 で流したときの diag_{name}.npz を読み、映像ごとに一番票の多い組（時刻ずれ・回転・拡大率・縦横比の組）の票が、
クエリのどの位置（下 120px の文字の帯か、それ以外か）と、DB のどの版（元・横 ×1/1.33・×1/1.78）・時刻から来ているかを出す"""
import sys, numpy as np
VAR = ["元", "×1/1.33", "×1/1.78"]; DBV = "bbb,ed,sintel,tos,sprite,agent327".split(",")
for name in sys.argv[1:]:
    z = np.load(f"diag_{name}.npz"); key, qa, da, QP, DP, FI, NPTS = z["key"], z["qa"], z["da"], z["QP"], z["DP"], z["FI"], int(z["NPTS"])
    H = QP[..., 1].max(); band = H * 600 / 720  # クエリ 960x720 の下 120px（y≥600）は、長辺 1280 にそろえた座標で y≥800
    qv = QP[QP[..., 0] >= 0]; print(f"== {name}  クエリ点の y 最大 {H:.0f}、帯の中の点の割合 {np.mean(qv[:, 1] >= band):.2f}")
    k1 = np.unique(np.stack([key, qa], 1), axis=0); k2 = np.unique(np.stack([key, da], 1), axis=0)
    u1, c1 = np.unique(k1[:, 0], return_counts=True); u2, c2 = np.unique(k2[:, 0], return_counts=True)
    v = np.minimum(c1, np.where(np.isin(u1, u2), c2[np.searchsorted(u2, u1).clip(0, len(u2) - 1)], 0))
    vid = u1 >> 22
    for vi in np.unique(vid):
        i = np.nonzero(vid == vi)[0]; j = i[np.argmax(v[i])]; k = u1[j]
        if v[j] < 15: continue
        off = (((k >> 12) & 1023) - 512); rot, sc, an = (k >> 8) & 15, ((k >> 3) & 31) - 16, k & 7
        m = key == k; qs = np.unique(qa[m]); ds = np.unique(da[m])
        qpt = QP[qs // NPTS, qs % NPTS]; g = ds // NPTS; dpt = DP[g, ds % NPTS]; fi = FI[g]
        print(f" {DBV[vi]}: 票 {v[j]}（ずれの箱 {off} 回転 {rot} 拡大 {sc} 縦横比 {an}）  クエリ点 {len(qs)} のうち帯の中 {np.mean(qpt[:, 1] >= band):.2f}"
              f"  クエリ frame {np.unique(qs // NPTS).tolist()}")
        print("   DB の版:", {VAR[int(x)]: int(n) for x, n in zip(*np.unique(fi[:, 1], return_counts=True))},
              " DB 時刻:", sorted({round(float(t), 1) for t in fi[:, 2]})[:8], f" DB 点の y 中央値 {np.median(dpt[:, 1]):.0f}（その版の y 最大 {DP[g][..., 1].max():.0f}）")
