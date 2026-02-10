use anyhow::{Context, Result};
use tracing::{info, warn};

use crate::video::FrameData;

/// Process frames with OCR to extract text
pub async fn process_frames(mut frames: Vec<FrameData>) -> Result<Vec<FrameData>> {
    info!("Processing OCR for {} frames", frames.len());
    
    // Process frames in parallel using rayon or async
    let mut tasks = Vec::new();
    
    for frame in &frames {
        let frame_path = frame.frame_path.clone();
        tasks.push(tokio::spawn(async move {
            extract_text_from_image(&frame_path).await
        }));
    }
    
    // Collect results
    for (i, task) in tasks.into_iter().enumerate() {
        match task.await {
            Ok(Ok(text)) => {
                if !text.trim().is_empty() {
                    frames[i].ocr_text = Some(text);
                }
            }
            Ok(Err(e)) => {
                warn!("OCR failed for frame {}: {}", frames[i].frame_path, e);
            }
            Err(e) => {
                warn!("Task panicked for frame: {}", e);
            }
        }
    }
    
    let text_frames = frames.iter().filter(|f| f.ocr_text.is_some()).count();
    info!("OCR complete: {}/{} frames contain text", text_frames, frames.len());
    
    Ok(frames)
}

/// Extract text from image using Tesseract OCR
async fn extract_text_from_image(image_path: &str) -> Result<String> {
    // Run OCR in a blocking task since leptess is not async
    let path = image_path.to_string();
    let text = tokio::task::spawn_blocking(move || {
        use leptess::{LepTess, Variable};
        
        let mut lt = LepTess::new(None, "eng")?;
        lt.set_image(&path)?;
        
        // Optimize for text detection
        lt.set_variable(Variable::TesseditPagesegMode, "6")?; // Assume uniform block of text
        lt.set_variable(Variable::TesseditCharWhitelist, None)?;
        
        Ok::<_, anyhow::Error>(lt.get_utf8_text()?)
    })
    .await
    .context("OCR task failed")??;
    
    Ok(text)
}