# Security Policy

## Supported Versions
Only the latest release on the `main` branch receives active security updates.

## Reporting a Vulnerability
Please report security issues confidentially using GitHub Private Vulnerability Reporting:
1. Navigate to the repository Security tab on GitHub.
2. Select "Report a vulnerability" to open an advisory.

Please avoid posting vulnerability details in public issues.

## Scope & Design Assumptions
Video Editor is a single-user desktop companion tool designed to run locally on `127.0.0.1`. It does not include multi-tenant user authentication. Exposing this application to public networks requires an authenticating reverse proxy.
