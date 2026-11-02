"""評価用クエリ（30秒クリップ×変換）を ffmpeg で作る"""
import json, os, random, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
S = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/src"); Q = os.path.expanduser(os.environ.get("VFEXP_DIR", "~/vfexp") + "/q")
DUR = {"bbb": 596, "ed": 653, "sintel": 888, "tos": 734, "sprite": 629, "agent327": 231,
       "llamigos": 150, "dillama": 146}
EXT = {"tos": "mov", "llamigos": "webm"}
POS = ["bbb", "ed", "sintel", "tos", "sprite", "agent327"]; NEG = ["llamigos", "dillama"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
CLIP = 30
def path(n): return f"{S}/{n}.{EXT.get(n, 'mp4')}"
VF = {
    "reenc480": "scale=-2:480",
    "low240": "scale=-2:240",
    "crop70": "crop=iw*0.7:ih*0.7,scale=-2:720",
    "color": "eq=brightness=0.08:contrast=1.3:saturation=0.5:gamma=1.2,scale=-2:720",
    "rot10": "scale=-2:720,rotate=10*PI/180:fillcolor=black",
    "aspect43_text": f"scale=960:720,setsar=1,drawbox=x=0:y=ih-120:w=iw:h=120:color=black@0.6:t=fill,drawtext=fontfile={FONT}:text='SAMPLE CHANNEL 2026':fontsize=56:fontcolor=white:x=40:y=h-95",
}
CRF = {"low240": 36}
def run(args):
    name, src, start, tf, bg, out = args
    if os.path.exists(out): return
    if tf in VF:
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(CLIP), "-i", src,
               "-vf", VF[tf], "-an", "-c:v", "libx264", "-crf", str(CRF.get(tf, 28)), "-preset", "veryfast", out]
    elif tf == "pip_half":  # 幅1/2（面積25%）を動く背景の右下へ
        fc = "[1:v]scale=1280:720,setsar=1[bg];[0:v]scale=640:-2[fg];[bg][fg]overlay=W-w-20:H-h-20"
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(CLIP), "-i", src,
               "-ss", "10", "-t", str(CLIP), "-i", bg, "-filter_complex", fc, "-an", "-c:v", "libx264", "-crf", "28",
               "-preset", "veryfast", "-t", str(CLIP), out]
    elif tf == "pip_third":  # 幅1/3（面積11%）を黒背景の中央へ
        fc = "color=black:s=1280x720:d=30[bg];[0:v]scale=426:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(CLIP), "-i", src,
               "-filter_complex", fc, "-an", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-t", str(CLIP), out]
    subprocess.run(cmd, check=True)
TFS = list(VF) + ["pip_half", "pip_third"]
def main():
    rnd = random.Random(42); jobs = []; meta = []
    for n in POS + NEG:
        for i in range(3):
            start = rnd.randint(20, DUR[n] - CLIP - 10) if n in POS else [5, 55, 105][i]
            for tf in TFS:
                bg = path("dillama" if n != "dillama" else "llamigos")
                out = f"{Q}/{n}_{i}_{tf}.mp4"
                jobs.append((n, path(n), start, tf, bg, out))
                meta.append({"file": out, "src": n, "start": start, "tf": tf, "positive": n in POS})
    json.dump(meta, open(f"{Q}/meta.json", "w"), indent=1)
    with ThreadPoolExecutor(4) as ex: list(ex.map(run, jobs))
    print("queries:", len(meta))
main()
