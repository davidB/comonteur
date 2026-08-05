"""A batch that only *creates* still journals, bumps cmt_rev, and would push one undo step.

SKILL.md promises the batch "produces the journal entries, bumps cmt_rev, and emits exactly one
labelled undo step the human can undo in one keystroke". That did not hold for creation-only
work: scene.new_scene() and text.create() set their properties directly rather than through
journal.set(), and journal.batch() gates the JSONL write, the cmt_rev bump *and* the undo_push
on `if writes:`. So the most common first batch — make a scene, put a title in it — was
invisible to the journal and left the human nothing to undo.

The undo_push itself cannot be observed here: journal.py already notes it needs a window, which
a headless run has not got. What this pins is the `writes` list that gates it — non-empty writes
is exactly the condition under which the GUI path pushes.
"""

import json
from pathlib import Path

import _bl

cmt = _bl.setup()

with cmt.journal.batch("shot-04: create title"):
    scn = cmt.scene.new_scene("shot-04", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "Ship faster", size=0.8)

# Creation is tagged and owned by the agent.
assert cmt.provenance.origin(scn) == "agent", cmt.provenance.origin(scn)
assert cmt.provenance.origin(title) == "agent", cmt.provenance.origin(title)
assert scn["cmt_id"] == "shot-04"

# ...and it is *recorded*, so revert and drift have something to work from.
assert cmt.journal.created_by_agent(title), (
    "text.create() wrote nothing to the journal — revert cannot undo this object"
)
assert cmt.journal.created_by_agent(scn), "scene.new_scene() wrote nothing to the journal"

# The entries reached the real file, not just the in-memory batch state.
entries = [json.loads(line) for line in Path(".comonteur/journal.jsonl").read_text().splitlines()]
creates = [e for e in entries if e["op"] == "create"]
assert {e["target"] for e in creates} == {
    cmt.journal.target_of(scn),
    cmt.journal.target_of(scn.camera),
    cmt.journal.target_of(title),
}, creates
assert len({e["batch"] for e in creates}) == 1, "one batch must produce one batch id"

# cmt_rev is bumped once per batch, which is the same `if writes:` gate.
assert scn["cmt_rev"] >= 1, scn["cmt_rev"]
rev_after_create = scn["cmt_rev"]

with cmt.journal.batch("shot-04: retitle"):
    cmt.journal.set(title, "data.body", "Ship even faster")

assert scn["cmt_rev"] == rev_after_create, "a batch that did not touch the scene bumped its rev"
assert title["cmt_rev"] > 1, "a second batch must bump the rev of what it touched"
assert title.data.body == "Ship even faster"
