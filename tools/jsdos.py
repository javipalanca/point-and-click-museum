"""Helpers to build js-dos v8 bundles (.jsdos files).

A .jsdos bundle is a plain ZIP archive with the game files at its root and a
`.jsdos/` folder holding `dosbox.conf` and `jsdos.json`. js-dos extracts the
archive and runs the [autoexec] section of dosbox.conf.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path, PurePosixPath

DEFAULT_CONF = {
    "sdl": {"autolock": "true", "sensitivity": "100"},
    "dosbox": {"machine": "svga_s3", "memsize": "16"},
    "cpu": {"core": "auto", "cputype": "auto", "cycles": "auto"},
    "mixer": {"rate": "44100"},
    "sblaster": {"sbtype": "sb16"},
}


def dosbox_conf(exe: str | None, cycles: str | None = None, extra_autoexec: list[str] | None = None) -> str:
    """Return a dosbox.conf that mounts the bundle as C: and runs `exe` (e.g. 'GAME\\START.BAT')."""
    sections = {k: dict(v) for k, v in DEFAULT_CONF.items()}
    if cycles:
        sections["cpu"]["cycles"] = cycles
    lines: list[str] = []
    for name, values in sections.items():
        lines.append(f"[{name}]")
        lines += [f"{k}={v}" for k, v in values.items()]
        lines.append("")
    lines += ["[autoexec]", "@echo off", "mount c .", "c:"]
    if exe:
        parts = [p for p in exe.replace("/", "\\").split("\\") if p]
        if len(parts) > 1:
            lines.append("cd \\" + "\\".join(parts[:-1]))
        lines.append(parts[-1])
    lines += extra_autoexec or []
    return "\n".join(lines) + "\n"


def make_bundle(files: dict[str, bytes], exe: str | None, cycles: str | None = None,
                extra_autoexec: list[str] | None = None) -> bytes:
    """Build a .jsdos archive in memory. `files` maps DOS paths (use '/') to bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(".jsdos/dosbox.conf", dosbox_conf(exe, cycles, extra_autoexec))
        z.writestr(".jsdos/jsdos.json", json.dumps({"version": "js-dos-v8"}, indent=2))
        for name, data in sorted(files.items()):
            z.writestr(str(PurePosixPath(name)), data)
    return buf.getvalue()


def files_from_dir(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def museum_demo_com() -> bytes:
    """A tiny original 16-bit DOS .COM program: prints a banner, waits for a key, exits."""
    msg = (
        "\r\n"
        "  POINT AND CLICK MUSEUM - DOSBOX ROOM\r\n"
        "  ====================================\r\n\r\n"
        "  DOSBox is running inside your browser.\r\n"
        "  DOSBox funciona dentro de tu navegador.\r\n"
        "  DOSBox laeuft in deinem Browser.\r\n"
        "  DOSBox tourne dans votre navigateur.\r\n\r\n"
        "  Next: MUSEUM PAINT, a mouse test.\r\n"
        "  Click the screen to capture the mouse,\r\n"
        "  Esc releases it in the browser.\r\n\r\n"
        "  Press any key...$"
    ).encode("ascii")
    code = bytes([
        0xBA, 0x10, 0x01,  # mov dx, 0x0110 (message offset)
        0xB4, 0x09,        # mov ah, 09h
        0xCD, 0x21,        # int 21h      -> print '$'-terminated string
        0xB4, 0x00,        # mov ah, 00h
        0xCD, 0x16,        # int 16h      -> wait for a key
        0xB8, 0x00, 0x4C,  # mov ax, 4C00h
        0xCD, 0x21,        # int 21h      -> exit to DOS
    ])
    assert len(code) == 0x10
    return code + msg


def museum_demo_bundle() -> bytes:
    readme = (
        "POINT AND CLICK MUSEUM\r\n\r\n"
        "MUSEUM.COM is a tiny test program (CC0).\r\n"
        "PAINT.COM is a mouse test (source: tools/dos/paint.asm).\r\n"
    ).encode("ascii")
    paint = (Path(__file__).resolve().parent / "dos" / "PAINT.COM").read_bytes()
    return make_bundle({"MUSEUM.COM": museum_demo_com(), "PAINT.COM": paint, "README.TXT": readme}, exe="MUSEUM.COM",
                       extra_autoexec=["PAINT.COM", "echo.", "echo Type PAINT, MUSEUM, DIR or VER."])
