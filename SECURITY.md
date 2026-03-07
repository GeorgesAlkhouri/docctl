# Security Policy

`docctl` is currently maintained by one maintainer. This policy defines how to report vulnerabilities and what response to expect.

## Supported Versions

| Version | Supported |
|---|---|
| `main` | Yes |
| Older commits/tags | No (best effort only) |

## Reporting a Vulnerability

Please use GitHub Private Vulnerability Reporting for this repository.

- Do not open public issues for suspected vulnerabilities.
- Reports sent through other channels may be delayed or not tracked.

## Preferred Report Content

Include as much of the following as possible:

- Affected commit, tag, or environment
- Reproduction steps
- Security impact and realistic attack path
- Proof of concept (minimal and safe)
- Any suggested mitigation

## Response Targets

- Initial acknowledgment: within 7 calendar days
- Triage update: within 14 calendar days after acknowledgment
- Ongoing updates: at least every 14 calendar days for open reports

Response timelines are targets, not guarantees.

## Disclosure Process

We follow coordinated disclosure:

1. Validate and triage the report.
2. Develop and release a fix.
3. Publish a security advisory/changelog note with affected and fixed versions.
4. Credit the reporter if they consent.

Please avoid public disclosure until a fix or coordinated disclosure date is agreed.

## Scope

Examples of in-scope issues:

- Privilege escalation or unintended file-system access
- Prompt/input handling that can trigger unsafe tool behavior
- Leakage of secrets or sensitive local data
- Dependency or supply-chain issues with practical impact

Examples generally out of scope:

- Non-security bugs without confidentiality/integrity/availability impact
- Theoretical findings without a plausible exploit path
- Requests to support unsupported versions

## Safe Harbor

We support good-faith security research conducted legally and responsibly. Do not access, modify, or destroy data you do not own, and avoid privacy violations or service disruption.
