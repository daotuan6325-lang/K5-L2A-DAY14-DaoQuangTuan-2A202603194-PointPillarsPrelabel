"""Tro giup sua nhan Day 14 tren CVAT (khong tu tao hay sua hinh hoc nhan).

  bev   : anh BEV lon cho tung frame: so pp_id, mau theo muc nghi, dau "M#" o cum diem
          khong co hop (ung vien bi sot). In bang ung vien.
  notes : ghi goi y vao thuoc tinh `note` cua tung cuboid pre-label tren CVAT
          (chi doi chu trong `note`; toa do, kich thuoc, lop giu nguyen va duoc kiem lai).

Vi du:
  python tools/d14_assist.py bev   --data "$DataVF" --frames d14_194/frames_A.txt --boxes d14_194/pred_A.json --out out/assist_A
  python tools/d14_assist.py notes --data "$DataVF" --student 194 --task A --boxes d14_194/pred_A.json --host http://localhost:8080 --user admin
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import vf_common as vf  # noqa: E402
from scripts import vf_d14  # noqa: E402

RANGE = 50.0
SIZE = {  # (dai, rong, cao) chap nhan, noi rong tu Bang 4.3
    "Car": ((3.6, 5.5), (1.6, 2.2), (1.3, 2.2)),
    "Truck": ((4.0, 16.5), (1.7, 3.3), (1.6, 4.2)),
    "Bus": ((8.0, 19.0), (2.3, 2.8), (2.8, 3.7)),
    "Cyclist": ((1.4, 3.6), (0.4, 1.6), (1.2, 2.1)),
    "Pedestrian": ((0.25, 1.0), (0.25, 1.0), (0.9, 2.0)),
}
SEV_COLOR = {1: (255, 60, 60), 2: (255, 170, 0), 3: (255, 230, 0), 4: (90, 220, 90), 9: (120, 120, 120)}


# ----------------------------------------------------------------- hints

def box_hint(b: dict) -> tuple[int, str]:
    """(muc, chu): 1 nen xoa, 2 can kiem, 3 can sua, 4 co ve on, 9 ngoai pham vi."""
    dist = math.hypot(b["x"], b["y"])
    npts = b.get("npts", 999)
    if dist > RANGE:
        return 9, f"ngoai {RANGE:.0f}m: khong tinh diem"
    if dist < 2.5:
        return 1, "XOA?: tam sat LiDAR, co the la chinh xe minh"
    if npts < 5:
        return 1, f"XOA?: chi {npts} diem LiDAR, xem camera"
    issues = []
    rng = SIZE.get(b["label"])
    if rng:
        for name, v, (lo, hi) in zip(("dai", "rong", "cao"), (b["length"], b["width"], b["height"]), rng):
            if not lo <= v <= hi:
                issues.append(f"{name} {v:.1f}m la")
    if b["label"] == "Car" and (b["length"] > 5.3 or b["height"] > 2.1):
        issues.append("co the Truck/Bus")
    sc = b.get("score")
    if (sc is not None and sc < 0.3) or npts < 15:
        head = f"KIEM: score {sc:.2f}, {npts} diem" if sc is not None else f"KIEM: {npts} diem"
        return 2, head + (f"; {', '.join(issues)}" if issues else "")
    if issues:
        return 3, "SUA?: " + ", ".join(issues)
    return 4, "OK?: kiem dau xe + day hop"


def where(x: float, y: float) -> str:
    return f"{'truoc' if y < 0 else 'sau'} {abs(y):.0f}m, {'trai' if x > 0 else 'phai'} {abs(x):.0f}m"


# ------------------------------------------------------- miss candidates

def _inside_any(xy: np.ndarray, boxes: list[dict], pad: float = 0.5) -> np.ndarray:
    hit = np.zeros(len(xy), dtype=bool)
    for b in boxes:
        d = xy - np.array([b["x"], b["y"]])
        c, s = math.cos(b["yaw"]), math.sin(b["yaw"])
        u, v = d[:, 0] * c + d[:, 1] * s, -d[:, 0] * s + d[:, 1] * c
        hit |= (np.abs(u) <= b["length"] / 2 + pad) & (np.abs(v) <= b["width"] / 2 + pad)
    return hit


def height_above_ground(pts: np.ndarray, cell: float = 4.0) -> np.ndarray:
    ij = np.floor(pts[:, :2] / cell).astype(np.int64)
    key = ij[:, 0] * 100003 + ij[:, 1]
    order = np.argsort(key)
    ground = np.empty(len(pts))
    k_sorted, z_sorted = key[order], pts[order, 2]
    starts = np.r_[0, np.flatnonzero(np.diff(k_sorted)) + 1]
    ends = np.r_[starts[1:], len(k_sorted)]
    for a, e in zip(starts, ends):
        ground[order[a:e]] = np.percentile(z_sorted[a:e], 3)
    return pts[:, 2] - ground


def miss_candidates(pts: np.ndarray, boxes: list[dict], cell: float = 0.4, limit: int = 20) -> list[dict]:
    r = np.hypot(pts[:, 0], pts[:, 1])
    keep = (r > 3.0) & (r <= RANGE)
    pts = pts[keep]
    hag = height_above_ground(pts)
    tall = hag > 3.6
    band = (hag > 0.3) & (hag < 3.6) & ~_inside_any(pts[:, :2], boxes)
    p, h = pts[band], hag[band]
    if not len(p):
        return []
    ij = np.floor(p[:, :2] / cell).astype(np.int64)
    cells: dict[tuple, list[int]] = {}
    for n, (i, j) in enumerate(map(tuple, ij)):
        cells.setdefault((i, j), []).append(n)
    tall_cells = set(map(tuple, np.floor(pts[tall, :2] / cell).astype(np.int64)))
    seen, out = set(), []
    for start in cells:
        if start in seen:
            continue
        comp, q = [], deque([start])
        seen.add(start)
        while q:
            c = q.popleft()
            comp.append(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nb = (c[0] + di, c[1] + dj)
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        q.append(nb)
        idx = [n for c in comp for n in cells[c]]
        if len(idx) < 12:
            continue
        if sum(c in tall_cells for c in comp) > 0.3 * len(comp):
            continue  # cay / nha: co nhieu diem cao hon 3.6 m phia tren
        xy = p[idx, :2]
        centre = xy.mean(axis=0)
        cov = np.cov((xy - centre).T) if len(idx) > 2 else np.eye(2)
        w, vec = np.linalg.eigh(cov)
        axis = vec[:, 1]
        proj = (xy - centre) @ np.c_[axis, vec[:, 0]]
        length, width = np.ptp(proj[:, 0]) + cell, np.ptp(proj[:, 1]) + cell
        top = float(h[idx].max())
        if top < 1.0 or length > 13 or width > 4 or (length > 5 and width < 0.8):
            continue  # qua thap, qua lon, hoac hang rao / tuong dai mong
        if length < 1.2 and width < 1.2:
            guess = "Pedestrian?"
        elif length < 2.8:
            guess = "Cyclist?"
        elif length < 6:
            guess = "Car?" if top < 2.2 else "Truck?"
        else:
            guess = "Truck/Bus?"
        ground = float(np.median(p[idx, 2] - h[idx]))
        out.append({"x": float(centre[0]), "y": float(centre[1]), "length": float(length), "width": float(width),
                    "top": top, "npts": len(idx), "guess": guess,
                    "dist": float(math.hypot(*centre)), "yaw": float(math.atan2(axis[1], axis[0])),
                    "z": ground + top / 2, "height": top})
    out.sort(key=lambda m: -m["npts"])
    return out[:limit]


# -------------------------------------------------------------- drawing

def draw_bev(name: str, pts: np.ndarray, boxes: list[dict], misses: list[dict], path: Path, size: int = 1500):
    from PIL import Image, ImageDraw, ImageFont

    span = RANGE + 2
    s = size / (2 * span)
    cx = cy = size / 2

    def to_px(x, y):  # VF: x trai, y sau -> anh: dau xe huong len
        return cx - x * s, cy + y * s

    img = Image.new("RGB", (size, size + 40), (12, 12, 16))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        big = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = big = ImageFont.load_default()
    hag = height_above_ground(pts)
    r = np.hypot(pts[:, 0], pts[:, 1])
    sel = r <= span * 1.42
    px = np.c_[cx - pts[sel, 0] * s, cy + pts[sel, 1] * s].astype(int)
    hh = hag[sel]
    arr = np.asarray(img).copy()
    ok = (px[:, 0] >= 0) & (px[:, 0] < size) & (px[:, 1] >= 0) & (px[:, 1] < size)
    px, hh = px[ok], hh[ok]
    col = np.where(hh[:, None] < 0.3, np.array([70, 70, 80]),
                   np.where(hh[:, None] < 2.5, np.array([200, 220, 255]), np.array([120, 160, 120])))
    arr[px[:, 1], px[:, 0]] = col
    img = Image.fromarray(arr)
    dr = ImageDraw.Draw(img)
    for ring in (10, 20, 30, 40, 50):
        rr = ring * s
        dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(200, 40, 40) if ring == 50 else (60, 60, 70))
        dr.text((cx + 4, cy - rr + 2), f"{ring}m", fill=(150, 150, 160), font=font)
    dr.text((cx - 30, 4), "TRUOC (dau xe)", fill=(255, 255, 255), font=font)
    dr.text((6, cy), "TRAI", fill=(255, 255, 255), font=font)
    dr.text((size - 50, cy), "PHAI", fill=(255, 255, 255), font=font)
    for b in boxes:
        sev, _ = box_hint(b)
        c, sn = math.cos(b["yaw"]), math.sin(b["yaw"])
        hl, hw = b["length"] / 2, b["width"] / 2
        corners = [(b["x"] + u * c - v * sn, b["y"] + u * sn + v * c) for u, v in ((hl, hw), (-hl, hw), (-hl, -hw), (hl, -hw))]
        poly = [to_px(*p) for p in corners]
        color = SEV_COLOR[sev]
        dr.polygon(poly, outline=color, width=3)
        front = to_px(b["x"] + hl * c, b["y"] + hl * sn)
        dr.line([to_px(b["x"], b["y"]), front], fill=color, width=2)
        tx, ty = to_px(b["x"], b["y"])
        dr.text((tx + 6, ty - 18), f"{b.get('pp_id', '?')}{b['label'][0]}", fill=color, font=big)
    for k, m in enumerate(misses, 1):
        mx, my = to_px(m["x"], m["y"])
        rad = max(10, 0.5 * max(m["length"], 1.0) * s + 6)
        dr.ellipse([mx - rad, my - rad, mx + rad, my + rad], outline=(0, 200, 255), width=3)
        dr.text((mx + rad, my - rad), f"M{k}", fill=(0, 220, 255), font=big)
    legend = ("do=nen xoa  cam=can kiem  vang=can sua  xanh la=co ve on  xam=ngoai 50m  "
              "| M# xanh duong = cum diem khong co hop (ung vien sot)  | so=pp_id, chu=lop, vach=dau hop")
    dr.rectangle([0, size, size, size + 40], fill=(0, 0, 0))
    dr.text((8, size + 4), f"{name}   {legend}", fill=(230, 230, 230), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


# --------------------------------------------------------------- commands

def cmd_bev(args) -> int:
    names = vf_d14.read_frame_list(args.frames)
    rows = vf_d14.frame_rows(Path(args.data), names)
    pred = json.loads(Path(args.boxes).read_text(encoding="utf-8-sig"))["frames"]
    out = Path(args.out)
    report = []
    for row in rows:
        pts = vf_d14.load_points(row)
        boxes = pred.get(row["name"], [])
        misses = miss_candidates(pts, boxes)
        path = out / f"{row['name']}.png"
        draw_bev(row["name"], pts, boxes, misses, path)
        report.append(f"\n=== {row['name']}  -> {path}")
        report.append("Ung vien bi sot (cum diem khong co hop; CHI la goi y, xac nhan bang camera truoc khi ve):")
        for k, m in enumerate(misses, 1):
            report.append(f"  M{k:<2} {where(m['x'], m['y']):<20} cach {m['dist']:4.1f}m  "
                          f"~{m['length']:.1f}x{m['width']:.1f}m, cao {m['top']:.1f}m, {m['npts']} diem  -> {m['guess']}")
        report.append("Hop pre-label (sap theo muc uu tien):")
        for b in sorted(boxes, key=lambda b: (box_hint(b)[0], math.hypot(b["x"], b["y"]))):
            sev, text = box_hint(b)
            report.append(f"  pp_id {b.get('pp_id'):>3} {b['label']:<10} {where(b['x'], b['y']):<20} {text}")
    text = "\n".join(report)
    (out / "goi_y.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nDa ghi anh va {out / 'goi_y.txt'}")
    return 0


def cvat_boxes(args) -> dict[str, list[dict]]:
    """Hop hien tai tren CVAT (sau khi ban sua), kem pp_id neu la hop pre-label."""
    from scripts.vf_cvat import connect, find_tasks, d14_task_name

    name = d14_task_name(vf.normalize_student(args.student), args.task)
    client = connect(args.host, args.user, args.org)
    tasks = find_tasks(client, name)
    if len(tasks) != 1:
        raise SystemExit(f"Can dung 1 task ten {name}, thay {len(tasks)}.")
    task = tasks[0]
    frames = [vf.frame_name(*vf.parse_frame_name(f.name)) for f in task.get_meta().frames]
    labels = {lab.id: lab for lab in task.get_labels()}
    out: dict[str, list[dict]] = {f: [] for f in frames}
    new_no: dict[str, int] = {}
    for s in task.get_annotations().shapes:
        if getattr(s.type, "value", str(s.type)) != "cuboid":
            continue
        lab = labels[s.label_id]
        spec = {a.id: a.name for a in lab.attributes}
        vals = {spec.get(a.spec_id): a.value for a in s.attributes}
        b = vf.cuboid_from_cvat(s.points, lab.name, "lwh", s.occluded)
        f = frames[s.frame]
        pp = vals.get("pp_id", "")
        if pp == "":
            new_no[f] = new_no.get(f, 0) + 1
            pp = f"moi{new_no[f]}"
        b.update(pp_id=pp, score=float(vals.get("score") or 0) if vals.get("score") else None,
                 note=vals.get("note", ""), cvat_id=s.id)
        out[f].append(b)
    return out


def _crop_views(frame_row: dict, calib: dict, boxes: list[dict], target: dict, out_dir: Path, stem: str) -> list[str]:
    """Anh camera cat quanh `target`, hop dich vien vang day, hop khac vien mong."""
    from PIL import Image, ImageDraw, ImageFont
    from scripts import vf_qa

    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    files = []
    for cam, path in frame_row["cameras"]:
        if cam not in calib:
            continue
        pieces = vf_qa.project_box(target, calib[cam])
        if not pieces:
            continue
        img = Image.open(path).convert("RGB")
        W, H = img.size
        dr = ImageDraw.Draw(img)
        for b in boxes:
            if b is target:
                continue
            for pc in vf_qa.project_box(b, calib[cam]):
                dr.line(pc, fill=vf_qa._hex(vf.LABEL_COLORS.get(b["label"], "#ffffff")), width=2)
        for pc in pieces:
            dr.line(pc, fill=(255, 255, 0), width=5)
        us = [u for pc in pieces for u, _ in pc]
        vs = [v for pc in pieces for _, v in pc]
        u0, u1, v0, v1 = max(min(us), 0), min(max(us), W), max(min(vs), 0), min(max(vs), H)
        cw, ch = max(u1 - u0, 1), max(v1 - v0, 1)
        side_w, side_h = max(cw * 2.2, 420), max(ch * 2.2, 300)
        cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
        box = [int(max(cu - side_w / 2, 0)), int(max(cv - side_h / 2, 0)),
               int(min(cu + side_w / 2, W)), int(min(cv + side_h / 2, H))]
        crop = img.crop(box)
        if crop.width < 640:
            crop = crop.resize((640, int(crop.height * 640 / crop.width)))
        elif crop.width > 900:
            crop = crop.resize((900, int(crop.height * 900 / crop.width)))
        ImageDraw.Draw(crop).text((8, 6), cam, fill=(255, 255, 0), font=font)
        name = f"{stem}_{cam}.jpg"
        crop.save(out_dir / name, quality=85)
        files.append(name)
    return files


VIEWER_HTML = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>D14 Box Viewer</title>
<style>
:root{--bg:#111318;--fg:#e8e8ea;--mut:#9aa0a6;--card:#1b1e25;--acc:#ffd400}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,Segoe UI,Arial}
header{display:flex;gap:8px;align-items:center;padding:8px 12px;background:#000;position:sticky;top:0;z-index:2;flex-wrap:wrap}
header button{background:var(--card);color:var(--fg);border:1px solid #333;padding:6px 12px;border-radius:6px;cursor:pointer}
header button.on{border-color:var(--acc);color:var(--acc)}
header input{background:var(--card);color:var(--fg);border:1px solid #333;padding:6px;border-radius:6px;width:150px}
main{display:grid;grid-template-columns:minmax(300px,48%) 1fr;gap:12px;padding:12px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.map{position:relative}.map img{width:100%;display:block}.map svg{position:absolute;inset:0;width:100%;height:100%}
.map polygon,.map circle{fill:rgba(255,255,255,0);stroke:none;cursor:pointer;pointer-events:all}
.map .sel{stroke:var(--acc);stroke-width:8;fill:rgba(255,212,0,.15)}
.info{background:var(--card);padding:10px;border-radius:8px;margin-bottom:10px}
.info b{color:var(--acc)} .mut{color:var(--mut)}
.cams img{max-width:100%;display:block;margin:0 0 10px;border-radius:6px}
.list{max-height:240px;overflow:auto;font-size:13px;margin-top:8px}
.list div{padding:2px 6px;cursor:pointer;border-radius:4px}.list div:hover{background:#2a2e38}
</style></head><body>
<header><span id="frames"></span><input id="q" placeholder="pp_id / M3 / moi1"><span class="mut" id="src"></span></header>
<main><div><div class="map"><img id="bev"><svg id="svg"></svg></div>
<div class="list" id="list"></div></div><div><div class="info" id="info">Bam vao mot hop tren ban do (hoac go pp_id).</div><div class="cams" id="cams"></div></div></main>
<script>
const D=__DATA__;let cur=Object.keys(D.frames)[0],sel=null;
const $=id=>document.getElementById(id);
$('src').textContent='Nguon: '+D.source;
function frames(){$('frames').innerHTML='';for(const f in D.frames){const b=document.createElement('button');b.textContent=f;b.className=f===cur?'on':'';b.onclick=()=>{cur=f;sel=null;draw()};$('frames').appendChild(b)}}
function draw(){frames();const F=D.frames[cur];$('bev').src=F.bev;const s=$('svg');s.setAttribute('viewBox','0 0 '+D.w+' '+D.h);s.innerHTML='';
 for(const it of F.items){let e;if(it.poly){e=document.createElementNS('http://www.w3.org/2000/svg','polygon');e.setAttribute('points',it.poly.map(p=>p.join(',')).join(' '))}
 else{e=document.createElementNS('http://www.w3.org/2000/svg','circle');e.setAttribute('cx',it.c[0]);e.setAttribute('cy',it.c[1]);e.setAttribute('r',it.r)}
 if(sel===it.key)e.setAttribute('class','sel');e.onclick=()=>pick(it.key);s.appendChild(e)}
 $('list').innerHTML=F.items.map(it=>`<div onclick="pick('${it.key}')"><b>${it.key}</b> ${it.label} <span class=mut>${it.where}</span> ${it.hint||''}</div>`).join('');
 show()}
function pick(k){sel=k;draw()}
function show(){const it=D.frames[cur].items.find(i=>i.key===sel);if(!it){$('cams').innerHTML='';return}
 $('info').innerHTML=`<b>${it.key}</b> &nbsp; ${it.label} &nbsp; <span class=mut>${it.where}</span><br>${it.dims}<br>${it.hint||''}`+(it.imgs.length?'':'<br><span class=mut>Khong camera nao thay hop nay (co the nam sau xe, qua cao/thap, hoac ngoai goc nhin).</span>');
 $('cams').innerHTML=it.imgs.map(u=>`<img src="${u}" loading="lazy">`).join('')}
$('q').onkeydown=e=>{if(e.key==='Enter'){const v=e.target.value.trim();const it=D.frames[cur].items.find(i=>i.key.toLowerCase()===v.toLowerCase()||i.key==='#'+v);if(it)pick(it.key)}};
draw();
</script></body></html>"""


