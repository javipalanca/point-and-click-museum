"""A catalogue with many playable games, for the DOSBox room tests (pages, search, letters, order).

    python3 tests/fixtures/arcade_catalog.py OUT.json [N]

Takes data/catalog.json and marks the first N (default 25) games that have an edition as playable, those with a
record in the timeline first (they have covers). Nothing is downloaded: the room only needs to list them."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
out, n = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 25
cat = json.loads((ROOT / "data" / "catalog.json").read_text("utf-8"))
done = 0
for g in sorted(cat["games"], key=lambda g: (not g.get("timeline"), g["title"])):
    if done < n and g.get("editions"):
        g["status"] = "playable"
        g["editions"][0]["status"] = "playable"
        done += 1
out.write_text(json.dumps(cat), "utf-8")
print(f"{done} playable games -> {out}")
