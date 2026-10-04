# Performance verification: 600 employees

Measured on 2026-10-04 against an isolated PostgreSQL database migrated to `2c3d4e5f6071`. The workload inserted 600 employees, 219,000 attendance records (2026-04-01 through 2027-03-31), and two punches per record. Synthetic rows were removed after the run. Times are local measurements, not service-level guarantees.

| Path | Previous shape | Updated shape |
|---|---:|---:|
| October attendance count, `EXPLAIN (ANALYZE, BUFFERS)` | `extract(month/year)`: parallel sequential scan, 22.7 ms | bounded date range: `ix_attendance_records_date_employee` bitmap index scan, 3.3 ms |
| 200 concurrent database count queries | 2.47 s total, 2.38 s p95 | 0.38 s total, 0.35 s p95 |
| 5,000 attendance retry items | per-item employee and ERP ID lookup pattern: 2.07 s | 500-item prefetch: 50 SELECTs, 0.053 s; 5,000 duplicates, no failures |

The punch exact-match query used `ix_attendance_punches_employee_time_type`; a one-month punch range used the existing employee index. The live-session index definition was verified after migration. An in-process HTTP load of 200 concurrent organization-owner dashboard requests on the same 600-employee dataset returned 200 successful responses in 4.10 s total (4.01 s p95). This load bypassed authentication in the test app to isolate dashboard and database work; it did not exercise the external network or browser rendering.

The targeted ERP tests cover accepted, duplicate, failed, and cross-chunk retry results. The full backend suite, Ruff, frontend lint, typecheck, build, and Shifts/Reports browser regressions passed. The synthetic test database is separate from development data.
