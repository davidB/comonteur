"""Single source for every comonteur identifier. Renaming stays a one-line change (SPEC.md header)."""

ADDON_ID = "comonteur"
CLI_NAME = "comonteur"
PREFIX = "cmt_"

PROP_ID = PREFIX + "id"
PROP_ORIGIN = PREFIX + "origin"
PROP_REV = PREFIX + "rev"
PROP_PARAM = PREFIX + "param"

ORIGIN_AGENT = "agent"
ORIGIN_HUMAN = "human"
ORIGIN_SHARED = "shared"

JOURNAL_DIR = ".comonteur"
JOURNAL_FILENAME = "journal.jsonl"

# 2D convention: kind="2d" scenes get an ortho camera this many Blender units tall
# (sensor_fit="VERTICAL"), regardless of landscape/portrait aspect. Not a rule for kind="3d".
FRAME_HEIGHT = 2.0