def cmd_viewer(args) -> int:
    from scripts import vf_qa

    names = vf_d14.read_frame_list(args.frames)
    rows = vf_d14.frame_rows(Path(args.data), names)
    if args.from_cvat:
        boxes_by = cvat_boxes(args)
        source = f"CVAT task {args.task} (hop hien tai, gom ca hop ban da sua/them)"
    else:
        boxes_by = json.loads(Path(args.boxes).read_text(encoding="utf-8-sig"))["frames"]
        source = f"file {args.boxes} (pre-label goc)"
    out = Path(args.out)
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    size, span = 1500, RANGE + 2
    sc = size / (2 * span)
    to_px = lambda x, y: [round(size / 2 - x * sc, 1), round(size / 2 + y * sc, 1)]  # noqa: E731
    data = {"source": source, "w": size, "h": size + 40, "frames": {}}
    calibs: dict[int, dict] = {}
    for row in rows:
        f = row["name"]
        if row["seq"] not in calibs:
            calibs[row["seq"]] = vf_qa.load_calib(Path(args.data) / f"sequence_{row['seq']:02d}")
        calib = calibs[row["seq"]]
        pts = vf_d14.load_points(row)
        boxes = boxes_by.get(f, [])
        for b in boxes:
            if "npts" not in b:
                from vf_pp.core import points_in_box
                b["npts"] = points_in_box(pts, b)
        misses = miss_candidates(pts, boxes)
        bev_name = f"{f}_bev.png"
        draw_bev(f, pts, boxes, misses, img_dir / bev_name, size=size)
        items = []
        for b in boxes:
            key = f"#{b.get('pp_id')}"
            sev, hint = box_hint(b)
            c, sn = math.cos(b["yaw"]), math.sin(b["yaw"])
            hl, hw = b["length"] / 2 + 0.6, b["width"] / 2 + 0.6
            poly = [to_px(b["x"] + u * c - v * sn, b["y"] + u * sn + v * c)
                    for u, v in ((hl, hw), (-hl, hw), (-hl, -hw), (hl, -hw))]
            imgs = _crop_views(row, calib, boxes, b, img_dir, f"{f}_{str(b.get('pp_id')).replace('#', '')}")
            items.append({"key": key, "label": b["label"], "where": where(b["x"], b["y"]),
                          "dims": f"{b['length']:.2f} x {b['width']:.2f} x {b['height']:.2f} m (dai x rong x cao), "
                                  f"{b.get('npts', '?')} diem, score {b.get('score') if b.get('score') is not None else '-'}",
                          "hint": f"{sev}-{hint}", "poly": poly, "imgs": [f"img/{u}" for u in imgs], "sev": sev})
        for k, m in enumerate(misses, 1):
            pseudo = {"x": m["x"], "y": m["y"], "z": m["z"], "length": max(m["length"], 0.6),
                      "width": max(m["width"], 0.6), "height": m["height"], "yaw": m["yaw"], "label": "?"}
            imgs = _crop_views(row, calib, boxes, pseudo, img_dir, f"{f}_M{k}")
            items.append({"key": f"M{k}", "label": m["guess"], "where": where(m["x"], m["y"]),
                          "dims": f"cum ~{m['length']:.1f} x {m['width']:.1f} m, cao {m['top']:.1f} m, {m['npts']} diem",
                          "hint": "UNG VIEN SOT: chi ve hop neu camera thay ro xe/nguoi",
                          "c": to_px(m["x"], m["y"]), "r": max(14, 0.5 * max(m["length"], 1) * sc + 8),
                          "imgs": [f"img/{u}" for u in imgs], "sev": 0})
        items.sort(key=lambda it: (it["sev"] if it["sev"] else 2.5, it["key"]))
        data["frames"][f] = {"bev": f"img/{bev_name}", "items": items}
        print(f"{f}: {len(boxes)} hop, {len(misses)} ung vien sot")
    html = VIEWER_HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Mo trong trinh duyet: {(out / 'index.html').resolve()}")
    return 0


