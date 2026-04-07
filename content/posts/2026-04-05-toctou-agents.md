---
title: "TOCTOU Race Conditions in Multi-Agent Systems"
date: 2026-04-05
description: "How TOCTOU vulnerabilities appear in multi-agent systems when concurrent agents hold overlapping write permissions on shared mutable state."
tags: ["AI Security", "Agent Security", "OWASP", "AISVS"]
---

Agent systems that do useful work tend to have multiple agents running concurrently, often reading and writing to the same underlying state. A support agent handles incoming requests while an ops agent processes escalations against the same ticket database, or a compliance agent monitors for policy violations on the same access control list that an access management agent writes grants to. When these agents run concurrently and their operations interleave, the same timing vulnerabilities that have existed in operating systems and concurrent programming for decades show up again.

In file system and kernel security this pattern is called time-of-check-time-of-use, or TOCTOU ([CWE-367](https://cwe.mitre.org/data/definitions/367.html)). A process checks a condition, then acts on it, but between the check and the action something else changes the state, so the check was valid when it happened but no longer holds when the action runs. The same pattern appears in agent orchestration once you have concurrent agents sharing mutable state.

## What this looks like in practice

Consider a billing system where a Refund Agent processes customer refund requests and a Fraud Agent monitors accounts and freezes them when it detects suspicious activity. Both agents read and write to the same account state, and both run concurrently because the system needs to process refunds quickly and catch fraud quickly, so neither waits for the other.

A fraudulent actor submits a refund request for $4,800 on a stolen account. The Fraud Agent has already flagged the account and is processing a freeze, but the Refund Agent picks up the request at roughly the same time:

```
T=0ms     Refund Agent: reads account state, checks balance, starts processing
T=80ms    Fraud Agent: flags account, begins writing FROZEN status
T=150ms   Refund Agent: writes REFUND_ISSUED to account, triggers payout
T=200ms   Fraud Agent: writes FROZEN to account
```

The refund went out at T=150ms and the freeze landed at T=200ms, so the final account state shows FROZEN, which looks correct if you only check the end state and the audit log. But $4,800 already left the system in the window between the refund write and the freeze write. The Refund Agent checked a valid, unfrozen account when it started, the Fraud Agent did its job and froze the account, and both agents behaved correctly, but the payout was already triggered before the freeze landed.

This does not require an attacker to exploit deliberately, because the same interleaving happens when legitimate concurrent operations run in the wrong order, which makes it harder to catch because the system looks like it is working. Sequential testing misses it because the vulnerability only exists under concurrent execution, and the timing windows in agent systems tend to be wider than in conventional application code because the agent is waiting on model inference between its authorisation check and its state mutation.

## Mitigation

The mitigation is atomicity at the state mutation layer, where transactions, optimistic locking, or compare-and-swap ensure that an authorisation check and the state mutation it gates cannot be split by a concurrent write from another agent. These are familiar concurrency primitives, but they tend to get overlooked in agent architectures where the focus is on model behaviour and prompt security rather than on how the orchestration layer handles shared state. Threat modeling and understanding the logical chains which can create these scenarios I discussed more here: [Datalog for Agent Security Analysis](https://joe-b-security.github.io/posts/2026-04-05-datalog-for-agent-security-analysis/)

## Contributing to AISVS

I noticed this gap while reviewing [OWASP AISVS](https://github.com/OWASP/AISVS) C9, which covers multi-agent orchestration security in detail but had no requirements for concurrent execution safety. The existing TOCTOU coverage in C9.2 addresses a different pattern, where the race is between an approval decision and execution within a single agent workflow. The concurrent agent pattern is distinct because the race is between two independent agents operating on shared state, where each agent's logic is individually correct but the interleaving creates a security violation.

I opened an [issue](https://github.com/OWASP/AISVS/issues/640) with a case study from my [threat modeling research](https://labs.snyk.io/resources/threat-modeling-best-defense/) and it was accepted as a new requirement ([PR](https://github.com/OWASP/AISVS/pull/641)), adding atomicity controls for concurrent agent operations on shared state to the standard.
