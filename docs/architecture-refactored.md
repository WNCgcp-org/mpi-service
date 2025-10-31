# MPI Service - Refactored Architecture

## Overview
The MPI service has been refactored to follow Domain-Driven Design (DDD) principles with a clear **Controller/Service/Repository** pattern. This provides better separation of concerns, testability, and maintainability.

## Architecture Pattern

### Three-Layer Architecture
```
┌─────────────────────────────────────┐
│         Controllers Layer           │  ← HTTP endpoints, request/response handling
├─────────────────────────────────────┤
│          Services Layer             │  ← Business logic, orchestration
├─────────────────────────────────────┤
│        Repositories Layer           │  ← Data persistence, caching
└─────────────────────────────────────┘
```

### Domain Structure
```
src/
├── domains/
│   ├── patient/
│   │   ├── controllers/    # HTTP endpoints
│   │   ├── services/       # Business logic
│   │   ├── repositories/   # Data access
│   │   └── models/         # Domain models
│   ├── matching/
│   │   ├── controllers/
│   │   ├── services/
│   │   ├── repositories/
│   │   └── models/
│   ├── admin/
│   │   └── ...
│   ├── monitoring/
│   │   └── ...
│   └── config/
│       └── ...
├── core/
│   └── dependencies.py     # Dependency injection
├── providers/              # MPI providers (Verato, Internal, Hybrid)
└── main_refactored.py     # Application entry point
```

## Domain Breakdown

### 1. **Patient Domain**
Handles patient data operations with minimal data storage.

**Controller** (`patient_controller.py`):
- `GET /api/v1/patients/{mpi_id}` - Get patient by MPI ID
- `POST /api/v1/patients/search` - Search patients
- `GET /api/v1/patients/{mpi_id}/identifiers` - Get patient identifiers
- `GET /api/v1/patients/{mpi_id}/history` - Get patient history
- `GET /api/v1/patients/{mpi_id}/links` - Get linked records
- `POST /api/v1/patients/{mpi_id}/verify` - Verify patient

**Service** (`patient_service.py`):
- Business logic for patient operations
- Caching strategy implementation
- Soundex encoding for fuzzy matching
- Confidence score calculations

**Repository** (`patient_repository.py`):
- MongoDB persistence
- Index management
- Audit logging
- Identifier mappings

**Models** (`patient.py`):
- `PatientEntity` - Internal representation
- `PatientResponse` - API response
- `PatientSearchRequest` - Search parameters
- `PatientIdentifier` - External identifiers

### 2. **Matching Domain**
Core MPI matching functionality with multi-level caching.

**Controller** (`matching_controller.py`):
- `POST /mpi/match` - Single patient match
- `POST /mpi/bulk-match` - Bulk matching with correlation IDs
- `POST /mpi/bulk-match-stream` - Streaming for large datasets
- `GET /mpi/cache/stats` - Cache statistics
- `POST /mpi/cache/clear` - Clear cache

**Service** (`matching_service.py`):
- Three-level caching (Memory → Redis → MongoDB)
- Provider abstraction
- Batch processing
- Correlation ID handling

**Repository** (`matching_repository.py`):
- Cache management
- Metrics collection
- Performance tracking

**Models** (`matching.py`):
- `MatchResult` - Single match result
- `BulkMatchRequest` - Bulk request with correlation IDs
- `BulkMatchResponse` - Bulk response (no PHI)

### 3. **Admin Domain** (To be fully implemented)
Administrative operations for patient management.

### 4. **Monitoring Domain** (To be fully implemented)
System health, metrics, and alerts.

### 5. **Config Domain** (To be fully implemented)
Dynamic configuration management.

## Key Design Decisions

### 1. **Minimal Data Storage**
The service only stores:
- Hashed SSNs for matching
- Soundex-encoded names
- MPI ID assignments
- Confidence scores
- External ID mappings

**NOT stored**:
- Full patient demographics
- Clinical data
- Claims/eligibility data
- PHI beyond matching keys

### 2. **Multi-Level Caching**
```
Request → L1 Memory → L2 Redis → L3 MongoDB → Provider API
         (<1ms)      (<5ms)     (<20ms)      (50-500ms)
```

### 3. **Provider Abstraction**
Modular provider system supporting:
- **Verato** - External matching service
- **Internal** - Probabilistic matching
- **Hybrid** - Multi-provider strategies

### 4. **Correlation IDs for Bulk**
Bulk operations use correlation IDs to:
- Avoid returning PHI
- Enable client-side result mapping
- Support audit trails

### 5. **Dependency Injection**
Clean dependency management through:
- FastAPI's `Depends()` system
- Centralized `MPIServiceContext`
- Repository pattern for data access

## Performance Optimizations

1. **uvloop** - 2-4x faster event loop
2. **orjson** - Fast JSON serialization
3. **Connection pooling** - Redis, MongoDB, HTTP
4. **Batch processing** - Configurable batch sizes
5. **Indexed queries** - Optimized MongoDB indexes
6. **Streaming API** - For large datasets

## API Usage Examples

### Single Match
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

Response:
{
  "mpi_id": "MPI-ABC12345",
  "confidence": 0.95,
  "provider": "internal",
  "processing_time_ms": 12.5
}
```

### Bulk Match with Correlation IDs
```bash
POST /mpi/bulk-match
{
  "patients": [
    {
      "correlation_id": "req-001",
      "patient_data": {
        "ssn": "123-45-6789",
        "first_name": "John"
      }
    }
  ]
}

Response:
{
  "request_id": "550e8400-...",
  "total_records": 1,
  "successful": 1,
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

## Benefits of New Architecture

1. **Separation of Concerns**
   - Controllers handle HTTP concerns only
   - Services contain business logic
   - Repositories manage data persistence

2. **Testability**
   - Each layer can be tested independently
   - Mock repositories for service tests
   - Mock services for controller tests

3. **Maintainability**
   - Clear domain boundaries
   - Single responsibility per class
   - Easy to locate functionality

4. **Scalability**
   - Stateless services
   - Horizontal scaling ready
   - Cache-first architecture

5. **Flexibility**
   - Easy to swap providers
   - Simple to add new domains
   - Clean extension points

## Migration Path

1. **Phase 1** - Run new refactored service alongside original
2. **Phase 2** - Gradually migrate endpoints to new structure
3. **Phase 3** - Complete remaining domain implementations
4. **Phase 4** - Deprecate original structure

## Next Steps

1. Complete stub domain implementations (Admin, Monitoring, Config)
2. Add comprehensive unit tests for each layer
3. Implement OpenAPI documentation
4. Add request validation middleware
5. Set up monitoring and alerting
6. Performance benchmarking