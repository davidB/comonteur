//! `timeline.yaml` → resolved assembly plan — SPEC.md §5.2/§10 M4. `timeline.yaml` is
//! the only file this crate resolves rather than merely validates: the anchor-relative
//! timing pipeline ("re-transcribe, re-resolve, done") needs a real word-timing lookup,
//! which is exactly the kind of logic that belongs in this Rust crate, not in
//! `addon/reconcile.py` — Python in this repo is scoped to the Blender addon (`bpy`) and
//! pure-logic tests, never a YAML-parsing runtime of its own. The output is plain JSON
//! (integer frame numbers, no more anchors) that `reconcile.py` reads with the stdlib
//! `json` module and turns into VSE strips.

use crate::captions::Word;
use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct TimelineDoc {
    pub fps: u32,
    pub resolution: (u32, u32),
    #[serde(default)]
    pub shots: Vec<Shot>,
    #[serde(default)]
    pub audio: Vec<AudioTrack>,
}

#[derive(Debug, Deserialize)]
pub struct Shot {
    pub id: String,
    pub source: Source,
    pub start: Option<i64>,
    pub anchor: Option<Anchor>,
    pub duration: i64,
    #[serde(rename = "in")]
    pub in_: Option<i64>,
    pub transition: Option<Transition>,
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Source {
    Scene { blend: String, scene: String },
    Movie { path: String },
}

#[derive(Debug, Deserialize)]
pub struct Anchor {
    pub word: String,
    pub occurrence: u32,
    #[serde(default)]
    pub offset: f64,
}

#[derive(Debug, Deserialize)]
pub struct Transition {
    #[serde(rename = "type")]
    pub kind: String,
    /// Seconds, like `Anchor::offset` — converted to frames at resolve time, same as
    /// anchors, since both are timed relative to the transcript/audio, not the edit grid.
    pub duration: f64,
}

#[derive(Debug, Deserialize)]
pub struct AudioTrack {
    pub id: String,
    pub path: String,
    pub start: Option<i64>,
    pub anchor: Option<Anchor>,
}

pub fn load(path: &Path) -> Result<TimelineDoc> {
    let text =
        std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
    serde_yaml_ng::from_str(&text).with_context(|| format!("parsing {}", path.display()))
}

pub fn load_transcript(path: &Path) -> Result<Vec<Word>> {
    let text =
        std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
    let doc: crate::captions::Captions =
        serde_json::from_str(&text).with_context(|| format!("parsing {}", path.display()))?;
    Ok(doc.words)
}

/// Pure logic: fail loudly rather than guess (SPEC.md §5.2).
pub fn validate(doc: &TimelineDoc) -> Vec<String> {
    let mut errors = Vec::new();
    if doc.shots.is_empty() {
        errors.push("timeline.yaml: `shots` is empty".to_string());
    }
    let mut shot_ids = HashSet::new();
    for (i, shot) in doc.shots.iter().enumerate() {
        if shot.id.trim().is_empty() {
            errors.push(format!("shots[{i}]: empty `id`"));
        } else if !shot_ids.insert(shot.id.clone()) {
            errors.push(format!("shots[{i}]: duplicate id {:?}", shot.id));
        }
        match (&shot.start, &shot.anchor) {
            (Some(_), None) | (None, Some(_)) => {}
            _ => errors.push(format!(
                "shots[{i}] ({}): exactly one of `start`/`anchor` must be set",
                shot.id
            )),
        }
        if shot.duration <= 0 {
            errors.push(format!(
                "shots[{i}] ({}): duration must be > 0, got {}",
                shot.id, shot.duration
            ));
        }
        if let Some(a) = &shot.anchor
            && a.occurrence < 1
        {
            errors.push(format!(
                "shots[{i}] ({}): anchor.occurrence must be >= 1, got {}",
                shot.id, a.occurrence
            ));
        }
    }
    let mut audio_ids = HashSet::new();
    for (i, track) in doc.audio.iter().enumerate() {
        if track.id.trim().is_empty() {
            errors.push(format!("audio[{i}]: empty `id`"));
        } else if !audio_ids.insert(track.id.clone()) {
            errors.push(format!("audio[{i}]: duplicate id {:?}", track.id));
        }
        match (&track.start, &track.anchor) {
            (Some(_), None) | (None, Some(_)) => {}
            _ => errors.push(format!(
                "audio[{i}] ({}): exactly one of `start`/`anchor` must be set",
                track.id
            )),
        }
    }
    errors
}

pub fn parse(path: &Path) -> Result<TimelineDoc> {
    let doc = load(path)?;
    let errors = validate(&doc);
    if !errors.is_empty() {
        bail!("{}", errors.join("\n"));
    }
    Ok(doc)
}

#[derive(Debug, Serialize, PartialEq)]
pub struct ResolvedTimeline {
    pub fps: u32,
    pub resolution: (u32, u32),
    pub shots: Vec<ResolvedShot>,
    pub audio: Vec<ResolvedAudio>,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct ResolvedShot {
    pub id: String,
    pub source: Source,
    pub start_frame: i64,
    pub duration_frames: i64,
    pub in_frame: Option<i64>,
    pub transition: Option<ResolvedTransition>,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct ResolvedTransition {
    #[serde(rename = "type")]
    pub kind: String,
    pub duration_frames: i64,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct ResolvedAudio {
    pub id: String,
    pub path: String,
    pub start_frame: i64,
}

/// Find the anchor word's Nth (1-indexed) occurrence in the transcript, case-insensitive,
/// and convert `word.start + offset` seconds to a frame number. Bails loudly (§5.2: "fail
/// loudly, never silently") if the word or occurrence isn't there — that's the "script
/// drifted from the recording" signal, not something to guess past.
fn resolve_anchor(anchor: &Anchor, words: &[Word], fps: u32) -> Result<i64> {
    let matches: Vec<&Word> = words
        .iter()
        .filter(|w| w.word.eq_ignore_ascii_case(&anchor.word))
        .collect();
    let idx = anchor.occurrence as usize;
    let word = matches.get(idx.saturating_sub(1)).copied().ok_or_else(|| {
        anyhow::anyhow!(
            "anchor word {:?} occurrence {} not found ({} occurrence(s) in transcript)",
            anchor.word,
            anchor.occurrence,
            matches.len()
        )
    })?;
    let seconds = word.start + anchor.offset;
    Ok((seconds * fps as f64).round() as i64)
}

fn resolve_position(
    id: &str,
    start: Option<i64>,
    anchor: Option<&Anchor>,
    transcript: Option<&[Word]>,
    fps: u32,
) -> Result<i64> {
    match (start, anchor) {
        (Some(s), None) => Ok(s),
        (None, Some(a)) => {
            let words = transcript.ok_or_else(|| {
                anyhow::anyhow!("{id:?} uses an anchor but no transcript was provided")
            })?;
            resolve_anchor(a, words, fps).with_context(|| format!("resolving anchor for {id:?}"))
        }
        _ => bail!("{id:?}: exactly one of start/anchor must be set"),
    }
}

/// `timeline.yaml` (already validated) + an optional transcript → a plan with plain
/// integer frame numbers and no more anchors, ready for `reconcile.py` to apply.
pub fn resolve(
    doc: &TimelineDoc,
    transcript: Option<&[Word]>,
    fps: u32,
) -> Result<ResolvedTimeline> {
    let mut shots = Vec::with_capacity(doc.shots.len());
    for shot in &doc.shots {
        let start_frame =
            resolve_position(&shot.id, shot.start, shot.anchor.as_ref(), transcript, fps)?;
        let transition = shot.transition.as_ref().map(|t| ResolvedTransition {
            kind: t.kind.clone(),
            duration_frames: (t.duration * fps as f64).round() as i64,
        });
        shots.push(ResolvedShot {
            id: shot.id.clone(),
            source: shot.source.clone(),
            start_frame,
            duration_frames: shot.duration,
            in_frame: shot.in_,
            transition,
        });
    }

    let mut audio = Vec::with_capacity(doc.audio.len());
    for track in &doc.audio {
        let start_frame = resolve_position(
            &track.id,
            track.start,
            track.anchor.as_ref(),
            transcript,
            fps,
        )?;
        audio.push(ResolvedAudio {
            id: track.id.clone(),
            path: track.path.clone(),
            start_frame,
        });
    }

    Ok(ResolvedTimeline {
        fps: doc.fps,
        resolution: doc.resolution,
        shots,
        audio,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn word(w: &str, start: f64, end: f64) -> Word {
        Word {
            word: w.to_string(),
            start,
            end,
        }
    }

    fn scene_shot(id: &str, start: Option<i64>, anchor: Option<Anchor>, duration: i64) -> Shot {
        Shot {
            id: id.to_string(),
            source: Source::Scene {
                blend: "compositions/frames/shot-01.blend".to_string(),
                scene: "GEN_hook".to_string(),
            },
            start,
            anchor,
            duration,
            in_: None,
            transition: None,
        }
    }

    #[test]
    fn valid_doc_has_no_errors() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", Some(0), None, 90)],
            audio: vec![],
        };
        assert!(validate(&doc).is_empty());
    }

    #[test]
    fn empty_shots_errors() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![],
            audio: vec![],
        };
        assert_eq!(validate(&doc).len(), 1);
    }

    #[test]
    fn duplicate_shot_id_errors() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![
                scene_shot("shot-01", Some(0), None, 90),
                scene_shot("shot-01", Some(90), None, 90),
            ],
            audio: vec![],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("duplicate id")));
    }

    #[test]
    fn both_start_and_anchor_set_errors() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot(
                "shot-01",
                Some(0),
                Some(Anchor {
                    word: "hi".into(),
                    occurrence: 1,
                    offset: 0.0,
                }),
                90,
            )],
            audio: vec![],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("exactly one of")));
    }

    #[test]
    fn non_positive_duration_errors() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", Some(0), None, 0)],
            audio: vec![],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("duration")));
    }

    #[test]
    fn resolve_passes_through_absolute_start() {
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", Some(42), None, 90)],
            audio: vec![],
        };
        let resolved = resolve(&doc, None, 30).unwrap();
        assert_eq!(resolved.shots[0].start_frame, 42);
    }

    #[test]
    fn resolve_finds_nth_anchor_occurrence() {
        let transcript = vec![
            word("the", 0.0, 0.2),
            word("data", 0.2, 0.6),
            word("data", 1.0, 1.4),
        ];
        let anchor = Anchor {
            word: "data".into(),
            occurrence: 2,
            offset: -0.1,
        };
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", None, Some(anchor), 90)],
            audio: vec![],
        };
        let resolved = resolve(&doc, Some(&transcript), 30).unwrap();
        // second "data" starts at 1.0s, offset -0.1s -> 0.9s * 30fps = 27
        assert_eq!(resolved.shots[0].start_frame, 27);
    }

    #[test]
    fn resolve_fails_loudly_on_missing_anchor_word() {
        let transcript = vec![word("hello", 0.0, 0.2)];
        let anchor = Anchor {
            word: "observability".into(),
            occurrence: 1,
            offset: 0.0,
        };
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", None, Some(anchor), 90)],
            audio: vec![],
        };
        let err = resolve(&doc, Some(&transcript), 30).unwrap_err();
        assert!(
            err.to_string().contains("observability") || {
                let chain: Vec<String> = err.chain().map(|e| e.to_string()).collect();
                chain.iter().any(|e| e.contains("observability"))
            }
        );
    }

    #[test]
    fn resolve_fails_loudly_on_missing_transcript() {
        let anchor = Anchor {
            word: "data".into(),
            occurrence: 1,
            offset: 0.0,
        };
        let doc = TimelineDoc {
            fps: 30,
            resolution: (1920, 1080),
            shots: vec![scene_shot("shot-01", None, Some(anchor), 90)],
            audio: vec![],
        };
        assert!(resolve(&doc, None, 30).is_err());
    }

    #[test]
    fn load_parses_real_yaml() {
        let dir = std::env::temp_dir().join(format!("cmt-timeline-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("timeline.yaml");
        std::fs::write(
            &path,
            "fps: 30\nresolution: [1920, 1080]\nshots:\n  - id: shot-01\n    source: {kind: scene, blend: compositions/frames/shot-01.blend, scene: GEN_hook}\n    start: 0\n    duration: 90\naudio: []\n",
        )
        .unwrap();
        let doc = parse(&path).unwrap();
        assert_eq!(doc.shots.len(), 1);
        assert_eq!(doc.shots[0].id, "shot-01");
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
