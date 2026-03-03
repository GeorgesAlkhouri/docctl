# RELIABILITY

Reliability expectations for agent-authored changes:
1. Stable process exit codes for known failure classes.
2. Deterministic JSON serialization for `--json` mode.
3. Reproducible local validation via pytest and smoke commands.
4. Any reliability regression must include a failing test before the fix.
