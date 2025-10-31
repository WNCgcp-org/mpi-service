# MPI Service Data Model

## Purpose
The MPI service is a **lightweight identifier resolution service** with **centralized configuration** and **domain-driven architecture**. It only stores the minimum data necessary to:
1. Match incoming patient data to existing MPI IDs
2. Cache recent lookups for performance with multi-level caching
3. Track identifier mappings with audit trails
4. Provide operational metrics and health monitoring

## Architecture Integration
This data model integrates with the **Controller/Service/Repository** pattern:
- **Repositories**: Handle data persistence using centralized `DatabaseManager`
- **Services**: Implement business logic with caching via `CacheManager`
- **Controllers**: Expose APIs with consistent response formats

## Collections

### 1. `mpi_identifiers` (Primary Collection)
Minimal patient identifier storage for matching:

```javascript
{
  "_id": ObjectId,
  "mpi_id": "MPI-ABC123",           // Unique master patient index ID
  "ssn_hash": "hash_value",          // Hashed SSN for matching
  "match_keys": {                    // Minimal keys for matching
    "first_name_soundex": "J500",    // Phonetic encoding
    "last_name_soundex": "S530",
    "dob": "1980-01-01",
    "ssn_last4": "6789"
  },
  "confidence": 0.95,                // Match confidence score
  "source": "verato",                // Data source (verato/internal)
  "created_at": ISODate(),
  "updated_at": ISODate(),
  "last_accessed": ISODate()        // For cache management
}
```

### 2. `identifier_mappings`
Maps external identifiers to MPI IDs:

```javascript
{
  "_id": ObjectId,
  "external_id": "agape|12345",     // External system identifier
  "external_system": "claims",       // System name
  "mpi_id": "MPI-ABC123",
  "created_at": ISODate()
}
```

### 3. `cache` (TTL Collection)
Temporary cache with automatic expiration:

```javascript
{
  "_id": "cache_key_hash",
  "request_hash": "hash_of_input",
  "mpi_id": "MPI-ABC123",
  "confidence": 0.95,
  "created_at": ISODate(),
  "expires_at": ISODate()           // MongoDB TTL index
}
```

### 4. `metrics` (Optional, TTL Collection)
Operational metrics with automatic cleanup:

```javascript
{
  "_id": ObjectId,
  "endpoint": "/mpi/match",
  "response_time_ms": 15.3,
  "cache_hit": true,
  "timestamp": ISODate(),
  "expires_at": ISODate()           // 30 day retention
}
```

## Key Design Decisions

### What We DON'T Store:
- Full patient demographics (names, addresses, phone numbers)
- Clinical data
- Claims data
- Eligibility data
- PHI beyond hashed/encoded matching keys

### What We DO Store:
- Hashed/encoded values for matching (SSN hash, soundex names)
- Minimal date fields (DOB) for matching
- MPI ID assignments
- Confidence scores
- External ID mappings
- Performance metrics

### Data Retention:
- **Identifiers**: Kept indefinitely (small footprint)
- **Cache**: 1-24 hours (configurable TTL)
- **Metrics**: 30 days (automatic cleanup via TTL index)

### Privacy & Security:
- SSNs are immediately hashed, never stored in plain text
- Names are stored as soundex encodings only
- No address or contact information stored
- Audit logs contain actions but minimal PHI

## Database Management

### **Centralized Index Creation**
All indexes are automatically created during service startup via `DatabaseManager`:

```python
# In core/database.py - BaseRepository handles common indexes
class DatabaseManager:
    async def initialize(self):
        # Auto-creates indexes for all collections
        await self._create_common_indexes()

    async def _create_common_indexes(self):
        # Primary indexes for mpi_identifiers
        await self.get_collection("mpi_identifiers").create_index([("mpi_id", 1)], unique=True)
        await self.get_collection("mpi_identifiers").create_index([("ssn_hash", 1)])
        # ... additional indexes
```

### **Index Strategy**

#### `mpi_identifiers`:
```javascript
// Primary lookup (managed by DatabaseManager)
db.mpi_identifiers.createIndex({"mpi_id": 1}, {unique: true})

// Matching indexes (auto-created during startup)
db.mpi_identifiers.createIndex({"ssn_hash": 1})
db.mpi_identifiers.createIndex({"match_keys.ssn_last4": 1, "match_keys.dob": 1})
db.mpi_identifiers.createIndex({
  "match_keys.last_name_soundex": 1,
  "match_keys.first_name_soundex": 1,
  "match_keys.dob": 1
})

// Maintenance indexes
db.mpi_identifiers.createIndex({"last_accessed": 1})
```

### `identifier_mappings`:
```javascript
// Bidirectional lookups
db.identifier_mappings.createIndex({"external_id": 1, "external_system": 1}, {unique: true})
db.identifier_mappings.createIndex({"mpi_id": 1})
```

### `cache`:
```javascript
// Fast lookups and auto-expiration
db.cache.createIndex({"request_hash": 1}, {unique: true})
db.cache.createIndex({"expires_at": 1}, {expireAfterSeconds: 0})
```

## Storage Estimates

For 1 million patients:
- `mpi_identifiers`: ~100 MB (100 bytes per record)
- `identifier_mappings`: ~200 MB (assuming 2 external IDs per patient)
- `cache`: ~10 MB (rolling window)
- `metrics`: ~50 MB (rolling 30 days)

**Total: < 500 MB for 1M patients**

## Migration from Current System

Current composite keys like:
```
agape|12345|CLM001|2025-01-15 00:00:00|2025-01-10 00:00:00
```

Will map to:
```javascript
{
  "external_id": "agape|12345",
  "mpi_id": "MPI-ABC123"
}
```

The service handles translation transparently during the migration period.