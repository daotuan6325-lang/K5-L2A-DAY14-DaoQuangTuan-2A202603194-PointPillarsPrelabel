"""Dua HOP NHAP (AI_DRAFT) len CVAT cho cac cum diem LiDAR chua co hop.

Chi THEM hop moi; khong xoa, khong sua hop dang co. Moi hop nhap co
note="AI_DRAFT - can kiem" de nguoi gan nhan kiem bang camera roi giu/sua/xoa.
Hop nhap KHONG phai nhan da kiem: phai mo CVAT kiem tung hop truoc khi xuat ref_*.json.

  plan : in danh sach hop nhap se them (khong ghi CVAT)
  push : sao luu annotation hien tai vao out/ roi them hop nhap

Vi du:
  python tools/d14_draft.py plan --data "$DataVF" --student 194 --task A --host http://localhost:8080 --user admin
  python tools/d14_draft.py push --data "$DataVF" --student 194 --task A --host http://localhost:8080 --user admin
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from scripts import vf_common as vf  # noqa: E402
from scripts import vf_d14  # noqa: E402
from scripts.vf_cvat import connect, cuboid_points, d14_task_name, find_tasks  # noqa: E402
import d14_assist as da  # noqa: E402

NOTE = "AI_DRAFT - can kiem"
# Kich thuoc toi thieu dat cho hop nhap (LiDAR chi thay mot phia nen cum diem thuong ngan hon vat that)
MIN_DIMS = {"Car": (3.9, 1.7, 1.45), "Truck": (5.5, 2.1, 2.4), "Bus": (10.0, 2.5, 3.0),
            "Cyclist": (1.7, 0.6, 1.6), "Pedestrian": (0.6, 0.6, 1.6)}


def classify(m: dict) -> str | None:
    """Lop hop ly theo kich thuoc cum diem; None = co ve la cot/cay/tuong -> bo qua."""
    L, W, H = m["length"], m["width"], m["top"]
    if H < 1.1 or H > 3.6:
        return None
    if L <= 1.3 and W <= 1.3:
        return "Pedestrian" if H <= 2.0 else None
    if L <= 2.6 and W <= 1.3:
        return "Cyclist" if H <= 2.0 else None
    if 2.6 < L <= 5.8 and 1.2 <= W <= 2.4:
        return "Car" if H <= 2.1 else "Truck"
    if 5.8 < L <= 12.5 and 1.8 <= W <= 3.4 and H >= 2.0:
        return "Bus" if L >= 9.5 and H >= 2.8 else "Truck"
    return None


def drafts_for(args) -> dict[str, list[dict]]:
    current = da.cvat_boxes(args)
    rows = vf_d14.frame_rows(Path(args.data), list(current))
    out = {}
    for row in rows:
        f = row["name"]
        pts = vf_d14.load_points(row)
        boxes = current[f]
        res = []
        for m in da.miss_candidates(pts, boxes, limit=60):
            lab = classify(m)
            if lab is None or m["npts"] < args.min_pts:
                continue
            l0, w0, h0 = MIN_DIMS[lab]
            L, W = max(m["length"], l0), max(m["width"], w0)
            H = max(m["top"], h0)
            ground = m["z"] - m["top"] / 2
            yaw = m["yaw"] % (2 * math.pi)
            res.append({"x": round(m["x"], 3), "y": round(m["y"], 3), "z": round(ground + H / 2, 3),
                        "length": round(L, 3), "width": round(W, 3), "height": round(H, 3),
                        "yaw": round(yaw, 4), "label": lab, "npts": m["npts"],
                        "where": da.where(m["x"], m["y"]), "dist": round(m["dist"], 1),
                        "seen": f"{m['length']:.1f}x{m['width']:.1f}x{m['top']:.1f}"})
        out[f] = res
    return out


def cmd_plan(args) -> int:
    drafts = drafts_for(args)
    for f, items in drafts.items():
        print(f"\n=== {f}: {len(items)} hop nhap")
        for k, b in enumerate(items, 1):
            print(f"  D{k:<2} {b['label']:<10} {b['where']:<22} cach {b['dist']:4.1f}m  "
                  f"cum {b['seen']}m -> hop {b['length']:.1f}x{b['width']:.1f}x{b['height']:.1f}  {b['npts']} diem")
    if args.save:
        Path(args.save).write_text(json.dumps({"frames": drafts}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nDa ghi {args.save}")
    return 0


def cmd_push(args) -> int:
    from cvat_sdk import models

    drafts = (json.loads(Path(args.drafts).read_text(encoding="utf-8"))["frames"]
              if args.drafts else drafts_for(args))
    name = d14_task_name(vf.normalize_student(args.student), args.task)
    client = connect(args.host, args.user, args.org)
    tasks = find_tasks(client, name)
    if len(tasks) != 1:
        raise SystemExit(f"Can dung 1 task ten {name}, thay {len(tasks)}.")
    task = tasks[0]
    ann = task.get_annotations()
    backup = ROOT / "out" / f"cvat_backup_{name}_truoc_draft_{time.strftime('%Y%m%d_%H%M%S')}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(ann.to_dict(), default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    labels = {lab.name: lab for lab in task.get_labels()}
    frame_idx = {vf.frame_name(*vf.parse_frame_name(fr.name)): i for i, fr in enumerate(task.get_meta().frames)}
    shapes = []
    for f, items in drafts.items():
        for k, b in enumerate(items, 1):
            lab = labels[b["label"]]
            spec = {a.name: a.id for a in lab.attributes}
            vals = {"pp_id": "", "score": "", "warn": f"draft D{k}", "note": NOTE}
            shapes.append(models.LabeledShapeRequest(
                type="cuboid", frame=frame_idx[f], label_id=lab.id, points=cuboid_points(b),
                attributes=[models.AttributeValRequest(spec_id=spec[a], value=v) for a, v in vals.items() if a in spec]))
    if not shapes:
        print("Khong co hop nhap nao.")
        return 0
    task.update_annotations(models.PatchedLabeledDataRequest(shapes=shapes))
    print(f"Da THEM {len(shapes)} hop nhap (note='{NOTE}') vao {name}. Sao luu truoc khi them: {backup}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("plan", "push"):
        p = sub.add_parser(n)
        p.add_argument("--data", required=True)
        p.add_argument("--student", required=True)
        p.add_argument("--task", choices=["A", "B"], required=True)
        p.add_argument("--host", required=True)
        p.add_argument("--user", required=True)
        p.add_argument("--org")
        p.add_argument("--min-pts", type=int, default=40)
        if n == "plan":
            p.add_argument("--save")
        else:
            p.add_argument("--drafts", help="JSON tu `plan --save` (da loc tay); bo trong = tinh lai")
    args = ap.parse_args()
    return {"plan": cmd_plan, "push": cmd_push}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
