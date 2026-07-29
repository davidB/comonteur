//! `narrative.yaml` ingest — SPEC.md §5.3 production contract. First-cut schema (no
//! example given in the spec): shots with intent, target duration, VO/b-roll references.

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use std::collections::HashSet;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct Narrative {
    pub shots: Vec<Shot>,
}

#[derive(Debug, Deserialize)]
pub struct Shot {
    pub id: String,
    pub intent: String,
    pub target_duration: Option<f64>,
    // ponytail: parsed and validated now, consumed by M3/M4 scene authoring/reconcile,
    // not by this ingest-only crate.
    #[allow(dead_code)]
    pub vo: Option<String>,
    #[allow(dead_code)]
    pub broll: Option<String>,
}

pub fn load(path: &Path) -> Result<Narrative> {
    let text =
        std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
    serde_yaml_ng::from_str(&text).with_context(|| format!("parsing {}", path.display()))
}

/// Pure logic: fail loudly rather than guess (SPEC.md §5.2's anchor-resolution
/// philosophy applied here too).
pub fn validate(doc: &Narrative) -> Vec<String> {
    let mut errors = Vec::new();
    if doc.shots.is_empty() {
        errors.push("narrative.yaml: `shots` is empty".to_string());
    }
    let mut seen = HashSet::new();
    for (i, shot) in doc.shots.iter().enumerate() {
        if shot.id.trim().is_empty() {
            errors.push(format!("shots[{i}]: empty `id`"));
        } else if !seen.insert(shot.id.clone()) {
            errors.push(format!("shots[{i}]: duplicate id {:?}", shot.id));
        }
        if shot.intent.trim().is_empty() {
            errors.push(format!("shots[{i}] ({}): empty `intent`", shot.id));
        }
        if let Some(d) = shot.target_duration
            && d <= 0.0
        {
            errors.push(format!(
                "shots[{i}] ({}): target_duration must be > 0, got {d}",
                shot.id
            ));
        }
    }
    errors
}

pub fn parse(path: &Path) -> Result<Narrative> {
    let doc = load(path)?;
    let errors = validate(&doc);
    if !errors.is_empty() {
        bail!("{}", errors.join("\n"));
    }
    Ok(doc)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shot(id: &str, intent: &str, target_duration: Option<f64>) -> Shot {
        Shot {
            id: id.to_string(),
            intent: intent.to_string(),
            target_duration,
            vo: None,
            broll: None,
        }
    }

    #[test]
    fn valid_doc_has_no_errors() {
        let doc = Narrative {
            shots: vec![
                shot("shot-01", "Hook", Some(6.0)),
                shot("shot-02", "Payoff", None),
            ],
        };
        assert!(validate(&doc).is_empty());
    }

    #[test]
    fn empty_shots_errors() {
        let doc = Narrative { shots: vec![] };
        assert_eq!(validate(&doc).len(), 1);
    }

    #[test]
    fn duplicate_id_errors() {
        let doc = Narrative {
            shots: vec![shot("shot-01", "A", None), shot("shot-01", "B", None)],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("duplicate id")));
    }

    #[test]
    fn missing_intent_errors() {
        let doc = Narrative {
            shots: vec![shot("shot-01", "  ", None)],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("empty `intent`")));
    }

    #[test]
    fn non_positive_duration_errors() {
        let doc = Narrative {
            shots: vec![shot("shot-01", "Hook", Some(0.0))],
        };
        let errors = validate(&doc);
        assert!(errors.iter().any(|e| e.contains("target_duration")));
    }

    #[test]
    fn load_parses_real_yaml() {
        let dir = std::env::temp_dir().join(format!("cmt-narrative-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("narrative.yaml");
        std::fs::write(
            &path,
            "shots:\n  - id: shot-01\n    intent: Hook\n    target_duration: 6\n",
        )
        .unwrap();
        let doc = parse(&path).unwrap();
        assert_eq!(doc.shots.len(), 1);
        assert_eq!(doc.shots[0].id, "shot-01");
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
