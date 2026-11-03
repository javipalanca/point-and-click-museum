#!/usr/bin/env python3
"""Descarga las imágenes reales del museo (portadas, capturas y logos) y registra su procedencia.

Lee `data/media.json → items`. Cada elemento declara a qué ficha pertenece (`group` + `id`), su papel
(`cover`, `screenshot`, `logo`) y de dónde sale (`src`):

    github:<owner>/<repo>@<commit>/<ruta>    fichero de un repositorio de GitHub, fijado a un commit
    wikipedia:<lang>:<Título del artículo>   imagen principal del artículo (infobox), vía la API de MediaWiki
    commons:File:<Nombre>                    fichero de Wikimedia Commons (o de Wikipedia, si no es libre)

La herramienta guarda el fichero en `assets/media/<group>/<id>-<role>.<ext>` (las PNG grandes se reducen con un
filtro de caja en Python puro), y escribe en el propio elemento `file`, `w`, `h`, `page` (página de la fuente) y,
para Wikimedia, `license`, `licenseUrl` y `author` tal como los publica Commons. `build.py` copia los ficheros a
`dist/` y muestra el crédito junto a cada imagen.

Uso:
    python3 tools/fetch_media.py               # descarga lo que falte
    python3 tools/fetch_media.py --force       # vuelve a descargarlo todo
    python3 tools/fetch_media.py --only games/loom
    python3 tools/fetch_media.py --check       # solo comprueba que los ficheros declarados existen

Solo biblioteca estándar. La identificación HTTP es genérica (sin datos personales).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA_JSON = ROOT / "data" / "media.json"
OUT = ROOT / "assets" / "media"
UA = "PointAndClickMuseum-media/1.0 (+https://github.com/javipalanca/point-and-click-museum)"
# Tamaños máximos guardados (px). Las capturas pequeñas (pixel art) se guardan tal cual.
QUANTIZE_ABOVE = 60_000
LIMITS = {"cover": ("h", 240), "screenshot": ("w", 400), "logo": ("w", 320)}


# ---------------------------------------------------------------- red
def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def api_json(base: str, params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    return json.loads(http_get(base + "?" + urllib.parse.urlencode(params)))


# ---------------------------------------------------------------- PNG en Python puro
def png_read(data: bytes):
    """Devuelve (ancho, alto, filas RGBA como bytearray). Admite PNG de 8 bits y paleta de 1-8 bits."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("no es PNG")
    pos, idat, plte, trns = 8, [], None, None
    w = h = depth = ctype = inter = None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"tRNS":
            trns = chunk
        elif typ == b"IDAT":
            idat.append(chunk)
        elif typ == b"IEND":
            break
    if inter:
        raise ValueError("PNG entrelazado")
    if depth != 8 and ctype != 3:
        raise ValueError(f"profundidad {depth} no admitida")
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, chans * depth // 8)
    stride = (w * chans * depth + 7) // 8
    raw = zlib.decompress(b"".join(idat))
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                b = prev[i]
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        o = y * w * 4
        if ctype == 6:
            out[o:o + w * 4] = line
        elif ctype == 2:
            out[o:o + w * 4:4], out[o + 1:o + w * 4:4], out[o + 2:o + w * 4:4] = line[0::3], line[1::3], line[2::3]
            out[o + 3:o + w * 4:4] = b"\xff" * w
        elif ctype == 0:
            for c in range(3):
                out[o + c:o + w * 4:4] = line
            out[o + 3:o + w * 4:4] = b"\xff" * w
        elif ctype == 4:
            for c in range(3):
                out[o + c:o + w * 4:4] = line[0::2]
            out[o + 3:o + w * 4:4] = line[1::2]
        else:  # paleta
            per = 8 // depth
            mask = (1 << depth) - 1
            for x in range(w):
                byte = line[x // per]
                idx = (byte >> (8 - depth * (x % per + 1))) & mask
                q = o + x * 4
                out[q:q + 3] = plte[idx * 3:idx * 3 + 3]
                out[q + 3] = trns[idx] if trns and idx < len(trns) else 255
    return w, h, out


def png_write(w: int, h: int, rgba: bytearray) -> bytes:
    opaque = all(a == 255 for a in rgba[3::4])
    rows = []
    for y in range(h):
        row = rgba[y * w * 4:(y + 1) * w * 4]
        if opaque:
            rgb = bytearray(w * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = row[0::4], row[1::4], row[2::4]
            row = rgb
        rows.append(b"\x00" + bytes(row))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2 if opaque else 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


def quantize(w: int, h: int, rgba: bytearray, colors: int = 256):
    """Corte mediano a 256 colores (histograma de 15 bits). Devuelve (paleta, índices) o None si hay alfa."""
    if any(a != 255 for a in rgba[3::4]):
        return None
    hist = {}
    for i in range(0, len(rgba), 4):
        k = (rgba[i] >> 3) << 10 | (rgba[i + 1] >> 3) << 5 | rgba[i + 2] >> 3
        hist[k] = hist.get(k, 0) + 1
    boxes = [list(hist.items())]
    ch = lambda k, c: (k >> (10 - 5 * c)) & 31
    while len(boxes) < colors:
        best = None
        for bi, b in enumerate(boxes):
            if len(b) < 2:
                continue
            spans = [max(ch(k, c) for k, _ in b) - min(ch(k, c) for k, _ in b) for c in range(3)]
            score = max(spans) * sum(n for _, n in b)
            if best is None or score > best[0]:
                best = (score, bi, spans.index(max(spans)))
        if best is None or best[0] == 0:
            break
        _, bi, c = best
        b = sorted(boxes.pop(bi), key=lambda kv: ch(kv[0], c))
        total, acc, cut = sum(n for _, n in b), 0, 1
        for j, (_, n) in enumerate(b):
            acc += n
            if acc >= total / 2:
                cut = min(max(j + 1, 1), len(b) - 1)
                break
        boxes += [b[:cut], b[cut:]]
    pal, lut = [], {}
    for b in boxes:
        tot = sum(n for _, n in b)
        pal.append(tuple(round(sum(((ch(k, c) << 3) | 4) * n for k, n in b) / tot) for c in range(3)))
        for k, _ in b:
            lut[k] = len(pal) - 1
    idx = bytearray(w * h)
    for j, i in enumerate(range(0, len(rgba), 4)):
        idx[j] = lut[(rgba[i] >> 3) << 10 | (rgba[i + 1] >> 3) << 5 | rgba[i + 2] >> 3]
    return pal, idx


def png_write_indexed(w: int, h: int, pal, idx: bytearray) -> bytes:
    rows = b"".join(b"\x00" + bytes(idx[y * w:(y + 1) * w]) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", b"".join(bytes(c) for c in pal)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def box_resize(w: int, h: int, px: bytearray, nw: int, nh: int) -> bytearray:
    """Reducción por promedio de área (filtro de caja), suficiente para miniaturas nítidas."""
    out = bytearray(nw * nh * 4)
    xs = [(x * w // nw, max(x * w // nw + 1, (x + 1) * w // nw)) for x in range(nw)]
    for ny in range(nh):
        y0, y1 = ny * h // nh, max(ny * h // nh + 1, (ny + 1) * h // nh)
        for nx, (x0, x1) in enumerate(xs):
            r = g = b = a = 0
            n = 0
            for y in range(y0, y1):
                base = y * w * 4
                for x in range(x0, x1):
                    q = base + x * 4
                    al = px[q + 3]
                    r += px[q] * al; g += px[q + 1] * al; b += px[q + 2] * al; a += al
                    n += 1
            q = (ny * nw + nx) * 4
            if a:
                out[q], out[q + 1], out[q + 2] = r // a, g // a, b // a
            out[q + 3] = a // n
    return out


def shrink_png(data: bytes, role: str):
    w, h, px = png_read(data)
    if sum(1 for a in px[3::4] if a < 255) * 200 < w * h:  # algún píxel suelto semitransparente: es opaca
        px[3::4] = b"\xff" * (w * h)
    axis, limit = LIMITS.get(role, ("w", 640))
    size = w if axis == "w" else h
    if size > limit:
        k = limit / size
        nw, nh = max(1, round(w * k)), max(1, round(h * k))
        f = -(-size // limit)  # pixel-art screenshots: reduce by a whole factor so pixels stay square and sharp
        if role == "screenshot" and w % f == 0 and h % f == 0 and size // f >= limit * 0.6:
            nw, nh = w // f, h // f
        px, w, h = box_resize(w, h, px, nw, nh), nw, nh
        data = png_write(w, h, px)
    if len(data) > QUANTIZE_ABOVE:  # fotografías y SVGA: 256 colores pesan un tercio y apenas se notan
        q = quantize(w, h, px)
        if q:
            small = png_write_indexed(w, h, *q)
            if len(small) < len(data):
                data = small
    return data, w, h


def image_size(data: bytes, ext: str):
    if ext == "png":
        return struct.unpack(">II", data[16:24])
    if ext in ("jpg", "jpeg"):
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    if ext == "gif":
        return struct.unpack("<HH", data[6:10])
    if ext == "svg":
        txt = data[:2000].decode("utf-8", "replace")
        wh = re.search(r'<svg[^>]*?\swidth="([\d.]+)"', txt), re.search(r'<svg[^>]*?\sheight="([\d.]+)"', txt)
        if all(wh):
            return round(float(wh[0].group(1))), round(float(wh[1].group(1)))
        vb = re.search(r'viewBox="\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)', txt)
        if vb:
            return round(float(vb.group(1))), round(float(vb.group(2)))
    return None, None


def clean_svg(data: bytes) -> bytes:
    txt = data.decode("utf-8")
    if re.search(r"<script|on\w+\s*=|javascript:", txt, re.I):
        raise ValueError("SVG con scripts: revísalo a mano")
    return txt.encode("utf-8")


# ---------------------------------------------------------------- fuentes
def from_github(spec: str):
    m = re.match(r"github:([^/]+)/([^@]+)@([0-9a-f]{7,40})/(.+)$", spec)
    if not m:
        raise ValueError(f"src de GitHub mal formado: {spec}")
    owner, repo, commit, path = m.groups()
    data = b""
    for _ in range(3):  # libretro-thumbnails usa enlaces simbólicos: su contenido es el nombre del destino
        qpath = urllib.parse.quote(path)
        data = http_get(f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{qpath}")
        if len(data) > 300 or b"\0" in data or not re.fullmatch(rb"[^\n<>]+\.(png|jpg|gif|svg)", data.strip()):
            break
        path = str(Path(path).parent / data.decode().strip())
    page = f"https://github.com/{owner}/{repo}/blob/{commit}/{urllib.parse.quote(path)}"
    return data, {"page": page}


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def commons_info(api: str, file_title: str, width: int):
    d = api_json(api, {"action": "query", "titles": file_title, "prop": "imageinfo",
                       "iiprop": "url|extmetadata|mime", "iiurlwidth": width})
    page = d["query"]["pages"][0]
    if "imageinfo" not in page:
        return None
    ii = page["imageinfo"][0]
    md = ii.get("extmetadata", {})
    val = lambda k: strip_html(md.get(k, {}).get("value", ""))
    return {"url": ii.get("thumburl") or ii["url"], "page": ii["descriptionurl"], "mime": ii.get("mime", ""),
            "license": val("LicenseShortName"), "licenseUrl": val("LicenseUrl"),
            "author": val("Artist") or val("Credit"), "nonFree": val("NonFree").lower() == "true"}


def from_commons(spec: str, role: str, lang: str = "en"):
    title = spec.split(":", 1)[1]
    width = LIMITS.get(role, ("w", 320))[1]
    info = commons_info("https://commons.wikimedia.org/w/api.php", title, width)
    if info is None:  # imagen no libre subida solo a Wikipedia
        info = commons_info(f"https://{lang}.wikipedia.org/w/api.php", title, width)
    if info is None:
        raise ValueError(f"no existe {title}")
    meta = {k: info[k] for k in ("page", "license", "licenseUrl", "author") if info.get(k)}
    if info["nonFree"]:
        meta["nonFree"] = True
    return http_get(info["url"]), meta


def from_wikipedia(spec: str, role: str):
    _, lang, title = spec.split(":", 2)
    d = api_json(f"https://{lang}.wikipedia.org/w/api.php",
                 {"action": "query", "titles": title, "prop": "pageimages|pageprops", "piprop": "name",
                  "redirects": 1})
    page = d["query"]["pages"][0]
    name = page.get("pageimage")
    if role == "logo":  # el logo oficial suele estar en Wikidata (P154)
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            wd = api_json("https://www.wikidata.org/w/api.php",
                          {"action": "wbgetclaims", "entity": qid, "property": "P154"})
            claims = wd.get("claims", {}).get("P154", [])
            if claims:
                name = claims[0]["mainsnak"]["datavalue"]["value"]
    if not name:
        raise ValueError(f"{title}: el artículo no tiene imagen principal")
    data, meta = from_commons("commons:File:" + name, role, lang)
    meta["article"] = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return data, meta


# ---------------------------------------------------------------- principal
def ext_of(data: bytes, src: str) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"GIF8":
        return "gif"
    if b"<svg" in data[:2000]:
        return "svg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ValueError(f"formato desconocido: {src}")


def fetch(item: dict) -> dict:
    src, role = item["src"], item["role"]
    if src.startswith("github:"):
        data, meta = from_github(src)
    elif src.startswith("wikipedia:"):
        data, meta = from_wikipedia(src, role)
    elif src.startswith("commons:"):
        data, meta = from_commons(src, role)
    else:
        raise ValueError(f"fuente desconocida: {src}")
    ext = ext_of(data, src)
    if ext == "png":
        data, w, h = shrink_png(data, role)
    elif ext == "svg":
        data = clean_svg(data)
        w, h = image_size(data, ext)
    else:
        w, h = image_size(data, ext)
    rel = f"{item['group']}/{item['id']}-{role}.{ext}"
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    for old in dest.parent.glob(f"{item['id']}-{role}.*"):
        if old != dest:
            old.unlink()
    dest.write_bytes(data)
    item.update(meta)
    item.update({"file": rel, "w": w, "h": h})
    return item


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="vuelve a descargar aunque exista el fichero")
    ap.add_argument("--only", action="append", default=[], help="grupo/id (se puede repetir)")
    ap.add_argument("--check", action="store_true", help="solo comprueba los ficheros declarados")
    a = ap.parse_args()
    doc = json.loads(MEDIA_JSON.read_text(encoding="utf-8"))
    items = doc["items"]
    if a.check:
        missing = [f"{i['group']}/{i['id']} ({i['role']})" for i in items
                   if not i.get("file") or not (OUT / i["file"]).exists()]
        print("\n".join(missing) or "todo en su sitio")
        return 1 if missing else 0
    errors = 0
    for it in items:
        key = f"{it['group']}/{it['id']}"
        if a.only and key not in a.only:
            continue
        if not a.force and it.get("file") and (OUT / it["file"]).exists():
            continue
        try:
            fetch(it)
            print(f"ok   {key:34} {it['role']:10} {it['w']}x{it['h']}  {it['file']}")
        except (urllib.error.URLError, ValueError, KeyError, OSError) as e:
            errors += 1
            print(f"FALLO {key:33} {it['role']:10} {e}", file=sys.stderr)
        MEDIA_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'sin errores' if not errors else f'{errors} fallos'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
