# People HRMS Documentation

This directory contains the authoritative system architecture and technical specifications for People HRMS.

---

## Documents

| Document | Purpose & Scope |
|---|---|
| **[`system-architecture-and-flows.md`](./system-architecture-and-flows.md)** | **The Canonical System Reference (10 Chapters)**.<br>Layering rules, ERP ownership boundary, multi-factor authentication state machine, database schemas, permission matrix, per-role UI flows, and decision register. |
| **[`seed-data-and-credentials.md`](./seed-data-and-credentials.md)** | **Seed Data & Developer Credentials Reference**.<br>Portals, usernames, passwords, test personas (CEO, HR, managers, employees), seed scripts, and database initialization lifecycle. |
| **[`erp-integration.md`](./erp-integration.md)** | **ERP Machine Integration Specification**.<br>HMAC-SHA256 authentication protocol, request timestamp/nonce replay defense, outbox change feeds, and bulk upsert envelopes. |

---

## Related Developer Tools

- **[ERP Test Simulator Harness](../tools/erp-simulator/README.md)**: Standalone browser-based testing console located in `tools/erp-simulator/` for exercising live ERP endpoints, generating HMAC signatures, and inspecting outbox events.

---

## Contributing & Maintenance Rule

Per [`AGENTS.md`](../AGENTS.md):
> **Before changing architecture, auth, roles, or any workflow, read `docs/system-architecture-and-flows.md`.** It is the end-to-end reference. If your change adds or removes a router, permission code, page, or ERP endpoint, update the matching table in that document in the same pull request.
