#!/usr/bin/env python3
"""
bake-network.py — download Prague's transit geometry once and write it straight
into prague-transit-3d.html, so the app never fetches track data at runtime.

    python bake-network.py                 # tracks + rail/tram/metro/trolleybus routes
    python bake-network.py --buses         # also bake every bus route (much bigger)
    python bake-network.py --tol 20        # coarser simplification, smaller file

Needs only Python 3 and an internet connection. Source is OpenStreetMap via the
Overpass API (ODbL). Re-run it whenever you want to refresh the network.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

HTML = "index.html"
BBOX = (49.92, 14.18, 50.20, 14.75)          # S, W, N, E — Prague and inner suburbs

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# OSM route= values to bake, keyed by the mode name the app uses
ROUTE_KINDS = {
    "tram": "tram",
    "subway": "metro",
    "train": "train",
    "trolleybus": "trolley",
    "ferry": "ferry",
    "funicular": "funi",
}


# ---------------------------------------------------------------- fetching --
def overpass(query, what):
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for host in MIRRORS:
        for attempt in range(2):
            try:
                print(f"  → {what}: {host.split('/')[2]}"
                      f"{' (retry)' if attempt else ''} … ", end="", flush=True)
                req = urllib.request.Request(
                    host, data=body,
                    headers={"User-Agent": "prague-transit-3d/1.0 (portfolio project)"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    raw = r.read()
                print(f"{len(raw)/1e6:.1f} MB")
                return json.loads(raw)
            except Exception as e:                      # noqa: BLE001
                print(f"failed ({e})")
                last = e
                time.sleep(4)
    raise SystemExit(f"Could not reach any Overpass mirror for {what}: {last}")


# ------------------------------------------------------------ simplifying --
def rdp(pts, tol):
    """Ramer–Douglas–Peucker, tolerance in degrees."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if denom == 0:
            d = (px - ax) ** 2 + (py - ay) ** 2
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / denom
            t = max(0.0, min(1.0, t))
            cx, cy = ax + t * dx, ay + t * dy
            d = (px - cx) ** 2 + (py - cy) ** 2
        if d > worst:
            worst, wi = d, i
    if worst > tol * tol:
        left = rdp(pts[:wi + 1], tol)
        right = rdp(pts[wi:], tol)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def encode(pts):
    """Google encoded polyline, precision 5. Roughly 6 bytes per point."""
    out, plat, plon = [], 0, 0
    for lon, lat in pts:
        ilat, ilon = round(lat * 1e5), round(lon * 1e5)
        for delta in (ilat - plat, ilon - plon):
            v = ~(delta << 1) if delta < 0 else (delta << 1)
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = ilat, ilon
    return "".join(out)


def prep(geometry, tol):
    pts = [(g["lon"], g["lat"]) for g in geometry]
    if len(pts) < 2:
        return None
    pts = rdp(pts, tol)
    return encode(pts) if len(pts) >= 2 else None


# ------------------------------------------------------------------ main ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buses", action="store_true",
                    help="also bake every bus route (adds a lot of weight)")
    ap.add_argument("--tol", type=float, default=12.0,
                    help="simplification tolerance in metres (default 12)")
    ap.add_argument("--html", default=HTML)
    args = ap.parse_args()

    tol = args.tol / 111_320.0                       # metres → degrees
    s, w, n, e = BBOX
    bb = f"{s},{w},{n},{e}"

    # ---- 1. the physical track network --------------------------------
    print("Downloading track network…")
    net_q = f"""[out:json][timeout:300];
(
  way["railway"="tram"]["service"!~"."]({bb});
  way["railway"="subway"]["service"!~"."]({bb});
  way["railway"="rail"]["service"!~"."]["usage"!="industrial"]({bb});
);
out geom;"""
    net_json = overpass(net_q, "tracks")

    net = {"tram": [], "subway": [], "rail": []}
    for el in net_json.get("elements", []):
        kind = (el.get("tags") or {}).get("railway")
        if kind in net and isinstance(el.get("geometry"), list):
            enc = prep(el["geometry"], tol)
            if enc:
                net[kind].append(enc)
    for k, v in net.items():
        print(f"    {k:7s} {len(v):5d} segments")

    # ---- 2. per-line route geometry ------------------------------------
    kinds = dict(ROUTE_KINDS)
    if args.buses:
        kinds["bus"] = "bus"

    print("Downloading routes…")
    parts = "\n".join(f'  rel["route"="{k}"]["ref"]({bb});' for k in kinds)
    rel_q = f"[out:json][timeout:300];\n(\n{parts}\n);\nout geom;"
    rel_json = overpass(rel_q, "routes")

    lines = {}
    for rel in rel_json.get("elements", []):
        tags = rel.get("tags") or {}
        ref, route = tags.get("ref"), tags.get("route")
        if not ref or route not in kinds:
            continue
        key = f"{route}/{ref}"
        bucket = lines.setdefault(key, [])
        for m in rel.get("members", []):
            if m.get("type") == "way" and isinstance(m.get("geometry"), list):
                enc = prep(m["geometry"], tol)
                if enc:
                    bucket.append(enc)
    for k in [k for k, v in lines.items() if not v]:
        del lines[k]

    # per-kind breakdown, so a missing mode is obvious rather than inferred
    by_kind = {}
    for key in lines:
        kind = key.split("/", 1)[0]
        by_kind.setdefault(kind, []).append(key.split("/", 1)[1])
    for kind in sorted(kinds):
        got = sorted(by_kind.get(kind, []), key=lambda r: (len(r), r))
        label = f"    {kind:11s} {len(got):4d} lines"
        if got:
            print(f"{label}   {', '.join(got[:14])}{' …' if len(got) > 14 else ''}")
        else:
            print(f"{label}   ← nothing found; check OSM tagging for this mode")
    if not args.buses:
        print("    bus            0 lines   ← not requested; re-run with --buses to include them")

    # ---- 3. splice into the HTML ---------------------------------------
    payload = {"net": net, "lines": lines}
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    print(f"Baked payload: {len(blob)/1e6:.2f} MB")

    try:
        html = open(args.html, encoding="utf-8").read()
    except FileNotFoundError:
        raise SystemExit(f"{args.html} not found — run this next to the HTML file.")

    start, end = "/*NETWORK_DATA_START*/", "/*NETWORK_DATA_END*/"
    if start not in html or end not in html:
        raise SystemExit("Marker comments missing from the HTML — is this the right file?")

    new_block = f"{start}\nconst BAKED_NETWORK = {blob};\n{end}"
    html = re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: new_block,
                  html, flags=re.S)

    open(args.html, "w", encoding="utf-8").write(html)
    size = len(html.encode("utf-8")) / 1e6
    print(f"\nWrote {args.html} — now {size:.2f} MB, fully self-contained.")
    print("Reload the page: the track layer and line clicks are instant, no network calls.")


if __name__ == "__main__":
    import urllib.parse
    sys.setrecursionlimit(20000)
    main()