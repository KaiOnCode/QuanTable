# Security Policy

## Supported Versions

| Version | Supported |
|---------|:---------:|
| latest  | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. Do NOT open a public issue.
2. Use the [GitHub Security Advisory](https://github.com/KaiOnCode/QuanTable/security/advisories/new) to report privately.
3. Include steps to reproduce, potential impact, and any suggested fixes.

We will acknowledge your report within 5 business days and work with you to resolve the issue.

## Scope

This policy applies to the [KaiOnCode/QuanTable](https://github.com/KaiOnCode/QuanTable) repository.

## Key Security Considerations

### API Keys and Credentials

QuanTable stores API keys in `properties.env`, which is gitignored. Never commit real API keys to the repository. The `properties.env.example` file contains only placeholder values.

### Agent Tool Execution

The ReAct agent can execute shell commands, read/write files, and make network requests through its tool system. These tools are gated and should only be used in local development environments. Do not expose the agent terminal to untrusted networks.

### Generated Reports

The system generates financial analysis reports that may contain LLM-generated content. These reports are for research purposes only and should not be treated as investment advice.

### Data Sources

Market data is fetched from third-party providers (Yahoo Finance, AkShare, Finnhub). API keys for these services are optional and stored locally. No user data is sent to third parties beyond standard LLM API calls.

## Official Channels

QuanTable is an open-source research tool. We will never ask for cryptocurrency payments, wallet connections, or "verification" of any kind. The only official channel is this GitHub repository.

## Disclosure

Please do not publicly disclose the vulnerability until we have released a fix.
We will credit reporters in the release notes (unless you prefer anonymity).
