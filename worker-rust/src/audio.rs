use anyhow::{Context, Result};
use std::path::Path;
use tracing::{info, warn};

/// Extract audio from video file
pub async fn extract_audio(video_path: &str, output_dir: &str, job_id: &str) -> Result<String> {
    info!("Extracting audio from {}", video_path);
    
    let output_path = Path::new(output_dir).join(format!("{}_audio.wav", job_id));
    let output_str = output_path.to_string_lossy();
    
    let output = tokio::process::Command::new("ffmpeg")
        .args(&[
            "-i", video_path,
            "-vn", // No video
            "-acodec", "pcm_s16le",
            "-ar", "16000", // 16kHz for Whisper
            "-ac", "1", // Mono
            "-y", // Overwrite
            &output_str,
        ])
        .output()
        .await
        .context("Failed to execute ffmpeg for audio extraction")?;
    
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        warn!("Audio extraction had issues: {}", stderr);
        // Continue anyway, audio might not exist
    }
    
    if output_path.exists() {
        info!("Audio extracted to {}", output_str);
        Ok(output_str.to_string())
    } else {
        anyhow::bail!("Audio file was not created")
    }
}

/// Transcribe audio using Whisper
pub async fn transcribe_audio(audio_path: &str) -> Result<String> {
    info!("Transcribing audio: {}", audio_path);
    
    // For now, we'll use the whisper command-line tool
    // In production, you'd use whisper-rs with a loaded model
    let output = tokio::process::Command::new("whisper")
        .args(&[
            audio_path,
            "--model", "base",
            "--language", "en",
            "--output_format", "txt",
            "--output_dir", "/tmp",
        ])
        .output()
        .await;
    
    match output {
        Ok(output) => {
            if output.status.success() {
                // Read the transcription file
                let txt_path = format!("{}.txt", audio_path.trim_end_matches(".wav"));
                if Path::new(&txt_path).exists() {
                    let text = tokio::fs::read_to_string(&txt_path).await?;
                    info!("Transcription complete: {} characters", text.len());
                    return Ok(text);
                }
            }
            // If whisper CLI fails or isn't available, return empty string
            warn!("Whisper transcription failed or not available");
            Ok(String::new())
        }
        Err(e) => {
            warn!("Whisper not available: {}", e);
            Ok(String::new())
        }
    }
}