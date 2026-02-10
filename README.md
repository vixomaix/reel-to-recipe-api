# Reel to Recipe API

Extract recipes from Instagram Reels, TikTok videos, and YouTube Shorts using AI-powered video analysis.

## Architecture

This project uses a hybrid Rust + Python architecture for optimal performance:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  FastAPI    │────▶│    Redis    │◀────│ Rust Worker │
│   (API)     │     │    Queue    │     │   (Video)   │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       │                                       ▼
       │                                ┌─────────────┐
       │                                │  FFmpeg /   │
       │                                │  Tesseract  │
       │                                └─────────────┘
       │
       ▼
┌─────────────┐
│  AI Worker  │
│  (Python)   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ OpenAI /    │
│ Anthropic   │
└─────────────┘
```

### Components

| Component | Language | Purpose |
|-----------|----------|---------|
| API | Python (FastAPI) | HTTP API for job submission and status |
| Rust Worker | Rust | Video download, frame extraction, OCR, audio transcription |
| AI Worker | Python | Recipe extraction using LLMs (OpenAI/Anthropic) |
| Redis | - | Job queue and result storage |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key (or Anthropic)

### Running with Docker

1. Clone the repository:
```bash
git clone https://github.com/yourusername/reel-to-recipe-api.git
cd reel-to-recipe-api
```

2. Set environment variables:
```bash
export OPENAI_API_KEY=your-api-key
# Or for Anthropic:
# export AI_PROVIDER=anthropic
# export ANTHROPIC_API_KEY=your-api-key
```

3. Start all services:
```bash
docker-compose up -d
```

4. Check the API is running:
```bash
curl http://localhost:8000/health
```

## API Usage

### Submit a video for processing

```bash
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.instagram.com/reel/ABC123/",
    "preferred_language": "en"
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Video extraction queued successfully",
  "check_status_url": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

### Check job status

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
```

### Get the extracted recipe

```bash
curl http://localhost:8000/api/v1/recipe/{job_id}
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Creamy Garlic Pasta",
  "description": "A quick and delicious creamy garlic pasta recipe",
  "ingredients": [
    {
      "name": "pasta",
      "quantity": "300",
      "unit": "g",
      "optional": false
    },
    {
      "name": "garlic",
      "quantity": "4",
      "unit": "cloves",
      "optional": false
    }
  ],
  "instructions": [
    {
      "step_number": 1,
      "description": "Boil pasta according to package instructions",
      "timestamp_start": 15.5,
      "timestamp_end": 45.2
    }
  ],
  "cook_time_minutes": 15,
  "prep_time_minutes": 5,
  "servings": 4,
  "difficulty": "easy",
  "tags": ["pasta", "garlic", "quick"],
  "source_url": "https://www.instagram.com/reel/ABC123/",
  "confidence_score": 0.94
}
```

## Development

### Running locally

#### 1. Start Redis
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

#### 2. Run the API
```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### 3. Run the Rust Worker
```bash
cd worker-rust
cargo run -- worker
```

#### 4. Run the AI Worker
```bash
cd ai-worker
pip install -r requirements.txt
python main.py
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `OPENAI_API_KEY` | OpenAI API key | Required for AI worker |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o` |
| `AI_PROVIDER` | AI provider to use | `openai` |
| `ANTHROPIC_API_KEY` | Anthropic API key | Alternative to OpenAI |
| `ANTHROPIC_MODEL` | Anthropic model | `claude-3-opus-20240229` |
| `OUTPUT_DIR` | Directory for video files | `/tmp/videos` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

## API Documentation

When running locally, API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## How It Works

1. **Video Download**: The Rust worker downloads the video using yt-dlp
2. **Frame Extraction**: Keyframes are extracted using FFmpeg scene detection
3. **OCR**: Text is extracted from frames using Tesseract OCR
4. **Audio Extraction**: Audio is extracted and transcribed using Whisper
5. **AI Processing**: All extracted data is sent to an LLM (GPT-4 or Claude) for recipe extraction
6. **Structured Output**: The AI returns a structured recipe with ingredients, instructions, and metadata

## License

MIT License - see LICENSE file for details.