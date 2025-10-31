# MPI Service

Enterprise-grade Master Patient Index service with **Domain-Driven Design** architecture, centralized configuration, and modular provider system.

## 🏗️ Architecture

Built with **Controller/Service/Repository** pattern and domain-based organization:

```
src/
├── main.py                    # Application entry point
├── core/
│   ├── config.py             # Centralized configuration
│   ├── database.py           # Database abstractions
│   ├── cache.py              # Cache abstractions
│   └── dependencies.py      # Dependency injection
├── domains/
│   ├── patient/             # Patient management
│   ├── matching/            # MPI matching logic
│   ├── admin/               # Administrative operations
│   ├── monitoring/          # System monitoring
│   └── config/              # Configuration management
└── providers/               # External provider integrations
    ├── verato.py           # Verato integration
    ├── internal.py         # Internal matching
    └── hybrid.py           # Multi-provider strategies
```

## ✨ Features

### **Domain-Driven Design**
- Clear domain boundaries with Controller/Service/Repository layers
- Centralized configuration with environment-specific validation
- Dependency injection for clean testing and modularity

### **Multi-Provider Support**
- **Verato**: External matching service integration
- **Internal**: Probabilistic matching with fuzzy logic
- **Hybrid**: Multi-strategy provider (parallel, consensus, fallback)

### **Performance Optimized**
- **uvloop**: 2-4x faster async performance
- **orjson**: High-speed JSON serialization
- **Multi-level caching**: Memory → Redis → MongoDB → Provider API
- **Connection pooling**: Database, Redis, and HTTP connections
- **Batch processing**: Configurable concurrency and batch sizes

### **Security & Compliance**
- **PHI protection**: Hash-based storage, correlation IDs for bulk operations
- **Minimal data storage**: Only matching keys, not full patient records
- **Audit trails**: Complete operation logging with correlation tracking
- **HIPAA-ready**: Designed for healthcare compliance requirements

### **Production Ready**
- **Health checks**: Liveness and readiness probes for Kubernetes
- **Monitoring**: Prometheus metrics and alerting
- **Configuration management**: Environment-based settings with validation
- **Docker deployment**: Multi-stage optimized containers

## 🚀 Quick Start

### Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set environment variables**:
```bash
export MPI_PROVIDER=internal                    # or verato, hybrid
export ENVIRONMENT=development
export REDIS_HOST=localhost
export MONGODB_URI=mongodb://localhost:27017
export MPI_DB=mpi_service
```

3. **Run the service**:
```bash
python src/main.py
```

### Docker Deployment

1. **Build and run with Docker Compose**:
```bash
docker-compose up --build
```

2. **Access the service**:
- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/api/v1/monitoring/metrics/prometheus

## 📡 API Endpoints

### **Matching APIs**

#### Single Patient Match
```bash
POST /mpi/match
{
  "patient_data": {
    "ssn": "123-45-6789",
    "first_name": "John",
    "last_name": "Smith",
    "dob": "1980-01-01"
  }
}

# Response
{
  "mpi_id": "MPI-ABC12345",
  "confidence": 0.95,
  "provider": "internal",
  "processing_time_ms": 12.5
}
```

#### Bulk Match with Correlation IDs
```bash
POST /mpi/bulk-match
{
  "patients": [
    {
      "correlation_id": "req-001",
      "patient_data": {
        "ssn": "123-45-6789",
        "first_name": "John",
        "last_name": "Smith"
      }
    }
  ],
  "return_phi": false
}

# Response (no PHI returned)
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_records": 1,
  "successful": 1,
  "failed": 0,
  "results": [
    {
      "correlation_id": "req-001",
      "mpi_id": "MPI-ABC12345",
      "confidence": 0.95,
      "status": "success"
    }
  ]
}
```

### **Patient Management APIs**

```bash
# Get patient by MPI ID
GET /api/v1/patients/{mpi_id}

# Search patients
POST /api/v1/patients/search
{
  "ssn": "123-45-6789",
  "fuzzy_match": true,
  "confidence_threshold": 0.8
}

# Get patient identifiers
GET /api/v1/patients/{mpi_id}/identifiers

# Get patient history
GET /api/v1/patients/{mpi_id}/history?days=30
```

### **Administrative APIs**

```bash
# Merge patients
POST /api/v1/admin/merge

# Manage duplicates
GET /api/v1/admin/duplicates/candidates

# Data quality reports
GET /api/v1/admin/quality/report
```

### **Monitoring APIs**

```bash
# System health
GET /api/v1/monitoring/health

# Performance metrics
GET /api/v1/monitoring/metrics/performance?period=24h

# Cache statistics
GET /api/v1/monitoring/metrics/cache
```

## ⚙️ Configuration

### **Centralized Configuration**

All configuration is managed through `src/core/config.py` with environment-specific validation:

