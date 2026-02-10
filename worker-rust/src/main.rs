use anyhow::Result;
use clap::{Parser, Subcommand};
use std::sync::Arc;
use tracing::{info, error};

mod audio;
mod download;
mod ocr;
mod video;
mod worker;

use worker::VideoWorker;

#[derive(Parser)]
#[command(name = "worker-rust")]
#[command(about = "Rust video processor for Reel to Recipe")]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
    
    /// Redis URL
    #[arg(long, env = "REDIS_URL", default_value = "redis://localhost:6379")]
    redis_url: String,
}

#[derive(Subcommand)]
enum Commands {
    /// Run as a worker processing jobs from Redis queue
    Worker {
        /// Consumer group name
        #[arg(long, default_value = "video-workers")]
        group: String,
        /// Consumer name (auto-generated if not provided)
        #[arg(long)]
        consumer: Option<String>,
    },
    /// Process a single video file (CLI mode)
    Process {
        /// Video URL to download and process
        #[arg(short, long)]
        url: String,
        /// Output directory
        #[arg(short, long, default_value = "./output")]
        output: String,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt::init();
    
    let cli = Cli::parse();
    
    match cli.command {
        Some(Commands::Worker { group, consumer }) => {
            info!("Starting video worker...");
            let worker = VideoWorker::new(&cli.redis_url, &group, consumer.as_deref()).await?;
            worker.run().await?;
        }
        Some(Commands::Process { url, output }) => {
            info!("Processing single video: {}", url);
            process_single_video(&url, &output).await?;
        }
        None => {
            // Default to worker mode
            info!("Starting video worker (default mode)...");
            let worker = VideoWorker::new(&cli.redis_url, "video-workers", None).await?;
            worker.run().await?;
        }
    }
    
    Ok(())
}

async fn process_single_video(url: &str, output_dir: &str) -> Result<()> {
    use std::path::Path;
    use uuid::Uuid;
    
    let job_id = Uuid::new_v4().to_string();
    std::fs::create_dir_all(output_dir)?;
    
    info!("Job {}: Downloading video from {}", job_id, url);
    let video_path = download::download_video(url, output_dir, &job_id).await?;
    
    info!("Job {}: Processing video", job_id);
    let video_info = video::process_video(&video_path, output_dir, &job_id).await?;
    
    info!("Job {}: Extracting frames", job_id);
    let frames = video::extract_keyframes(&video_path, output_dir, &job_id).await?;
    
    info!("Job {}: Running OCR on frames", job_id);
    let frames_with_ocr = ocr::process_frames(frames).await?;
    
    info!("Job {}: Extracting audio", job_id);
    let audio_path = audio::extract_audio(&video_path, output_dir, &job_id).await?;
    
    info!("Job {}: Transcribing audio", job_id);
    let transcription = audio::transcribe_audio(&audio_path).await?;
    
    // Save results
    let result = serde_json::json!({
        "job_id": job_id,
        "video_path": video_path,
        "video_info": video_info,
        "frames": frames_with_ocr,
        "audio_path": audio_path,
        "transcription": transcription,
    });
    
    let result_path = Path::new(output_dir).join(format!("{}_result.json", job_id));
    std::fs::write(&result_path, serde_json::to_string_pretty(&result)?)?;
    
    info!("Job {}: Complete! Results saved to {:?}", job_id, result_path);
    
    Ok(())
}