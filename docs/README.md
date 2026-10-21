# People HRMS Documentation

This directory contains the authoritative system architecture, specifications, and testing harnesses for People HRMS.

---

## Documents

| Document | Purpose & Scope |
|---|---|
| **[`system-architecture-and-flows.md`](./system-architecture-and-flows.md)** | **The Canonical System Reference (10 Chapters)**.<br>Layering rules, ERP ownership boundary, multi-factor authentication state machine, database schemas, permission matrix, per-role UI flows, and decision register. |
| **[`erp-integration.md`](./erp-integration.md)** | **ERP Machine Integration Specification**.<br>HMAC-SHA256 authentication protocol, request timestamp/nonce replay defense, outbox change feeds, and bulk upsert envelopes. |
| **[`erp-test/`](./erp-test/README.md)** | **Interactive ERP Test Harness**.<br>Standalone browser-based simulator tool to generate HMAC signatures, test attendance upserts, dispatch shift schedules, and inspect outbox event feeds. |

---

## Contributing & Maintenance Rule

Per [`AGENTS.md`](file:///AGENTS.md):
> **Before changing architecture, auth, roles, or any workflow, read `docs/system-architecture-and-flows.md`.** It is the end-to-end reference. If your change adds or removes a router, permission code, page, or ERP endpoint, update the matching table in that document in the same pull request.
