# Document Analysis Service

A FastAPI-based microservice for intelligent document analysis using AI-powered processing. This service analyzes documents such as resumes, extracting structured information, scoring against job requirements, and providing detailed insights.

## Features

- **AI-Powered Analysis**: Utilizes Google's Gemini AI for advanced document understanding and analysis
- **Multi-Format Support**: Processes PDF files, Word documents (.docx, .doc), and images (.jpg, .jpeg, .png, .tiff)
- **Synchronous & Asynchronous Processing**: Supports both immediate analysis and queued processing for large documents
- **User Authentication & Authorization**: JWT-based auth with user tiers (Standard, Premium, Admin)
- **Rate Limiting**: Tiered rate limits to manage API usage
- **Audit Logging**: Comprehensive logging of all operations for compliance and debugging
- **Database Integration**: MySQL for data persistence with SQLAlchemy ORM
- **Caching**: Redis-based caching for improved performance
- **Webhook Support**: Configurable webhooks for async job completion notifications
- **Health Monitoring**: Built-in health checks and metrics
- **CORS Support**: Configurable CORS for web integration

## Architecture

The service follows a modular architecture:

- **API Layer** (`app/api/`): FastAPI routers and endpoints
- **Core Services** (`app/core/`): Logging, middleware, security, Redis integration
- **Business Logic** (`app/services/`): Analysis services, auth, rate limiting, webhooks
- **Data Layer** (`app/database/`): Models, repositories, connection management
- **Models** (`app/models/`): Pydantic models for requests/responses
- **Utilities** (`app/utils/`): Helper functions and validators

## Prerequisites

- Python 3.8+
- MySQL 8.0+
- Redis 6.0+
- Google Gemini API key

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd document-analysis-service
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:
   ```env
   # Database
   MYSQL_HOST=localhost
   MYSQL_USER=your_mysql_user
   MYSQL_PASSWORD=your_mysql_password
   MYSQL_DATABASE=document_analysis_db

   # Redis
   REDIS_URL=localhost
   REDIS_PASSWORD=your_redis_password  # Optional

   # AI Service
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-1.5-flash  # Or your preferred model

   # Security
   SECRET_KEY=your_secret_key_here

   # Other settings as needed
   ```

5. Set up the database:
   - Create a MySQL database named `document_analysis_db`
   - Run database migrations (if using Alembic):
     ```bash
     alembic upgrade head
     ```

## Usage

### Running the Service

Start the development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

When running in debug mode, access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Key Endpoints

- `POST /api/v1/documents/analyze` - Synchronous document analysis
- `POST /api/v1/documents/analyze-async` - Asynchronous document analysis
- `GET /api/v1/documents/job/{job_id}` - Check async job status
- `GET /api/v1/documents/jobs/results` - Get batch job results
- `POST /api/v1/documents/create-token` - Create analysis token
- `GET /health` - Health check

### Example Usage

```python
import requests

# Synchronous analysis
response = requests.post(
    "http://localhost:8000/api/v1/documents/analyze",
    headers={"Authorization": "Bearer your_token"},
    json={
        "document_content": "extracted text from document",
        "job_description": "Software Engineer position requirements",
        "required_skills": ["Python", "FastAPI", "SQL"],
        "preferred_skills": ["Docker", "Kubernetes"]
    }
)

print(response.json())
```

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Deployment

### Docker (Not yet configured)

Docker setup is planned but not implemented. Future deployment will include:
- Multi-stage Dockerfile for optimized images
- Docker Compose for local development with MySQL and Redis
- Kubernetes manifests for production deployment

### Environment Variables

See the configuration section above for all available environment variables.

## Configuration

The service uses Pydantic settings for configuration. Key settings include:

- **API Settings**: Version strings, debug mode
- **Security**: JWT secrets, token expiration
- **Database**: MySQL connection parameters
- **Redis**: Caching and rate limiting configuration
- **Rate Limits**: Tier-based API limits
- **CORS**: Allowed origins and headers

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is private property and not licensed for public use.

## Contact

For questions or support, contact: mohmmadbaqiro31@gmail.com