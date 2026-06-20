# Phase 8 — Enterprise & Compliance

**Status:** 🔴 Not started · **Depends on:** Phases 3, 4, 6, 7

## Objective
The capabilities required to operate as licensed financial infrastructure: AML/CTF,
transaction monitoring, regulatory reporting, treasury/settlement operations, and
data-residency/governance controls.

## Work items
- **P8-01** AML/CTF: sanctions & PEP screening at onboarding and on payout; case
  management.
- **P8-02** Transaction monitoring: rule-based + threshold alerts feeding the Phase 3
  review queue; SAR/STR workflow.
- **P8-03** Regulatory reporting templates + scheduled submissions.
- **P8-04** Treasury & settlement: nostro/float management, settlement files,
  reconciliation against rail statements.
- **P8-05** Data governance: residency, retention, WORM audit storage, encryption at
  rest/in transit, key management.
- **P8-06** Access controls: SoD (segregation of duties), maker-checker on sensitive
  ops, full admin audit trail.
- **P8-07** DR/BCP: backups, RPO/RTO targets, multi-AZ topology (retires the
  single-DB/single-Redis SPOF).

## Acceptance criteria
- Screening blocks a sanctioned party end-to-end.
- Auditor can trace any cent from rail to GL to statement.
- Documented RPO/RTO met in a restore drill.

## Exit criteria
- [ ] Compliance, monitoring, treasury, and resilience controls operational and audited.
