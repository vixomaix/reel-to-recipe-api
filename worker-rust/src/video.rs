use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tracing::{info, warn};

/// Video metadata
#[derive(Debug, Serialize, Deserialize)]
pub struct VideoInfo {
    pub duration_seconds: f64,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub codec: String,
}

/// Process video and extract metadata
pub async fn process_video(video_path: &str, output_dir: &str, job_id: &str) -> Result<VideoInfo> {
    info!("Processing video: {}", video_path);
    
    // Use ffprobe to get video info
    let output = tokio::process::Command::new("ffprobe")
        .args(&[
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ])
        .output()
        .await
        .context("Failed to execute ffprobe")?;
    
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("ffprobe failed: {}", stderr);
    }
    
    let info: serde_json::Value = serde_json::from_slice(&output.stdout)?;
    
    let stream = info["streams"][0].clone();
    let format = info["format"].clone();
    
    // Parse frame rate (e.g., "30/1" -> 30.0)
    let fps_str = stream["r_frame_rate"].as_str().unwrap_or("30/1");
    let fps = parse_fps(fps_str)?;
    
    let video_info = VideoInfo {
        duration_seconds: format["duration"]
            .as_str()
            .unwrap_or("0")
            .parse()
            .unwrap_or(0.0),
        width: stream["width"].as_u64().unwrap_or(0) as u32,
        height: stream["height"].as_u64().unwrap_or(0) as u32,
        fps,
        codec: stream["codec_name"].as_str().unwrap_or("unknown").to_string(),
    };
    
    info!("Video info: {:?}", video_info);
    
    Ok(video_info)
}

fn parse_fps(fps_str: &str) -> Result<f64> {
    if fps_str.contains('/') {
        let parts: Vec<&str> = fps_str.split('/').collect();
        if parts.len() == 2 {
            let num: f64 = parts[0].parse()?;
            let den: f64 = parts[1].parse()?;
            if den != 0.0 {
                return Ok(num / den);
            }
        }
    }
    Ok(fps_str.parse().unwrap_or(30.0))
}

/// Extract keyframes at scene changes
pub async fn extract_keyframes(
    video_path: &str, 
    output_dir: &str, 
    job_id: &str
) -> Result<Vec<FrameData>> {
    use std::time::Duration;
    
    info!("Extracting keyframes from {}", video_path);
    
    let frames_dir = Path::new(output_dir).join(format!("{}_frames", job_id));
    std::fs::create_dir_all(&frames_dir)?;
    
    // Use ffmpeg scene detection to extract keyframes
    let scene_threshold = 0.3;
    let output_pattern = frames_dir.join("frame_%04d.jpg");
    
    let output = tokio::process::Command::new("ffmpeg")
        .args(&[
            "-i", video_path,
            "-vf", &format!("select='gt(scene,\,{})',showinfo", scene_threshold),
            "-vsync", "vfr",
            "-frame_pts", "1",
            "-q:v", "2",
            output_pattern.to_str().unwrap(),
        ])
        .output()
        .await
        .context("Failed to execute ffmpeg for frame extraction")?;
    
    // Also extract frames at regular intervals (every 2 seconds)
    let regular_pattern = frames_dir.join("regular_%04d.jpg");
    let _ = tokio::process::Command::new("ffmpeg")
        .args(&[
            "-i", video_path,
            "-vf", "fps=1/2,showinfo",
            "-frame_pts", "1",
            "-q:v", "2",
            regular_pattern.to_str().unwrap(),
        ])
        .output()
        .await;
    
    // Collect all extracted frames
    let mut frames = Vec::new();
    let entries = std::fs::read_dir(&frames_dir)?;
    
    for entry in entries {
        let entry = entry?;
        let path = entry.path();
        
        if let Some(ext) = path.extension() {
            if ext == "jpg" {
                // Extract timestamp from filename
                let filename = path.file_stem().unwrap().to_string_lossy();
                let timestamp = parse_timestamp(&filename).unwrap_or(0.0);
                let is_keyframe = filename.starts_with("frame_");
                
                frames.push(FrameData {
                    timestamp,
                    frame_path: path.to_string_lossy().to_string(),
                    ocr_text: None,
                    is_keyframe,
                });
            }
        }
    }
    
    // Sort by timestamp
    frames.sort_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap());
    
    info!("Extracted {} frames", frames.len());
    
    Ok(frames)
}

fn parse_timestamp(filename: &str) -> Option<f64> {
    // Parse timestamp from frame_pts filename
    // Format: frame_1234.jpg where 1234 is the frame number or timestamp
    if let Some(underscore_pos) = filename.rfind('_') {
        let num_str = &filename[underscore_pos + 1..];
        num_str.parse::<f64>().ok()
    } else {
        None
    }
}

/// Frame data structure
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct FrameData {
    pub timestamp: f64,
    pub frame_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ocr_text: Option<String>,
    pub is_keyframe: bool,
}