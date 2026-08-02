"""text.word_spans() gives whitespace-delimited (start, end) index pairs aligned with
split_chars()'s output — the shared helper for grouping characters into words instead
of every caller hand-rolling the same whitespace scan.
"""

import _bl

cmt = _bl.setup()

BODY = "ab cd  ef"
spans = cmt.text.word_spans(BODY)
words = [BODY[s:e] for s, e in spans]
assert words == ["ab", "cd", "ef"], words

assert cmt.text.word_spans("") == []
assert cmt.text.word_spans("   ") == []
assert cmt.text.word_spans("solo") == [(0, 4)]
