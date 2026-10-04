# ERP CRUD Test Console

A small, dependency-free static web page for exercising every ERP integration
endpoint (`/api/v1/integrations/erp/**`) against a running HRMS API. Use it to
create, update and delete organization, employee, shift, attendance, overtime,
holiday and leave data without hand-crafting signed HTTP requests.

> **Light theme:** Cattupuchin (light mode).

> **Development tool only.** It can hold an ERP signing secret in browser
> storage and signs requests from the browser. Never host it on a deployed or
> public origin.

## Files

| File           | Purpose                                                                 |
| -------------- | ----------------------------------------------------------------------- |
| `index.html`   | Page layout: connection/auth config, lookup login, endpoint catalog.    |
| `styles.css`   | Self-contained styling (no CDN or build step). Light theme: Cattupuchin. |
| `endpoints.js` | Catalog of all 35 ERP endpoints, each with a typed field schema.        |
| `lookups.js`   | Human-login reference-data sources used to populate ID dropdowns.       |
| `form.js`      | Renders the typed fields as inputs and builds the JSON payload.         |
| `app.js`       | Signing, request execution, response rendering, history, persistence.   |

## Prerequisites

1. **The API is running** from `app/api/`:
   ```bash
   uv run fastapi dev main.py
   ```
2. **ERP auth is configured.** The page supports both modes:

   - **HMAC (default).** Provide an ERP client in the API environment:
     ```bash
     ERP_API_CLIENTS='{"primary-erp":{"secret":"replace-with-32-or-more-random-characters","scopes":["*"]}}'
     ```
     Enter the same `client_id` and `secret` in the page.
   - **Development API key.** Set a key and select the "development API key" auth mode:
     ```bash
     ENVIRONMENT=development
     ERP_API_KEY=dev-secret
     ```
     `X-API-Key` is only accepted when `ENVIRONMENT=development` (or `dev`/`test`/`local`).

3. **A business lookup account.** Reference-data dropdowns are read from the
   workforce APIs, and the **technical Super Admin is denied there** (the API
   answers `403 TECHNICAL_ADMIN_ONLY`). Sign in as a business user instead.
   A fresh development database seeds only the Super Admin, so create one
   employee first with the ERP employee endpoint (dev key or HMAC) using
   `role: "ORGANIZATION_OWNER"`, then sign in with that employee's `username`
   (or mobile number) and `initial_password` at `/auth/employee/login`.
   An ERP-provisioned account is flagged `must_change_password`, and every
   workforce read answers `403 PASSWORD_CHANGE_REQUIRED` until that is done.
   When the page detects this it reveals a **Change password & re-sign in**
   control; use it once and the account becomes usable for lookups.
   If `MFA_REQUIRED_FOR_SUPER_ADMIN=true` the technical login returns an MFA
   challenge, which this dev tool cannot complete.

## Running

Serve the folder over HTTP on localhost. `file://` will not work because the
page needs Web Crypto and CORS, both of which require a proper origin.

```bash
cd docs/erp-test
python3 -m http.server 5500
# then open http://localhost:5500
```

The API's development CORS policy already accepts any `http://localhost:<port>`
or `http://127.0.0.1:<port>` origin.

## Typical create/update walkthrough

1. Confirm the **Base URL** (`http://localhost:8000`) and ERP auth mode.
2. Sign in under **Lookup login** as the business user created below (not the
   Super Admin) and click **Load reference data**. This fills the ID dropdowns
   and the "Reference IDs" panel on the right.
3. Pick an endpoint from the **Endpoints** catalog. The request card shows the
   method, path and query parameters, then a **typed form** for the body:
   text, number, date, time, checkbox-style Yes/No and dropdowns for enums and
   reference IDs. Fields are grouped into collapsible sections, required ones
   are marked with `*`.
4. Fill the fields and click **Send request**. Only the fields you filled are
   sent, so update (PATCH) endpoints behave like true partial updates. Use
   **Payload preview** to see the exact JSON that will be sent, and **History**
   to replay a request.

Recommended dependency order for a fresh database:

```
organization → unit → department → designation
→ shift → employee → shift assignment
→ attendance records → overtime records → holidays
→ leave period → leave type → leave balances → leave changes
```

## Notes on the API contract

- Path parameters must be existing numeric IDs (`unit_id`, `employee_id`,
  `shift_id`, `type_id`, ...). The dropdowns come straight from the read APIs.
  Fields whose reference list is not loaded fall back to a plain text input.
- Select fields marked `— not set —` are omitted from the payload entirely,
  which is what lets a PATCH change one field without clearing the rest.
- Attendance bulk uses `{ "records": [ ... ] }`; overtime, holidays, leave
  balances and the leave acknowledgement use **bare JSON arrays**.
- Retries are idempotent by `erp_record_id` / `erp_event_id` / `erp_holiday_id`.
- A `403` usually means the ERP client lacks the endpoint's scope; a `409`
  usually means a reused nonce or a duplicate record; `422` is validation.
- HMAC canonical string: `METHOD`, path with query, timestamp, nonce and the
  SHA-256 body hash, joined by newlines. Nonce is single-use, timestamp must be
  within `ERP_SIGNATURE_MAX_AGE_SECONDS` (default 300s).
