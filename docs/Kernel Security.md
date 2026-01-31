This document reflects 'Security Measures' that are applied to the Kernel.

# Tracking Requests

A `RequestAnalyticsMiddleware` is used to persist into the `http_request_logs` database table.

## How the data is used?

1. IP address and user agents are used to detect brute-force attacks, credentials stuffing, automated scanning. Combined with status codes, they reveal unauthorized access attemts.
2. Duration measurements identify slow endpoints without requiring APM tooling. Content length helps correlate payload size with latency.
3. GEO data (from nginx GeoIP) is useful for identifying access patterns.

# Security Assesment

1. CORS Configuration (`src/config`)
2. HTTP Security Headers

