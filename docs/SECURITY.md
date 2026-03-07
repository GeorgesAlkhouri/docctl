# SECURITY

Security expectations for agent-authored changes:
1. Keep mutating operations explicit (`ingest` is mutating, others are read-only).
2. Avoid hidden network behavior; model download must be explicit.
3. Preserve provenance metadata required for auditability (`doc_id`, `source`, `title`).
4. Prefer authoritative references for security guidance and avoid unverified sources.