| Category | Variable | Description | Default |
|----------|----------|-------------|---------|
| **App** | `APP_NAME` | Application name | MPI Service |
| | `ENVIRONMENT` | Environment (development/production) | development |
| | `DEBUG` | Enable debug mode | true |
| **Provider** | `MPI_PROVIDER` | Provider (verato/internal/hybrid) | internal |
| | `VERATO_API_KEY` | Verato API key | - |
| | `VERATO_ENDPOINT` | Verato endpoint URL | - |
| **Database** | `MONGODB_URI` | MongoDB connection string | mongodb://localhost:27017 |
| | `MPI_DB` | Database name | mpi_service |
| | `MONGO_POOL_SIZE` | Connection pool size | 50 |
| **Cache** | `REDIS_HOST` | Redis hostname | localhost |
| | `REDIS_PORT` | Redis port | 6379 |
| | `REDIS_POOL_SIZE` | Redis connection pool | 50 |
| | `CACHE_TTL` | Default cache TTL (seconds) | 3600 |
| **Performance** | `CONNECTION_POOL_SIZE` | HTTP connection pool | 100 |
| | `BATCH_SIZE` | Batch processing size | 100 |
| | `REQUEST_TIMEOUT` | Request timeout (seconds) | 30 |

### **Provider Strategies**

#### Internal Provider
- Probabilistic matching with configurable thresholds
- Soundex phonetic matching for names
- Multi-field scoring with confidence calculation

#### Verato Provider
- Integration with Verato Connect API
- Production-grade matching service
- Handles complex patient demographics

#### Hybrid Provider
- **Parallel**: Run multiple providers concurrently
- **Consensus**: Require agreement between providers
- **Fallback**: Primary provider with backup
- **Best Confidence**: Choose highest confidence result

## 🔧 Development

### **Running Tests**
```bash
# Unit tests
pytest tests/ -v

# Provider tests
python test_providers_simple.py

# Integration tests
python test_providers.py
```

### **Code Quality**
```bash
# Formatting
black src/

# Type checking
mypy src/

# Linting
ruff src/
```

### **Performance Profiling**
```bash
# CPU profiling
py-spy record -o profile.svg -- python src/main.py

# Memory profiling
mprof run python src/main.py && mprof plot
```

## 📊 Monitoring & Observability

### **Health Checks**
- **Liveness**: `/health` - Basic service availability
- **Readiness**: `/api/v1/monitoring/health/readiness` - All dependencies ready
- **Deep Health**: `/api/v1/monitoring/health` - Comprehensive system status

### **Metrics**
- **Prometheus**: `/api/v1/monitoring/metrics/prometheus`
- **Performance**: Request duration, throughput, error rates
- **Cache**: Hit/miss rates across all cache levels
- **Provider**: Success rates, latency, error tracking

### **Alerting**
- Configurable alert thresholds
- Provider failure detection
- Performance degradation monitoring
- Cache failure notifications

## 🏛️ Data Architecture

### **Minimal Persistence Strategy**
```javascript
// Only stores matching keys, not full patient data
{
  "mpi_id": "MPI-ABC123",
  "ssn_hash": "hashed_value",           // Hashed for privacy
  "match_keys": {
    "first_name_soundex": "J500",       // Phonetic encoding
    "last_name_soundex": "S530",
    "dob": "1980-01-01",
    "ssn_last4": "6789"
  },
  "confidence": 0.95,
  "source": "internal",
  "created_at": "2024-10-31T...",
  "last_accessed": "2024-10-31T..."
}
```

### **Cache Strategy**
```
L1: Memory Cache    (<1ms)   - Hot path data
L2: Redis Cache     (<5ms)   - Session data
L3: MongoDB Cache   (<20ms)  - Computed results
L4: Provider API    (50-500ms) - External calls
```

## 🔐 Security

- **No PHI Storage**: Only hashed identifiers and matching keys
- **Correlation IDs**: Bulk operations without PHI transmission
- **Audit Trails**: Complete operation logging
- **Access Control**: API key management and rate limiting
- **Encryption**: In-transit and at-rest data protection

## 🚢 Deployment

### **Docker**
```bash
docker build -t mpi-service .
docker run -p 8000:8000 mpi-service
```

### **Kubernetes**
- Health check endpoints for probes
- ConfigMap for environment-specific settings
- Secrets for sensitive configuration
- Horizontal Pod Autoscaling support

### **Cloud Build**
```bash
# Automated CI/CD with Google Cloud Build
gcloud builds submit --config cloudbuild.yaml
```

## 📈 Performance

### **Targets**
- **Latency**: P95 < 50ms, P99 < 100ms
- **Throughput**: 100-500 req/sec sustained
- **Cache Hit Rate**: > 90%
- **Availability**: 99.9% uptime

### **Optimizations**
- **Connection Pooling**: All external services
- **Batch Processing**: Configurable concurrency
- **Async Operations**: Non-blocking I/O throughout
- **Caching**: Multi-level with intelligent invalidation

## 📚 Documentation

- **Architecture**: `/docs/architecture-refactored.md`
- **Data Model**: `/docs/data-model.md`
- **Outstanding Questions**: `/docs/outstanding-questions.md`
- **Enhanced Scoper Agent**: `/docs/enhanced-scoper-agent.md`

## 🤝 Contributing

1. Follow domain-driven design patterns
2. Use Controller/Service/Repository layers
3. Add tests for all new functionality
4. Update documentation for API changes
5. Ensure performance targets are met

## 📄 License

Proprietary - All Rights Reserved