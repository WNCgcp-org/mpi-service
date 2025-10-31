# Outstanding High-Level Questions for MPI Service

## 🎯 Strategic Questions

### 1. Integration Point & Data Flow
- [ ] **Where exactly in the Silkroad pipeline should this be called?** We know it's "after standardization, before aggregation" but the specific integration point affects performance and data consistency.
- [ ] **What's the rollback plan if MPI assignments change?** If we reassign an MPI ID, how do downstream systems handle that?

### 2. Success Metrics & Validation
- [ ] **How will you measure the 98% grouping agreement target?** Do you have a test dataset from Verato to validate against?
- [ ] **What's the plan for ongoing accuracy monitoring?** How do you detect when matching quality degrades?

### 3. Operational Concerns
- [ ] **What's the disaster recovery plan?** If the MPI service goes down, does Silkroad processing halt?
- [ ] **How do you handle the transition period?** During migration, what happens to records that have both old composite keys AND new MPI IDs?

### 4. Scale & Performance Reality Check
- [ ] **What's the actual volume expectation?** You mentioned eligibility data first - what's the realistic daily/hourly volume?
- [ ] **Provider SLA expectations?** If Verato has outages, does processing queue or fail?

### 5. Business Logic Complexity
- [ ] **Edge cases for matching?** What about patients with no SSN, name changes, data entry errors?
- [ ] **Confidence threshold governance?** Who decides when a 0.7 confidence match is acceptable vs requiring manual review?

## 🔧 Technical Architecture Questions

### 6. Data Governance
- [ ] **Data retention policies?** How long do you keep cached matches, audit logs, metrics?
- [ ] **Cross-environment consistency?** How do you ensure dev/staging/prod have consistent MPI assignments?

### 7. Integration Complexity
- [ ] **Downstream system impact?** Which systems consume MPI IDs and how do they handle the transition?
- [ ] **Batch vs real-time processing?** Should Silkroad call MPI per-record or batch entire files?

### 8. Monitoring & Alerting
- [ ] **What operational metrics matter most?** Response time, cache hit rate, confidence scores, error rates?
- [ ] **Alert thresholds?** When should the system page someone vs just log an issue?

## 💡 Critical Missing Pieces

### 9. Test Data Strategy
- [ ] **Do you have a representative dataset to test matching accuracy?**
- [ ] **How will you validate the 98% grouping agreement before go-live?**
- [ ] **What's the process for creating test scenarios with edge cases?**

### 10. Fallback Behavior
- [ ] **What happens when MPI service is unavailable?** Queue? Skip? Fail?
- [ ] **Should there be a "degraded mode" that uses simple rules when providers are down?**
- [ ] **How long can the system be down before business impact?**

### 11. Manual Override Process
- [ ] **How do humans correct bad matches or merge duplicate records?**
- [ ] **What's the approval process for manual MPI assignments?**
- [ ] **How do manual changes propagate to downstream systems?**

### 12. Cross-System Consistency
- [ ] **How do you ensure the same patient gets the same MPI ID across different data sources?**
- [ ] **What happens when the same patient appears in claims and eligibility with different demographics?**
- [ ] **How do you handle data quality issues that affect matching?**

### 13. Performance Testing
- [ ] **Have you validated the system can handle your expected load?**
- [ ] **What's the performance baseline and targets for each endpoint?**
- [ ] **How do you test bulk processing performance with realistic data volumes?**

### 14. Compliance Documentation
- [ ] **Do you need formal documentation for HIPAA compliance, SOC2, etc.?**
- [ ] **What audit trails are required for regulatory compliance?**
- [ ] **How do you handle data breach notification requirements?**

## 🚀 Critical Go-Live Questions

### 15. Migration Strategy
- [ ] **What's your go-live strategy?** Because this affects financial data, you'll need a bulletproof migration plan.
- [ ] **How do you ensure data integrity throughout the transition?**
- [ ] **What's the rollback plan if issues are discovered post-migration?**
- [ ] **How do you validate that all existing composite keys map correctly to MPI IDs?**

### 16. Deployment & Operations
- [ ] **What's the deployment pipeline for updates?**
- [ ] **How do you handle schema changes or provider updates?**
- [ ] **What's the process for emergency hotfixes?**
- [ ] **How do you coordinate deployments with Silkroad pipeline schedules?**

### 17. Team & Process
- [ ] **Who's responsible for ongoing MPI service maintenance?**
- [ ] **What's the escalation process for matching issues?**
- [ ] **How do you handle customer inquiries about patient matching?**
- [ ] **What training is needed for support teams?**

## 📋 Next Actions

1. **Prioritize questions** based on go-live timeline
2. **Assign owners** for each question category
3. **Create timeline** for resolving critical questions
4. **Document decisions** as they're made
5. **Regular review** of outstanding questions in team meetings

---

**Status**: Outstanding as of October 31, 2024
**Review Frequency**: Weekly until go-live, monthly thereafter
**Owner**: Product/Engineering Team