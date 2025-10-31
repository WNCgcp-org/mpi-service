# MPI Service

High-performance Master Patient Index service with pluggable provider architecture.

## Features

- **Multi-provider support**: Verato, Internal, or Hybrid modes
- **Performance optimized**:
  - uvloop for 2-4x faster async
  - orjson for fast JSON serialization
  - Multi-level caching (Memory → Redis → MongoDB)
  - Connection pooling for all external services
- **ML-ready**: Prepared for machine learning integration (Phase 2)
- **Production-ready**: Docker, metrics, health checks, monitoring

## Performance Targets

- **Latency**: P95 < 50ms, P99 < 100ms
- **Throughput**: 100-500 req/sec sustained
- **Cache hit rate**: > 90%
- **Concurrent connections**: 1000+

## Quick Start

### Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set environment variables**:
```bash
export MPI_PROVIDER=verato
export VERATO_API_KEY=your_key_here
export REDIS_HOST=localhost
export MONGODB_URI=mongodb://localhost:27017
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
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

## API Endpoints

### Single Patient Match
```bash
POST /mpi/match
Content-Type: application/json

{
  "patient_data": {
    "ssn": "123-45-6789",
    "first_name": "John",
    "last_name": "Smith",
    "dob": "1980-01-01"
  }
}
```

### Batch Processing
```bash
POST /mpi/batch
Content-Type: application/json

{
  "patients": [
    {"ssn": "123-45-6789", "first_name": "John", ...},
    {"ssn": "987-65-4321", "first_name": "Jane", ...}
  ]
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MPI_PROVIDER` | Provider type (verato/internal/hybrid) | verato |
| `REDIS_HOST` | Redis hostname | localhost |
| `REDIS_PORT` | Redis port | 6379 |
| `REDIS_POOL_SIZE` | Redis connection pool size | 50 |
| `MONGODB_URI` | MongoDB connection string | mongodb://localhost:27017 |
| `MONGO_POOL_SIZE` | MongoDB connection pool size | 50 |
| `CONNECTION_POOL_SIZE` | HTTP connection pool size | 100 |
| `CACHE_TTL` | Cache TTL in seconds | 3600 |
| `BATCH_SIZE` | Batch processing size | 100 |

## Performance Optimizations

The service includes several performance optimizations:

1. **uvloop**: Drop-in replacement for asyncio event loop (2-4x faster)
2. **orjson**: Fast JSON serialization (2-3x faster than standard json)
3. **Multi-level caching**:
   - L1: In-memory cache (< 1ms)
   - L2: Redis cache (< 5ms)
   - L3: MongoDB (< 20ms)
4. **Connection pooling**: Reuse connections for all external services
5. **Batch processing**: Process multiple records efficiently
6. **Indexed queries**: MongoDB indexes on commonly queried fields

## Monitoring

The service exposes Prometheus metrics at `/metrics`:

- `mpi_requests_total`: Total requests by method and status
- `mpi_request_duration_seconds`: Request duration histogram
- `mpi_cache_hits_total`: Cache hit counter
- `mpi_cache_misses_total`: Cache miss counter
- `mpi_active_connections`: Active connection gauge

## Development

### Running Tests
```bash
pytest tests/ -v
```

### Profiling
```bash
# CPU profiling
py-spy record -o profile.svg -- python src/main.py

# Memory profiling
mprof run python src/main.py
mprof plot
```

### Code Formatting
```bash
black src/
mypy src/
```

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  FastAPI    │
│   + uvloop  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Memory Cache│ ◄─── L1 Cache (<1ms)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│Redis Cache  │ ◄─── L2 Cache (<5ms)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   MongoDB   │ ◄─── L3 Storage (<20ms)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Provider   │
│  (Verato/   │
│  Internal)  │
└─────────────┘
```

## License

Proprietary - All Rights Reserved