def cmd_notes(args) -> int:
    from cvat_sdk import models
    from scripts.vf_cvat import connect, find_tasks, d14_task_name

    pred = json.loads(Path(args.boxes).read_text(encoding="utf-8-sig"))["frames"]
    name = d14_task_name(vf.normalize_student(args.student), args.task)
    client = connect(args.host, args.user, args.org)
    tasks = find_tasks(client, name)
    if len(tasks) != 1:
        raise SystemExit(f"Can dung 1 task ten {name}, thay {len(tasks)}.")
    task = tasks[0]
    frames = [vf.frame_name(*vf.parse_frame_name(f.name)) for f in task.get_meta().frames]
    labels = {lab.id: lab for lab in task.get_labels()}
    ann = task.get_annotations()
    backup = Path(args.backup or f"out/cvat_backup_{name}.json")
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(ann.to_dict(), default=str, ensure_ascii=False), encoding="utf-8")
    by_key = {(f, str(b.get("pp_id"))): b for f, bs in pred.items() for b in bs}
    updates, before = [], {}
    for s in ann.shapes:
        lab = labels[s.label_id]
        spec = {a.id: a.name for a in lab.attributes}
        vals = {spec.get(a.spec_id): a.value for a in s.attributes}
        pp = vals.get("pp_id", "")
        b = by_key.get((frames[s.frame], pp)) if pp != "" else None
        if b is None:
            continue
        sev, text = box_hint(b)
        note = f"{sev}-{text}"
        if vals.get("note") == note:
            continue
        before[s.id] = (list(s.points), s.label_id, s.frame)
        attrs = [models.AttributeValRequest(spec_id=a.spec_id, value=(note if spec.get(a.spec_id) == "note" else a.value))
                 for a in s.attributes]
        if "note" not in vals:
            note_id = next(i for i, n in spec.items() if n == "note")
            attrs.append(models.AttributeValRequest(spec_id=note_id, value=note))
        updates.append(models.LabeledShapeRequest(
            id=s.id, type=s.type, frame=s.frame, label_id=s.label_id, points=list(s.points),
            occluded=s.occluded, z_order=s.z_order, rotation=s.rotation, group=s.group,
            source=s.source, attributes=attrs))
    if not updates:
        print("Khong co gi can cap nhat.")
        return 0
    task.update_annotations(models.PatchedLabeledDataRequest(shapes=updates))
    after = {s.id: (list(s.points), s.label_id, s.frame) for s in task.get_annotations().shapes}
    changed = [i for i, v in before.items() if after.get(i) != v]
    if changed:
        raise SystemExit(f"CANH BAO: hinh hoc cua {changed} khac truoc khi cap nhat. Ban sao luu: {backup}")
    print(f"Da ghi goi y vao `note` cua {len(updates)} cuboid trong {name} (hinh hoc giu nguyen). Sao luu: {backup}")
    print("Tai lai (F5) trang job tren CVAT de thay `note` trong DETAILS.")
    return 0


def main() -> int:
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bev")
    b.add_argument("--data", required=True)
    b.add_argument("--frames", required=True)
    b.add_argument("--boxes", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_bev)
    v = sub.add_parser("viewer")
    v.add_argument("--data", required=True)
    v.add_argument("--frames", required=True)
    v.add_argument("--boxes", help="file pred (khi khong dung --from-cvat)")
    v.add_argument("--out", required=True)
    v.add_argument("--from-cvat", action="store_true", help="lay hop hien tai tu CVAT")
    v.add_argument("--student")
    v.add_argument("--task", choices=["A", "B"])
    v.add_argument("--host")
    v.add_argument("--user")
    v.add_argument("--org")
    v.set_defaults(func=cmd_viewer)
    n = sub.add_parser("notes")
    n.add_argument("--student", required=True)
    n.add_argument("--task", required=True, choices=["A", "B"])
    n.add_argument("--boxes", required=True)
    n.add_argument("--host", required=True)
    n.add_argument("--user", required=True)
    n.add_argument("--org")
    n.add_argument("--backup")
    n.set_defaults(func=cmd_notes)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
