//! `assets/manifest.json` ingest — SPEC.md §5.3: content-addressed by sha256, per-asset
//! duration/fps/resolution/has_alpha/codec from `ffprobe`.

use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ProbeInfo {
    pub duration: Option<f64>,
    pub fps: Option<f64>,
    pub resolution: Option<[u64; 2]>,
    pub has_alpha: bool,
    pub codec: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct AssetEntry {
    pub sha256: String,
    pub path: String,
    #[serde(flatten)]
    pub probe: ProbeInfo,
}

pub type Manifest = BTreeMap<String, AssetEntry>;

const ALPHA_PIX_FMTS: &[&str] = &[
    "rgba", "bgra", "argb", "abgr", "ya8", "ya16le", "ya16be", "gbrap",
];

fn has_alpha(pix_fmt: &str) -> bool {
    ALPHA_PIX_FMTS.contains(&pix_fmt) || pix_fmt.starts_with("yuva")
}

fn parse_rate(rate: &str) -> Option<f64> {
    let (num, den) = rate.split_once('/')?;
    let (num, den): (f64, f64) = (num.parse().ok()?, den.parse().ok()?);
    if den == 0.0 { None } else { Some(num / den) }
}

/// Pure function over an already-parsed `ffprobe -show_format -show_streams
/// -print_format json` value — unit-tested against literal fixtures, no subprocess.
pub fn parse_probe(probe_json: &Value) -> ProbeInfo {
    let streams = probe_json
        .get("streams")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let video = streams
        .iter()
        .find(|s| s.get("codec_type").and_then(Value::as_str) == Some("video"));
    let primary = video.or_else(|| streams.first());

    let duration = primary
        .and_then(|s| s.get("duration"))
        .or_else(|| probe_json.get("format").and_then(|f| f.get("duration")))
        .and_then(Value::as_str)
        .and_then(|s| s.parse::<f64>().ok());

    let fps = video
        .and_then(|s| s.get("r_frame_rate"))
        .and_then(Value::as_str)
        .and_then(parse_rate);

    let resolution = primary.and_then(|s| {
        let w = s.get("width").and_then(Value::as_u64)?;
        let h = s.get("height").and_then(Value::as_u64)?;
        Some([w, h])
    });

    let pix_fmt = primary
        .and_then(|s| s.get("pix_fmt"))
        .and_then(Value::as_str);
    let codec = primary
        .and_then(|s| s.get("codec_name"))
        .and_then(Value::as_str)
        .map(str::to_string);

    ProbeInfo {
        duration,
        fps,
        resolution,
        has_alpha: pix_fmt.is_some_and(has_alpha),
        codec,
    }
}

pub fn sha256_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path).with_context(|| format!("opening {}", path.display()))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    let digest = hasher.finalize();
    Ok(digest.iter().map(|b| format!("{b:02x}")).collect())
}

fn run_ffprobe(path: &Path) -> Result<Value> {
    let out = Command::new("ffprobe")
        .args([
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ])
        .arg(path)
        .output()
        .context("running ffprobe (is it on PATH? see `comonteur doctor`)")?;
    if !out.status.success() {
        anyhow::bail!(
            "ffprobe failed on {}: {}",
            path.display(),
            String::from_utf8_lossy(&out.stderr)
        );
    }
    serde_json::from_slice(&out.stdout).context("parsing ffprobe JSON output")
}

pub fn probe_asset(path: &Path, rel_path: &str) -> Result<AssetEntry> {
    let sha256 = sha256_file(path)?;
    let probe_json = run_ffprobe(path)?;
    Ok(AssetEntry {
        sha256,
        path: rel_path.to_string(),
        probe: parse_probe(&probe_json),
    })
}

pub fn build_manifest(assets_dir: &Path, out_path: &Path) -> Result<Manifest> {
    let mut manifest = Manifest::new();
    for entry in walk_files(assets_dir)? {
        let rel = entry
            .strip_prefix(assets_dir)
            .unwrap_or(&entry)
            .to_string_lossy()
            .replace('\\', "/");
        if rel == "manifest.json" {
            continue;
        }
        let asset = probe_asset(&entry, &rel)?;
        manifest.insert(asset.sha256.clone(), asset);
    }
    let json = serde_json::to_string_pretty(&manifest)?;
    fs::write(out_path, json).with_context(|| format!("writing {}", out_path.display()))?;
    Ok(manifest)
}

fn walk_files(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();
    for entry in fs::read_dir(dir).with_context(|| format!("reading {}", dir.display()))? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with('.') {
            continue;
        }
        if path.is_dir() {
            files.extend(walk_files(&path)?);
        } else {
            files.push(path);
        }
    }
    Ok(files)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn plain_video_no_alpha() {
        let probe = json!({
            "format": {"duration": "12.5"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                 "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}
            ]
        });
        let info = parse_probe(&probe);
        assert_eq!(info.duration, Some(12.5));
        assert_eq!(info.fps, Some(30.0));
        assert_eq!(info.resolution, Some([1920, 1080]));
        assert!(!info.has_alpha);
        assert_eq!(info.codec.as_deref(), Some("h264"));
    }

    #[test]
    fn video_with_alpha() {
        let probe = json!({
            "format": {"duration": "3.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "prores", "width": 800, "height": 600,
                 "pix_fmt": "yuva444p10le", "r_frame_rate": "24/1"}
            ]
        });
        assert!(parse_probe(&probe).has_alpha);
    }

    #[test]
    fn audio_only_has_no_resolution_or_fps() {
        let probe = json!({
            "format": {"duration": "45.2"},
            "streams": [
                {"codec_type": "audio", "codec_name": "pcm_s24le"}
            ]
        });
        let info = parse_probe(&probe);
        assert_eq!(info.duration, Some(45.2));
        assert_eq!(info.fps, None);
        assert_eq!(info.resolution, None);
        assert!(!info.has_alpha);
        assert_eq!(info.codec.as_deref(), Some("pcm_s24le"));
    }

    #[test]
    fn no_streams_returns_none_fields() {
        let probe = json!({"format": {}, "streams": []});
        let info = parse_probe(&probe);
        assert_eq!(info.duration, None);
        assert_eq!(info.resolution, None);
        assert_eq!(info.codec, None);
    }

    #[test]
    fn sha256_matches_known_vector() {
        let dir = std::env::temp_dir().join(format!("cmt-manifest-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hello.txt");
        fs::write(&path, b"hello world").unwrap();
        let hash = sha256_file(&path).unwrap();
        assert_eq!(
            hash,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
        fs::remove_dir_all(&dir).unwrap();
    }
}
