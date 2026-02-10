use anyhow::{Context, Result};
use redis::aio::Connection;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::time::Duration;
use tokio::time::timeout;
use tracing::{error, info, warn};
use uuid::Uuid;

use crate::audio;
use crate::download;
use crate::ocr;
use crate::video;

/// Video worker that processes jobs from Redis queue
pub struct VideoWorker {
    redis_client: redis::Client,
    group_name: String,
    consumer_name: String,
}

#[derive(Debug, Deserialize)]
struct QueueJob {
    job_id: String,
    #[serde(flatten)]
    data: serde_json::Value,
}

impl VideoWorker {
    pub async fn new(redis_url: &str, group_name: &str, consumer_name: Option<&str>) -> Result<Self> {
        let redis_client = redis::Client::open(redis_url).context("Failed to connect to Redis")?;
        
        // Create consumer group if it doesn't exist
        let mut conn = redis_client.get_async_connection().await?;
        let _: Result<(), _> = redis::cmd("XGROUP")
            .arg("CREATE")
            .arg("queue:video_processing")
            .arg(group_name)
            .arg("$")
            .arg("MKSTREAM")
            .query_async(&mut conn)
            .await;
        
        let consumer_name = consumer_name
            .map(|s| s.to_string())
            .unwrap_or_else(|| format!("consumer-{}", Uuid::new_v4()));
        
        info!(
            "Video worker initialized: group={}, consumer={}",
            group_name, consumer_name
        );
        
        Ok(Self {
            redis_client,
            group_name: group_name.to_string(),
            consumer_name,
        })
    }
    
