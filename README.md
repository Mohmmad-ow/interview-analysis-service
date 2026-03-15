# Interview Analysis Microservice

A high-performance FastAPI-based microservice for automated interview analysis using AI-powered transcription and evaluation. This service processes interview audio recordings, transcribes them using Whisper, and analyzes candidate responses using Google's Gemini AI to provide comprehensive feedback on technical skills, communication abilities, and key insights.

## Features

- **Audio Transcription**: Automatic speech-to-text using OpenAI's Whisper model
- **AI-Powered Analysis**: Intelligent evaluation using Google's Gemini AI
- **Dual Processing Modes**:
  - Synchronous processing for quick results (< 2 minutes)
  - Asynchronous processing for longer interviews with webhook callbacks
- **Multi-language Support**: English and Arabic transcription
- **Rate Limiting**: Tiered rate limits (Standard, Premium, Admin)
- **Authentication & Authorization**: JWT-based auth with role-based access
- **Audit Logging**: Comprehensive logging for compliance and monitoring
- **Database Integration**: MySQL for persistent storage, Redis for caching
- **Docker Support**: Containerized deployment with Docker Compose
- **Health Monitoring**: Built-in health checks and metrics

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Audio Input   │───▶│  Transcription  │───▶│   AI Analysis   │
│   (MP3/WAV)     │    │   (Whisper)     │    │   (Gemini AI)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Job Queue     │    │   Rate Limit    │    │   Results DB    │
│   (Redis)       │    │   (Redis)       │    │   (MySQL)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Tech Stack

- **Framework**: FastAPI with automatic OpenAPI documentation
- **AI/ML**:
  - OpenAI Whisper (faster-whisper) for transcription
  - Google Gemini AI for analysis
- **Database**: MySQL for persistent data, Redis for caching/rate limiting
- **Authentication**: JWT tokens with role-based access control
- **Deployment**: Docker with Docker Compose
- **Monitoring**: Structured logging with Loguru

## Quick Start

### Prerequisites

- Python 3.9+
- MySQL 8.0+
- Redis 6.0+
- FFmpeg (for audio processing)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd interview-analysis-service
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Start infrastructure**
   ```bash
   # Start MySQL and Redis (using Docker)
   docker run -d -p 3306:3306 --name mysql mysql:8.0
   docker run -d -p 6379:6379 --name redis redis:6.0
   ```

6. **Run database migrations**
   ```bash
   # The service will auto-create tables on startup
   ```

7. **Start the service**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

The API will be available at `http://localhost:8000` with documentation at `http://localhost:8000/docs`.

## API Usage

### Authentication

First, obtain a JWT token:

```bash
curl -X POST "http://localhost:8000/api/v1/create-token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "tier": "premium",
    "email": "user@example.com"
  }'
```

### Synchronous Analysis

For short interviews (< 2 minutes):

```bash
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "https://example.com/interview.mp3",
    "interview_id": "interview_123",
    "job_description": "Senior Python Developer with FastAPI experience",
    "language": "en"
  }'
```

### Asynchronous Analysis

For longer interviews with webhook callbacks:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze/async" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "https://example.com/interview.mp3",
    "interview_id": "interview_123",
    "job_description": "Senior Python Developer with FastAPI experience",
    "language": "en",
    "callback_url": "https://your-app.com/webhooks/analysis-complete"
  }'
```

### Check Job Status

```bash
curl -X GET "http://localhost:8000/api/v1/job/status/{job_id}" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_HOST` | localhost | MySQL server host |
| `MYSQL_USER` | root | MySQL username |
| `MYSQL_PASSWORD` | password | MySQL password |
| `MYSQL_DATABASE` | interview-analysis-database | Database name |
| `REDIS_URL` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis port |
| `SECRET_KEY` | auto-generated | JWT signing key |
| `STANDARD_RATE_LIMIT_MINUTE` | 5 | Standard tier requests per minute |
| `PREMIUM_RATE_LIMIT_MINUTE` | 20 | Premium tier requests per minute |

### Rate Limiting

The service implements tiered rate limiting:

- **Standard**: 5 requests/minute, 50/hour
- **Premium**: 20 requests/minute, 200/hour
- **Admin**: 100 requests/minute, unlimited/hour

## Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t interview-analysis-service ./docker

# Run with Docker Compose
docker-compose -f docker/docker-compose.yml up -d
```

### Docker Compose Configuration

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MYSQL_HOST=mysql
      - REDIS_URL=redis
    depends_on:
      - mysql
      - redis

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: interview-analysis-database

  redis:
    image: redis:6.0
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Project Structure

```
interview-analysis-service/
├── app/
│   ├── api/           # API routes and dependencies
│   ├── core/          # Core functionality (logging, middleware, etc.)
│   ├── database/      # Database models and repositories
│   ├── models/        # Pydantic models
│   ├── services/      # Business logic services
│   └── utils/         # Utility functions
├── tests/             # Unit and integration tests
├── docker/            # Docker configuration
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

## Monitoring & Logging

- **Health Checks**: `GET /health` endpoint
- **Structured Logging**: All logs include correlation IDs and user context
- **Audit Logging**: All analysis requests are logged for compliance
- **Error Tracking**: Comprehensive error logging with context

## Security

- JWT-based authentication with configurable expiration
- CORS protection with configurable origins
- Rate limiting to prevent abuse
- Input validation using Pydantic models
- Secure credential management via environment variables

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is private and proprietary.

## Support

For support or questions, please contact: mohmmadbaqiro31@gmail.com

## API Documentation

When running locally, visit `http://localhost:8000/docs` for interactive API documentation powered by Swagger UI.