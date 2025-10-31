# MPI Service Documentation

## 📚 Documentation Overview

This directory contains comprehensive documentation for the **MPI Service** - an enterprise-grade Master Patient Index service built with domain-driven design principles.

## 📋 Documentation Index

### **Core Documentation**
- **[Main README](../README.md)** - Complete service overview, quick start, and API reference
- **[Architecture](./architecture-refactored.md)** - Domain-driven design patterns and system architecture
- **[Data Model](./data-model.md)** - Minimal persistence strategy and database design

### **Implementation Guides**
- **[Code Cleanup Summary](./code-cleanup-summary.md)** - Recent refactoring and cleanup activities
- **[Outstanding Questions](./outstanding-questions.md)** - Open questions for project completion

### **Development Tools**
- **[Enhanced Scoper Agent](./enhanced-scoper-agent.md)** - AI agent for project scoping based on MPI learnings

## 🏗️ Architecture Summary

The MPI Service follows **Domain-Driven Design** with:

### **Core Infrastructure** (`src/core/`)
- **Configuration**: Centralized, environment-specific, type-safe
- **Database**: Connection management, abstractions, auto-indexing
- **Cache**: Multi-level caching (Memory → Redis → MongoDB)
- **Dependencies**: Clean dependency injection for FastAPI

### **Domain Organization** (`src/domains/`)
- **Patient**: Patient data operations with minimal storage
- **Matching**: Core MPI matching with correlation IDs
- **Admin**: Administrative operations and data quality
- **Monitoring**: System health, metrics, and alerting
- **Config**: Dynamic configuration management

### **Provider System** (`src/providers/`)
- **Verato**: External matching service integration
- **Internal**: Probabilistic matching with fuzzy logic
- **Hybrid**: Multi-strategy provider (parallel, consensus, fallback)

## 🎯 Key Features

### **Enterprise-Grade**
- **Performance**: uvloop, orjson, connection pooling, multi-level caching
- **Security**: PHI protection, hash-based storage, correlation IDs
- **Monitoring**: Health checks, Prometheus metrics, alerting
- **Deployment**: Docker, Kubernetes, Cloud Build support

### **Domain-Driven Design**
- **Controller/Service/Repository** pattern throughout
- **Clear domain boundaries** with consistent interfaces
- **Centralized configuration** with validation
- **Dependency injection** for clean testing

### **Production-Ready**
- **Minimal data storage** - only matching keys, not full patient records
- **Audit trails** with correlation tracking
- **Graceful degradation** when dependencies fail
- **Environment-specific** configuration validation

## 🚀 Quick Navigation

### **For Developers**
1. Start with **[Main README](../README.md)** for setup and API usage
2. Review **[Architecture](./architecture-refactored.md)** for design patterns
3. Check **[Data Model](./data-model.md)** for persistence strategy

### **For Operations**
1. **[Main README](../README.md)** has deployment instructions
2. **[Architecture](./architecture-refactored.md)** covers monitoring and health checks
3. **[Outstanding Questions](./outstanding-questions.md)** lists operational decisions needed

### **For Project Planning**
1. **[Outstanding Questions](./outstanding-questions.md)** for go-live planning
2. **[Enhanced Scoper Agent](./enhanced-scoper-agent.md)** for similar projects
3. **[Code Cleanup Summary](./code-cleanup-summary.md)** for maintenance insights

## 📈 Service Capabilities

### **Matching APIs**
- Single patient match with confidence scoring
- Bulk operations with correlation IDs (no PHI transmission)
- Streaming API for large datasets
- Multi-provider strategies (Verato/Internal/Hybrid)

### **Patient Management**
- Search with fuzzy matching and configurable thresholds
- Identifier management (MRN, SSN, Insurance IDs)
- History and audit trails
- Linked record management (merges, duplicates)

### **Administrative Operations**
- Patient record merging/unmerging
- Duplicate candidate management
- Data quality reporting and monitoring
- Manual override processes

### **System Monitoring**
- Health checks (liveness, readiness, deep health)
- Performance metrics (latency, throughput, cache hit rates)
- Provider monitoring (success rates, error tracking)
- Alert management and resolution

## 🔧 Configuration Management

### **Environment Variables**
All configuration is centralized in `src/core/config.py`:
- **App Settings**: Name, version, debug mode
- **Provider Config**: Verato/Internal/Hybrid settings
- **Database**: MongoDB connection and pooling
- **Cache**: Redis configuration and TTL settings
- **Performance**: Connection pools, batch sizes, timeouts

### **Environment-Specific Validation**
- **Development**: Relaxed validation, debug features enabled
- **Production**: Strict validation, security features enforced
- **Type Safety**: Dataclass-based configuration with validation

## 📊 Performance & Scalability

### **Performance Targets**
- **Latency**: P95 < 50ms, P99 < 100ms
- **Throughput**: 100-500 req/sec sustained
- **Cache Hit Rate**: > 90%
- **Availability**: 99.9% uptime

### **Optimization Techniques**
- **Multi-level Caching**: Memory → Redis → MongoDB → Provider API
- **Connection Pooling**: Database, Redis, HTTP connections
- **Async Operations**: uvloop, non-blocking I/O throughout
- **Batch Processing**: Configurable concurrency and batch sizes

## 🔐 Security & Compliance

### **PHI Protection**
- **Minimal Storage**: Only hashed identifiers and matching keys
- **Correlation IDs**: Bulk operations without PHI transmission
- **Hash-based Storage**: SSNs and sensitive data never stored plaintext
- **Audit Trails**: Complete operation logging with correlation tracking

### **Access Control**
- **API Key Management**: Secure authentication
- **Rate Limiting**: Protect against abuse
- **Environment Isolation**: Separate dev/staging/production
- **Encryption**: In-transit and at-rest data protection

## 🎖️ Production Readiness

### **Deployment Support**
- **Docker**: Multi-stage optimized containers
- **Kubernetes**: Health probes, ConfigMaps, Secrets
- **Cloud Build**: Automated CI/CD pipeline
- **Docker Compose**: Local development environment

### **Operational Features**
- **Health Checks**: Multiple levels of system validation
- **Metrics**: Prometheus integration with comprehensive telemetry
- **Logging**: Structured logging with correlation IDs
- **Configuration**: Dynamic updates without restart

---

**Last Updated**: October 31, 2024
**Version**: 2.0.0
**Architecture**: Domain-Driven Design with Controller/Service/Repository pattern