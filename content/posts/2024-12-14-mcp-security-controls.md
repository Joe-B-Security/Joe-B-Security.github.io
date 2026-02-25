---
title: "Contributing MCP Security Controls to OWASP"
date: 2025-04-28
description: "How I helped add 17 new security controls to OWASP LLMSVS for Model Context Protocol"
tags: ["MCP", "AI Security", "OWASP", "Open Source"]
---

## Expanding the Threat Surface

MCP's popularity means a massive expansion of the AI threat surface. We've gone from isolated chatbots to AI agents with broad system access including token replay attacks, tool poisoning and prompt injection cascades

The open source community needed guidance, and OWASP's LLM Security Verification Standard was the obvious place to put it.

## My Contribution to OWASP LLMSVS

I contributed 17 new testable security requirements specifically for MCP implementations. These controls cover the critical security gaps:

- **Authentication & Authorization**: Mutual-TLS, signed tokens, proper OAuth scoping
- **Server Management**: Allow-listing, manifest integrity, connection validation
- **Runtime Protection**: Rate limiting, sandboxing, anomaly detection
- **Transparency**: Audit logging, user visibility into tool invocations

The goal was simple: give developers clear controls and guidance to implement MCP securely.

## Why This Matters for Open Source

Security standards only work when they're widely adopted. By contributing to OWASP LLMSVS, these MCP controls become part of the broader security community's toolkit. Developers building AI applications now have concrete, testable requirements instead of vague security advice.

### Resources

- Read the full technical analysis at [Snyk Labs](https://labs.snyk.io/resources/snyk-contributes-new-mcp-security-controls-owasp-llmsvs/)
- Check out the [OWASP LLMSVS controls](https://github.com/OWASP/www-project-llm-verification-standard) for the complete security requirements
