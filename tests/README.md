# Reel to Recipe API - Tests

## Structure

```
tests/
├── unit/                  # Unit tests for individual components
│   ├── api/              # API route tests
│   ├── services/         # Service layer tests
│   └── workers/          # Worker tests
├── integration/          # Integration tests
│   ├── test_api_flow.py  # Full API flow tests
│   └── test_workers.py   # Worker integration tests
├── conftest.py          # pytest fixtures and configuration
└── fixtures/            # Test data and fixtures
    ├── sample_videos/   # Sample video files for testing
    └── mock_data/       # JSON mock data
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -v

# Integration tests only
pytest tests/integration -v --docker

# With coverage
pytest --cov=api --cov=ai_worker --cov-report=html

# Specific test file
pytest tests/unit/api/test_extract.py -v
```

## Test Data

- Sample Instagram reel (short cooking video)
- Sample TikTok video (recipe format)
- Mock OCR output
- Mock transcription data
- Mock AI responses

## Fixtures

Key fixtures in `conftest.py`:
- `redis_client` - Redis test instance
- `test_app` - FastAPI test client
- `sample_job_data` - Mock job data
- `mock_video_data` - Mock processed video data
