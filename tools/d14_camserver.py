"""Server cuc bo cho userscript `tools/cvat-d14-cameras.user.js` (chi nghe 127.0.0.1).

Userscript doc hop tu CVAT (cung phien dang nhap cua ban), gui sang day; server chieu hop
len 7 anh camera bang calib.json cua VF va tra ve toa do pixel. Server khong ghi gi vao CVAT.

  python tools/d14_camserver.py --data "C:\\...\\Data-VF"
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import vf_common as vf  # noqa: E402
from scripts import vf_d14, vf_qa  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from d14_assist import box_hint  # noqa: E402

DATA: Path = Path(".")
IMG_W = 960
FRAME_RE = re.compile(r"s\d{2}f\d{2}")


@lru_cache(maxsize=32)
def frame_row(name: str) -> dict:
    return vf_d14.frame_rows(DATA, [name])[0]


@lru_cache(maxsize=8)
def calib(seq: int) -> dict:
    return vf_qa.load_calib(DATA / f"sequence_{seq:02d}")


@lru_cache(maxsize=8)
def points(name: str):
    return vf_d14.load_points(frame_row(name))


@lru_cache(maxsize=64)
def cam_jpeg(name: str, cam: str) -> tuple[bytes, float]:
    from PIL import Image
    path = dict(frame_row(name)["cameras"])[cam]
    img = Image.open(path).convert("RGB")
    scale = IMG_W / img.width
    img = img.resize((IMG_W, round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue(), scale


def project(payload: dict) -> dict:
    from vf_pp.core import points_in_box

    name = payload["frame"]
    row = frame_row(name)
    cal = calib(row["seq"])
    pts = points(name)
    boxes = []
    for s in payload["shapes"]:
        b = vf.cuboid_from_cvat(s["points"], s.get("label", "?"))
        b["npts"] = points_in_box(pts, b)
        b["pp_id"] = s.get("pp_id", "")
        try:
            b["score"] = float(s.get("score") or "")
        except ValueError:
            pass  # hop ban tu ve: khong co score
        sev, hint = box_hint(b)
        boxes.append({"id": s["id"], "pp_id": b["pp_id"], "label": b["label"], "box": b,
                      "dist": round(math.hypot(b["x"], b["y"]), 1), "npts": b["npts"],
                      "dims": f"{b['length']:.2f} x {b['width']:.2f} x {b['height']:.2f} m",
                      "hint": f"{sev}-{hint}" if b["pp_id"] != "" else hint.replace("XOA?", "KIEM"), "sev": sev})
    cams = []
    for cam, _path in row["cameras"]:
        if cam not in cal:
            continue
        _jpg, scale = cam_jpeg(name, cam)
        items = []
        for bx in boxes:
            pieces = vf_qa.project_box(bx["box"], cal[cam])
            if pieces:
                items.append({"id": bx["id"], "lines": [[[round(u * scale, 1), round(v * scale, 1)] for u, v in pc]
                                                       for pc in pieces]})
        cams.append({"cam": cam, "url": f"/cam/{name}/{cam}.jpg", "scale": scale, "boxes": items})
    for bx in boxes:
        del bx["box"]
    return {"frame": name, "boxes": boxes, "cams": cams}


class Handler(BaseHTTPRequestHandler):
    def _head(self, code: int, ctype: str, length: int):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "max-age=3600")
        self.end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._head(code, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._head(204, "text/plain", 0)

    def do_GET(self):
        m = re.fullmatch(r"/cam/(s\d{2}f\d{2})/(cam\d{2})\.jpg", self.path.split("?")[0])
        if m:
            try:
                body, _ = cam_jpeg(m.group(1), m.group(2))
            except Exception as exc:  # noqa: BLE001
                return self._json({"error": str(exc)}, 404)
            self._head(200, "image/jpeg", len(body))
            self.wfile.write(body)
            return
        if self.path.startswith("/ping"):
            return self._json({"ok": True, "data": str(DATA)})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.path.startswith("/project"):
            return self._json({"error": "not found"}, 404)
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if not FRAME_RE.fullmatch(payload.get("frame", "")):
                raise ValueError("frame khong hop le")
            self._json(project(payload))
        except Exception as exc:  # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)

    def log_message(self, fmt, *args):
        pass


def main() -> int:
    global DATA
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    DATA = Path(args.data)
    if not (DATA / "sequence_01").exists():
        raise SystemExit(f"{DATA} khong chua sequence_01.")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Camera server: http://127.0.0.1:{args.port}  (Ctrl+C de dung)")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
