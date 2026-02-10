use anyhow::{Context, Result};
use std::path::{Path, PathBuf};
use tracing::{info, warn};
use uuid::Uuid;

/// Download video from URL using yt-dlp
pub async fn download_video(url: &str, output_dir: &str, job_id: &str) -> Result<String> {
    let output_path = Path::new(output_dir).join(format!("{}_video.%(ext)s", job_id));
    let output_template = output_path.to_string_lossy();
    
    info!("Downloading video to {}", output_template);
    
    let output = tokio::process::Command::new("yt-dlp")
        .args(&[
            "--format", "best[height<=1080]",
            "--output", &output_template,
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            url,
        ])
        .output()
        .await
        .context("Failed to execute yt-dlp")?;
    
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("yt-dlp failed: {}", stderr);
    }
    
    // Find the downloaded file
    let dir = std::fs::read_dir(output_dir)?;
    for entry in dir {
        let entry = entry?;
        let path = entry.path();
        if let Some(name) = path.file_stem() {
            if name.to_string_lossy().starts_with(&format!("{}_video", job_id)) {
                return Ok(path.to_string_lossy().to_string());
            }
        }
    }
    
    anyhow::bail!("Downloaded video file not found")
}