    pub async fn run(&self) -> Result<()> {
        info!("Video worker started, waiting for jobs...");
        
        let output_dir = std::env::var("OUTPUT_DIR").unwrap_or_else(|_| "/tmp/videos".to_string());
        std::fs::create_dir_all(&output_dir)?;
        
        loop {
            match self.process_next_job(&output_dir).await {
                Ok(true) => {
                    // Job processed successfully
                }
                Ok(false) => {
                    // No job available, wait a bit
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
                Err(e) => {
                    error!("Error processing job: {}", e);
                    tokio::time::sleep(Duration::from_secs(5)).await;
                }
            }
        }
    }
    
    async fn process_next_job(&self, output_dir: &str) -> Result<bool> {
        let mut conn = self.redis_client.get_async_connection().await?;
        
        // Read from stream
        let result: Option<(String, Vec<(String, Vec<(String, String)>)>)> = redis::cmd("XREADGROUP")
            .arg("GROUP")
            .arg(&self.group_name)
            .arg(&self.consumer_name)
            .arg("COUNT")
            .arg(1)
            .arg("BLOCK")
            .arg(5000) // 5 second timeout
            .arg("STREAMS")
            .arg("queue:video_processing")
            .arg(">")
            .query_async(&mut conn)
            .await
            .ok()
            .flatten();
        
        let (stream_name, messages) = match result {
            Some((stream, msgs)) if !msgs.is_empty() => (stream, msgs),
            _ => return Ok(false), // No job available
        };
        
        let (message_id, fields) = &messages[0];
        
        // Parse job data
        let job_data: serde_json::Value = fields
            .iter()
            .find(|(k, _)| k == "data")
            .map(|(_, v)| serde_json::from_str(v).ok())
            .flatten()
            .or_else(|| {
                fields.iter()
                    .find(|(k, _)| k == "job_id")
                    .map(|(job_id, _)| {
                        json!({
                            "job_id": job_id.clone(),
                            "url": fields.iter().find(|(k, _)| k == "url").map(|(_, v)| v.clone()),
                        })
                    })
            })
            .context("Failed to parse job data")?;
        
        let job_id = job_data["job_id"]
            .as_str()
            .context("Job ID not found")?;
        
        let url = job_data["url"]
            .as_str()
            .context("URL not found")?;
        
        info!("Processing job {}: {}", job_id, url);
        
        // Update job status
        self.update_job_status(&mut conn, job_id, "downloading", 10).await?;
        
        // Step 1: Download video
        let video_result = download::download_video(url, &output_dir, job_id).await;
        
        match video_result {
            Ok(video_path) => {
                self.update_job_status(&mut conn, job_id, "processing_video", 25).await?;
                
                // Step 2: Process video metadata
                let video_info = match video::process_video(&video_path, &output_dir, job_id).await {
                    Ok(info) => info,
                    Err(e) => {
                        warn!("Failed to extract video metadata: {}", e);
                        self.fail_job(&mut conn, job_id, &format!("Video processing failed: {}", e)).await?;
                        self.ack_message(&mut conn, &stream_name, message_id).await?;
                        return Ok(true);
                    }
                };
                
                // Step 3: Extract frames
                self.update_job_status(&mut conn, job_id, "extracting_ocr", 40).await?;
                let frames = match video::extract_keyframes(&video_path, &output_dir, job_id).await {
                    Ok(f) => f,
                    Err(e) => {
                        warn!("Failed to extract frames: {}", e);
                        Vec::new()
                    }
                };
                
                // Step 4: OCR on frames
                let frames_with_ocr = match ocr::process_frames(frames).await {
                    Ok(f) => f,
                    Err(e) => {
                        warn!("OCR processing failed: {}", e);
                        Vec::new()
                    }
                };
                
                // Step 5: Extract audio
                self.update_job_status(&mut conn, job_id, "transcribing_audio", 60).await?;
                let audio_path = audio::extract_audio(&video_path, &output_dir, job_id).await.ok();
                
                // Step 6: Transcribe audio
                let transcription = if let Some(ref path) = audio_path {
                    audio::transcribe_audio(path).await.unwrap_or_default()
                } else {
                    String::new()
                };
                
                // Step 7: Queue for AI processing
                self.update_job_status(&mut conn, job_id, "ai_processing", 80).await?;
                
                let video_data = json!({
                    "job_id": job_id,
                    "video_path": video_path,
                    "duration_seconds": video_info.duration_seconds,
                    "resolution": {
                        "width": video_info.width,
                        "height": video_info.height,
                    },
                    "fps": video_info.fps,
                    "frames": frames_with_ocr,
                    "audio_path": audio_path,
                    "transcription": transcription,
                });
                
                // Send to AI queue
                redis::cmd("XADD")
                    .arg("queue:ai_processing")
                    .arg("*")
                    .arg("job_id")
                    .arg(job_id)
                    .arg("video_data")
                    .arg(video_data.to_string())
                    .query_async(&mut conn)
                    .await?;
                
                // Acknowledge message
                self.ack_message(&mut conn, &stream_name, message_id).await?;
                
                info!("Job {} sent to AI processing queue", job_id);
            }
            Err(e) => {
                error!("Failed to download video for job {}: {}", job_id, e);
                self.fail_job(&mut conn, job_id, &format!("Download failed: {}", e)).await?;
                self.ack_message(&mut conn, &stream_name, message_id).await?;
            }
        }
        
        Ok(true)
    }
    
    async fn update_job_status(
        &self,
        conn: &mut Connection,
        job_id: &str,
        status: &str,
        progress: i32,
    ) -> Result<()> {
        let job_key = format!("job:{}", job_id);
        
        let script = r#"
            local job = redis.call('get', KEYS[1])
            if job then
                local data = cjson.decode(job)
                data.status = ARGV[1]
                data.progress = tonumber(ARGV[2])
                data.updated_at = ARGV[3]
                redis.call('set', KEYS[1], cjson.encode(data))
                return 1
            end
            return 0
        "#;
        
        let now = chrono::Utc::now().to_rfc3339();
        
        // Use regular get/set since Lua cjson might not be available
        let job_data: Option<String> = redis::cmd("GET")
            .arg(&job_key)
            .query_async(conn)
            .await?;
        
        if let Some(data) = job_data {
            let mut job: serde_json::Value = serde_json::from_str(&data)?;
            job["status"] = json!(status);
            job["progress"] = json!(progress);
            job["updated_at"] = json!(now);
            
            redis::cmd("SET")
                .arg(&job_key)
                .arg(job.to_string())
                .query_async(conn)
                .await?;
        }
        
        Ok(())
    }
    
    async fn fail_job(&self, conn: &mut Connection, job_id: &str, error: &str) -> Result<()> {
        self.update_job_status(conn, job_id, "failed", 0).await?;
        
        let job_key = format!("job:{}", job_id);
        let job_data: Option<String> = redis::cmd("GET")
            .arg(&job_key)
            .query_async(conn)
            .await?;
        
        if let Some(data) = job_data {
            let mut job: serde_json::Value = serde_json::from_str(&data)?;
            job["error_message"] = json!(error);
            
            redis::cmd("SET")
                .arg(&job_key)
                .arg(job.to_string())
                .query_async(conn)
                .await?;
        }
        
        Ok(())
    }
    
    async fn ack_message(&self, conn: &mut Connection, stream: &str, id: &str) -> Result<()> {
        redis::cmd("XACK")
            .arg(stream)
            .arg(&self.group_name)
            .arg(id)
            .query_async(conn)
            .await?;
        
        Ok(())
    }
}