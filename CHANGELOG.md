# Changelog

All notable changes to troxy are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **`troxy_explain_failure` MCP tool** — analyzes recent HTTP failures (4xx/5xx) and returns
  semantic failure groups with plain-English hypotheses (`auth_failure`, `rate_limit`,
  `server_error`, `token_expired`, etc.). Accepts `domain` and `since` filters.
  First wedge analytics tool; applies lenses *Semantic > raw* and *MCP as the surface*.
- `query_failures` in `core/query.py` — reusable query helper for error-range flows,
  shared by the MCP handler and future CLI commands.

## [0.5.7] — prior release

*(Baseline — see git log for earlier history)*
