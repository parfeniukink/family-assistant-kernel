# Security & Architecture Review


## 2. Request Analytics

### What Data Is Collected

The `RequestAnalyticsMiddleware` captures the following for every HTTP request:

| Field              | Source                                          | Purpose                                 |
| ------------------ | ----------------------------------------------- | --------------------------------------- |
| `ip_address`       | `X-Real-IP` / `X-Forwarded-For` / `client.host` | Identify clients, detect abuse patterns |
| `method`           | `request.method`                                | Traffic analysis by HTTP verb           |
| `path`             | `request.url.path`                              | Endpoint popularity, error hotspots     |
| `status_code`      | `response.status_code`                          | Error rate monitoring                   |
| `user_agent`       | `User-Agent` header                             | Client identification, bot detection    |
| `referer`          | `Referer` header                                | Traffic source analysis                 |
| `country` / `city` | `X-Geoip-Country` / `X-Geoip-City` headers      | Geographic distribution of traffic      |
| `user_id`          | JWT `Authorization` header (best-effort)        | Per-user usage patterns                 |
| `duration_ms`      | `time.monotonic()` delta                        | Performance monitoring                  |
| `content_length`   | `Content-Length` header                         | Request size analysis                   |
| `created_at`       | Database `now()`                                | Time-series analysis                    |

### Why This Data

- **Security:** IP addresses and user agents enable detection of brute-force
  attacks, credential stuffing, and automated scanning. Combined with status
  codes, they reveal unauthorized access attempts.
- **Performance:** Duration measurements identify slow endpoints without
  requiring APM tooling. Content length helps correlate payload size with
  latency.
- **Operations:** Geographic data (from nginx GeoIP) provides visibility into
  where traffic originates, useful for identifying unexpected access patterns.
- **Business:** Per-user and per-endpoint usage data informs feature
  prioritization and capacity planning.

### Design Decisions

- **Fire-and-forget writes:** The DB insert runs as an `asyncio.create_task()`,
  so logging never adds latency to the actual request. Errors are caught and
  logged via loguru.
- **Best-effort user extraction:** JWT decoding in the middleware does not
  enforce authentication. If the token is invalid or missing, `user_id` is
  simply `None`.
- **Truncation:** `user_agent` and `path` are truncated to 500 characters to
  prevent oversized payloads from bloating the logs table.

---

## 3. Security Assessment

### Findings & Mitigations Applied

#### 3a. CORS Configuration (Medium Risk -> Mitigated)

**Finding:** CORS was configured with `allow_origins: ["*"]`,
`allow_methods: ["*"]`, `allow_headers: ["*"]`. This allowed any origin to
make credentialed cross-origin requests.

**Mitigation:** Defaults tightened to:

- Origins: `["https://budget.parfeniukink.space"]` (matches ingress)
- Methods: explicit list of used HTTP methods
- Headers: only `Authorization` and `Content-Type`

These remain configurable via environment variables for development.

#### 3b. Missing Security Headers (Medium Risk -> Mitigated)

**Finding:** No security headers were set on API responses.

**Mitigation:** `SecurityHeadersMiddleware` now sets:

- `X-Content-Type-Options: nosniff` - prevents MIME type sniffing
- `X-Frame-Options: DENY` - prevents clickjacking
- `X-XSS-Protection: 1; mode=block` - legacy XSS filter
- `Strict-Transport-Security` - enforces HTTPS (SSL at ingress)
- `Content-Security-Policy: default-src 'none'` - restrictive CSP for JSON API
- `Referrer-Policy: strict-origin-when-cross-origin` - limits referrer leakage
- `Permissions-Policy` - disables unnecessary browser features
- `Cache-Control: no-store` - prevents caching of API responses

#### 3c. Rate Limit Response (Low Risk -> Mitigated)

**Finding:** The rate limit handler returned `JSONResponse(None, status_code=429)`
with no body or `Retry-After` header.

**Mitigation:** Now returns a proper error body using the existing `ErrorResponse`
schema and includes a `Retry-After` header with appropriate delay based on the
limit window.

#### 3d. Request Logging Gap (Informational -> Mitigated)

**Finding:** No request-level logging existed for security auditing.

**Mitigation:** `RequestAnalyticsMiddleware` now logs all requests with client
IP, user agent, path, status code, and optional user identity. This enables
post-incident forensics and abuse detection.

### Existing Security Strengths

- **JWT authentication** with short-lived access tokens (15 min) and hashed
  refresh tokens (SHA256) stored in the database.
- **Argon2 password hashing** per OWASP recommendations.
- **Rate limiting** on sensitive endpoints (login: 5/min, 20/hour; refresh:
  10/min).
- **Sentry integration** with PII collection for production error tracking.
- **Database error sanitization** in the CQS layer prevents internal details
  from leaking to clients.

---

## 4. K3S / Ingress-Specific Considerations

### IP Extraction

The nginx-ingress controller in K3S sets `X-Real-IP` and `X-Forwarded-For`
headers automatically. The analytics middleware respects these with a priority
chain: `X-Real-IP` > `X-Forwarded-For` (first entry) > `request.client.host`.

This is correct for a single-proxy setup where nginx-ingress is the only
reverse proxy in front of the application. If additional proxies are added
(e.g., Cloudflare), the IP extraction logic should be revisited.

### GeoIP

The middleware reads `X-Geoip-Country` and `X-Geoip-City` headers, which are
populated by the nginx-ingress GeoIP module when enabled. If GeoIP is not
configured on the ingress, these fields will be `NULL` in the database, which
is handled gracefully.

### SSL Termination

SSL is terminated at the ingress level. The `Strict-Transport-Security` header
is set by the application middleware as defense-in-depth, complementing any
HSTS configuration on the ingress itself.

### CORS and Ingress

The ingress already restricts CORS to `budget.parfeniukink.space`. Setting the
same restriction at the application level provides defense-in-depth: if the
ingress configuration is changed or bypassed, the API still enforces origin
restrictions.

---

## 5. Recommendations for Future Improvements

### High Priority

1. **Request log retention policy:** Implement a scheduled task (K8s CronJob)
   to purge `request_logs` older than 90 days to prevent unbounded table growth.

2. **IP-based blocking:** Use the `request_logs` table to build an automated
   IP blocking mechanism for repeated 401/403 responses from the same IP.

3. **Database connection pooling tuning:** The fire-and-forget analytics writes
   create new sessions. Under high load, consider a dedicated connection pool or
   batch inserts.

### Medium Priority

4. **Structured logging:** Migrate loguru configuration to JSON format for
   better integration with log aggregation tools (Loki, ELK).

5. **Request ID propagation:** Add a `X-Request-ID` header to correlate logs
   across middleware, application, and external services.

6. **CSP reporting:** Add `report-uri` directive to Content-Security-Policy
   to collect violation reports.

### Low Priority

7. **Analytics dashboard:** Build read-only endpoints to query `request_logs`
   for operational dashboards (top paths, error rates, geographic distribution).

8. **Anomaly detection:** Use the analytics data to detect unusual patterns
   (traffic spikes, new user agents, geographic anomalies).

9. **API versioning:** Consider URL-based API versioning (`/v1/...`) for
   future backward-compatibility management.
