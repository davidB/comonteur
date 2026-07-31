"""journal.set() survives the array-valued properties it invites you to write.

The journal is JSONL, and bpy hands back `Vector`, `Color` and `bpy_prop_array` for anything
vector-shaped — none of them JSON-serializable. Writing a whole `scale` or a material's
`default_value` raised `TypeError: Object of type Vector is not JSON serializable` at *batch
exit*, inside the `finally` that flushes the batch. By then earlier entries in the same batch
have already been appended, so the batch is half-written and the exception surfaces far from
the call that caused it.

api.md offers `set()` as "the escape hatch for any property the typed helpers don't cover", so
these values are exactly what it will be pointed at.
"""

import json
from pathlib import Path

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-json", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "Ship faster", size=0.8)

with cmt.journal.batch("array-valued writes"):
    cmt.journal.set(title, "scale", (2.0, 2.0, 2.0))
    cmt.journal.set(title, "location", (1.0, 2.0, 3.0))
    cmt.journal.set(title, "location[1]", 0.5)  # scalar still fine

assert tuple(title.scale) == (2.0, 2.0, 2.0), tuple(title.scale)

# Every line has to be readable back — a half-written batch is worse than no journal.
lines = Path(".comonteur/journal.jsonl").read_text().splitlines()
entries = [json.loads(line) for line in lines if line.strip()]

by_path = {e["path"]: e for e in entries if e.get("op") == "set"}
assert set(by_path) == {"scale", "location", "location[1]"}, sorted(by_path)
assert by_path["scale"]["new"] == [2.0, 2.0, 2.0], by_path["scale"]
assert by_path["location[1]"]["new"] == 0.5, by_path["location[1]"]

# last_agent_value round-trips through JSON, so revert has something usable.
assert list(cmt.journal.last_agent_value(title, "scale")) == [2.0, 2.0, 2.0]
