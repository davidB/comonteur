//! `captions/*.json` ingest — SPEC.md §5.3. Word-level timing, normalized from either
//! TTS provider timing marks (exact by construction) or Whisper word-level output
//! (primary path for human-recorded VO, not a degraded fallback). Normalization only —
//! comonteur does not invoke `whisper` itself; per §5.7 that's an existing external
//! pipeline (`vo:transcribe`) whose `transcript.json` output this module consumes.

use serde::Serialize;
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct Word {
    pub word: String,
    pub start: f64,
    pub end: f64,
}

#[derive(Debug, Serialize, serde::Deserialize)]
pub struct Captions {
    pub words: Vec<Word>,
}

const WORD_KEYS: &[&str] = &["word", "text"];
const START_KEYS: &[&str] = &["start", "start_time"];
const END_KEYS: &[&str] = &["end", "end_time"];

fn first_str(v: &Value, keys: &[&str]) -> Option<String> {
    keys.iter()
        .find_map(|k| v.get(k).and_then(Value::as_str))
        .map(str::to_string)
}

fn first_f64(v: &Value, keys: &[&str]) -> Option<f64> {
    keys.iter().find_map(|k| v.get(k).and_then(Value::as_f64))
}

/// Pure logic: tolerant of common key aliases (`word`/`text`, `start`/`start_time`,
/// `end`/`end_time`) since neither Whisper's nor any given TTS provider's exact wire
/// format is pinned by the spec.
pub fn normalize_words(raw: &[Value]) -> Vec<Word> {
    raw.iter()
        .filter_map(|v| {
            Some(Word {
                word: first_str(v, WORD_KEYS)?,
                start: first_f64(v, START_KEYS)?,
                end: first_f64(v, END_KEYS)?,
            })
        })
        .collect()
}

/// openai-whisper's documented `segments[].words[]` shape — a concrete, verifiable
/// format. This is what a project's existing `vo:transcribe` task already produces.
pub fn from_whisper_json(v: &Value) -> Vec<Word> {
    let segments = v
        .get("segments")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let words: Vec<Value> = segments
        .iter()
        .flat_map(|seg| {
            seg.get("words")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default()
        })
        .collect();
    normalize_words(&words)
}

/// Generic normalizer for upstream-supplied TTS provider timing marks. No specific
/// vendor is named anywhere in the spec, so this is a tolerant first-cut shape — a
/// top-level array, or `{"words": [...]}` / `{"alignment": [...]}` — not a vendor
/// contract.
pub fn from_timing_marks(v: &Value) -> Vec<Word> {
    let raw: Vec<Value> = if let Some(arr) = v.as_array() {
        arr.clone()
    } else {
        v.get("words")
            .or_else(|| v.get("alignment"))
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };
    normalize_words(&raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn normalize_words_handles_key_aliases() {
        let raw = vec![
            json!({"word": "hello", "start": 0.0, "end": 0.4}),
            json!({"text": "world", "start_time": 0.4, "end_time": 0.9}),
        ];
        let words = normalize_words(&raw);
        assert_eq!(
            words,
            vec![
                Word {
                    word: "hello".into(),
                    start: 0.0,
                    end: 0.4
                },
                Word {
                    word: "world".into(),
                    start: 0.4,
                    end: 0.9
                },
            ]
        );
    }

    #[test]
    fn normalize_words_skips_entries_missing_fields() {
        let raw = vec![
            json!({"word": "orphan"}),
            json!({"word": "ok", "start": 1.0, "end": 1.2}),
        ];
        assert_eq!(normalize_words(&raw).len(), 1);
    }

    #[test]
    fn from_whisper_json_flattens_segments() {
        let v = json!({
            "segments": [
                {"words": [
                    {"word": "hello", "start": 0.0, "end": 0.4},
                    {"word": "there", "start": 0.4, "end": 0.8}
                ]},
                {"words": [
                    {"word": "world", "start": 1.0, "end": 1.5}
                ]}
            ]
        });
        let words = from_whisper_json(&v);
        assert_eq!(words.len(), 3);
        assert_eq!(words[2].word, "world");
    }

    #[test]
    fn from_timing_marks_accepts_top_level_array() {
        let v = json!([{"word": "hi", "start": 0.0, "end": 0.2}]);
        assert_eq!(from_timing_marks(&v).len(), 1);
    }

    #[test]
    fn from_timing_marks_accepts_words_wrapper() {
        let v = json!({"words": [{"word": "hi", "start": 0.0, "end": 0.2}]});
        assert_eq!(from_timing_marks(&v).len(), 1);
    }

    #[test]
    fn from_timing_marks_accepts_alignment_wrapper() {
        let v = json!({"alignment": [{"text": "hi", "start_time": 0.0, "end_time": 0.2}]});
        assert_eq!(from_timing_marks(&v).len(), 1);
    }
}
