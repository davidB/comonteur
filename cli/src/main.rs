//! comonteur CLI — SPEC.md §10 M2. Ingest-only for now (narrative/manifest/captions);
//! `doctor`/`setup`/`new` are M5.5 scope, not built here.

mod captions;
mod manifest;
mod narrative;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand, ValueEnum};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "comonteur")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Ingest a production-contract input (SPEC.md §5.3)
    Ingest {
        #[command(subcommand)]
        target: IngestTarget,
    },
}

#[derive(Subcommand)]
enum IngestTarget {
    /// Validate narrative.yaml
    Narrative { path: PathBuf },
    /// Build assets/manifest.json from an assets directory
    Manifest {
        assets_dir: PathBuf,
        #[arg(short, long)]
        out: Option<PathBuf>,
    },
    /// Normalize word-level timing into captions/*.json
    Captions {
        input: PathBuf,
        #[arg(long, value_enum)]
        kind: CaptionsKind,
        #[arg(short, long)]
        out: PathBuf,
    },
}

#[derive(Clone, ValueEnum)]
enum CaptionsKind {
    Whisper,
    Tts,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Ingest { target } => match target {
            IngestTarget::Narrative { path } => {
                let doc = narrative::parse(&path)?;
                println!("OK: {} shot(s)", doc.shots.len());
            }
            IngestTarget::Manifest { assets_dir, out } => {
                let out = out.unwrap_or_else(|| assets_dir.join("manifest.json"));
                let m = manifest::build_manifest(&assets_dir, &out)?;
                println!("wrote {} ({} asset(s))", out.display(), m.len());
            }
            IngestTarget::Captions { input, kind, out } => {
                let text = std::fs::read_to_string(&input)
                    .with_context(|| format!("reading {}", input.display()))?;
                let v: serde_json::Value = serde_json::from_str(&text)
                    .with_context(|| format!("parsing {}", input.display()))?;
                let words = match kind {
                    CaptionsKind::Whisper => captions::from_whisper_json(&v),
                    CaptionsKind::Tts => captions::from_timing_marks(&v),
                };
                let out_doc = captions::Captions { words };
                std::fs::write(&out, serde_json::to_string_pretty(&out_doc)?)
                    .with_context(|| format!("writing {}", out.display()))?;
                println!("wrote {} ({} word(s))", out.display(), out_doc.words.len());
            }
        },
    }
    Ok(())
}
