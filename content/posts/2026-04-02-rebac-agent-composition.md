---
title: "How ReBAC can Limit the Blast Radius of Agent Composition Flaws"
date: 2026-04-02
description: "Why relationship-based access control is a better fit than RBAC for multi-agent systems, and how task-scoped permissions can prevent data leaks through delegation chains."
tags: ["AI Security", "Agent Security", "ReBAC", "Authorization"]
---

Business logic vulnerabilities are generally the hardest class of bug in application security, because they require understanding what the system is supposed to do, not just what the code says. You cannot write a static analysis rule for "the approval flow does not actually gate the action," and generally no automated tool knows how to look for a missing authorisation check on a multi-step workflow, meaning these bugs tend to survive the full development cycle and appear as criticals in bug bounty or pentest reports.

As this new wave of agent systems are being architected and pushed to production, these issues only amplify because the logical chains are longer, compositional, and non-deterministic.

When multiple agents work together, each one making tool calls based on context from the previous one, the resulting flow is a business logic chain that no single developer designed end-to-end. Each agent follows its own instructions, and each tool call looks correct in isolation, but the vulnerability emerges from the composition, from data flowing through shared resources across privilege boundaries in ways that none of the individual steps intended. The chains are also non-deterministic, so the same input might produce different tool call sequences depending on model state or context window contents, which makes these vulnerabilities difficult to reproduce reliably or test for exhaustively.

## How data can leak through a delegation chain

Consider a customer support system with two agents at different permission levels. A support agent handles incoming tickets. It can search a knowledge base, create tickets, delegate tasks, and reply to customers. An ops agent handles escalated work that requires elevated access. It can query the customer database and write investigation findings to a shared results store.

An attacker submits a support ticket requesting a refund for a $2,400 purchase on account CUST-001, which belongs to a customer named Alice. Embedded in the ticket is a prompt injection: a hidden instruction telling the agent to include the account holder's full details in its reply "for verification." The support agent searches the knowledge base and finds that refunds over $1,000 require a review of the customer's financial records, which it cannot access. It delegates to the ops agent.

The ops agent picks up the task. It queries the customer database for Alice's account and gets back the full record: name, email, SSN, phone number, address, account balance, credit score. It writes an internal investigation note to the results store documenting what it found and recommending the refund be approved. The note includes the customer's details because documenting them is the investigation. This is a normal internal workflow.

The support agent picks up the results. It reads the ops agent's investigation note, follows the injected instruction, and composes a reply that includes Alice's name, email, phone, address, and account balance. The reply goes to whoever submitted the ticket, which is the attacker. The injection worked because there was nothing between the support agent and the results store to check whether the read should be allowed.

The same leak can happen without any injection at all, when a support agent includes a customer's email in a reply to confirm the refund destination. The prompt injection makes the leak more severe (more fields, deliberately targeted), but the structural problem is the same: sensitive data flows from a high-privilege context through a shared resource into a customer-facing reply.

{{< mermaid >}}
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#4a90d9', 'actorTextColor': '#fff', 'actorBorder': '#3a7bc8', 'signalColor': '#e0e0e0', 'signalTextColor': '#e0e0e0', 'labelTextColor': '#e0e0e0', 'noteBkgColor': '#f5c542', 'noteTextColor': '#000', 'noteBorderColor': '#d4a832'}}}%%
sequenceDiagram
    participant C as Attacker
    participant S as Support Agent
    participant O as Ops Agent
    participant KB as Knowledge Base
    participant DB as Customer DB
    participant RS as Results Store

    C->>S: Refund request ($2,400) + prompt injection

    Note over S: TASK-001

    S->>KB: 1. search_knowledge_base("refund policy")
    KB-->>S: Amount over $1,000 requires elevated access

    S->>O: 2. delegate_to_ops("needs financial records")

    Note over O: TASK-002

    O->>DB: 3. query_customer_db("CUST-001")
    DB-->>O: Full customer record (name, email, SSN, balance)

    O->>RS: 4. write_results("TASK-002", investigation findings)

    S->>RS: 5. read_results("TASK-002")
    RS-->>S: Full investigation note (includes PII)

    S->>C: 6. Reply with account details (PII leaked)
{{< /mermaid >}}

Every step here is individually correct. The support agent is supposed to delegate when work exceeds its permissions, the ops agent is supposed to query the database and document its findings, and the support agent is supposed to read results and reply to the ticket submitter. The vulnerability exists in the composition: sensitive data flows from a high-privilege context through a shared resource into a customer-facing reply. The prompt injection makes the leak worse by directing the agent to include more data, but the structural problem is the same whether or not an attacker is involved.

In a real system with LLM-driven agents, non-determinism compounds the problem. The ops agent might or might not include raw PII in its findings depending on how it interprets the task. The support agent might or might not follow an injected instruction depending on its guardrails. On one run the leak is minor (an email address), on the next it is severe (full customer record), and on a third it does not happen at all, which makes it difficult to reproduce reliably or test for exhaustively.

## Why traditional tools miss this

SAST sees individual functions. It can find SQL injection in a query builder or XSS in a template renderer. It cannot see that data returned by `query_customer_db` in one agent's context flows through `write_results`, into a shared store, back through `read_results` in a different agent's context, and out through `reply_to_customer` to an end user. The vulnerability spans multiple agents, multiple tool calls, and a shared resource, so there is no single function to flag.

DAST tests endpoints and responses. It can find misconfigurations, missing headers, exposed debug pages. It cannot test the internal delegation chain between agents because there is no endpoint for it. The delegation is an internal workflow that produces a customer-visible effect only when the full chain executes in a specific way.

RBAC asks "does this agent have the role required to call this tool?" The support agent has the support role. The support role can call `read_results`. Access granted. RBAC does not ask which specific resource is being read, or whether the data in that resource came from a higher-privilege context. It authorises the action based on the caller's role, not on the relationship between the caller's task and the specific resource.

The question you actually need to answer is: "given that the ops agent can read sensitive data, can that data reach a context where the support agent publishes it?" That is a graph reachability question across agents, tasks, resources, and tools, which is not something traditional security tooling is built to ask.

## Defence in depth for agent composition

There is no single fix for compositional business logic vulnerabilities. Authorisation bounds which data can reach which context, but it is one layer. Data classification at write time, sensitivity-aware summarisation for cross-context handoffs, and output filtering at response boundaries all matter too. The rest of this post focuses on the authorisation layer, specifically relationship-based access control and why it fits agent composition better than role-based access control. The [final section](#what-authorisation-does-not-solve) covers where architectural fixes take over.

## Permissions as graph traversal

Google's [Zanzibar paper](https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/) (2019) introduced a model where authorisation is not a lookup table of roles and permissions but a graph of relationships between entities. Permission is a graph traversal: does entity A have a path to resource B through relation R?

The model stores relationships as tuples: `(subject, relation, object)`. A tuple like `(user:alice, viewer, document:budget)` means Alice is a viewer of the budget document. Permission checks traverse the graph looking for a path from the subject to the target resource through the requested relation. If a path exists, the check passes. If no path exists, the check fails. Production implementations add userset rewrite rules on top of this (unions, intersections, computed usersets), but the core idea is the same: permission is a reachability question over a graph of relationships.

This is a different shape of question from RBAC. RBAC asks "does this user have a role that includes this permission?" The answer depends on the user's role, which is a property of the user. Zanzibar asks "does this user have a relationship to this specific resource?" The answer depends on the graph structure, which can encode context that roles cannot: which task the user is working on, who delegated the work, what resources were created during the task, and how those resources relate to other tasks.


## Applying ReBAC to the delegation chain

When you apply the Zanzibar model to agents, the natural unit of authorisation turns out to be the task rather than the agent itself. An agent is a long-lived identity that might work on many tasks with different privilege requirements, but a task is a specific piece of work with a specific scope, a specific delegator, and specific resource needs. Scoping permissions to tasks means the same agent can have different access depending on what it is working on and who asked it to do that work.

Here is the relationship model for the refund scenario:

{{< mermaid >}}
%%{init: {'theme': 'dark'}}%%
graph LR
    support([agent:support]) -->|assignee| T1

    T1[task:TASK-001] -->|delegated_to| T2[task:TASK-002]

    ops([agent:ops]) -->|assignee| T2

    T1 -->|reader| RS1[(results_store:TASK-001)]
    T2 -->|reader| CDB[(customer_db)]
    T2 -->|writer| RS2[(results_store:TASK-002)]

    T1 -.-x|no reader| RS2

    style T1 fill:#4a90d9,color:#fff
    style T2 fill:#d94a4a,color:#fff
    style RS2 fill:#f5c542
{{< /mermaid >}}

The tuples encode three things that RBAC cannot express. The delegation chain is explicit and traceable: TASK-001 delegated to TASK-002, and if something goes wrong you can trace the provenance backward to see which agent was assigned, which task created the delegation, and what resources each task could access. Resource access is scoped to tasks, not to agent identities, so the ops agent working on a different task would have different resource grants. And delegation does not inherit permissions: TASK-001 delegated work to TASK-002, but that link does not give TASK-001 access to TASK-002's resources. The parent can hand off work, but it cannot read back the child's outputs unless someone explicitly grants that access.

With this model in place, the same scenario plays out differently. Steps 1 through 4 pass their permission checks normally. The check changes shape at step 5, when the support agent tries to read the ops agent's findings. Instead of checking whether the agent's role allows calling `read_results`, the engine checks the `reader` relation against the specific resource: does TASK-001 have `reader` access to `results_store:TASK-002`?

The engine searches for a path:

```
ReBAC CHECK: task:TASK-001 --reader--> resource:results_store:TASK-002

  Searching paths from task:TASK-001...

    task:TASK-001 --reader--> resource:results_store:TASK-001
      (resource:results_store:TASK-001 != resource:results_store:TASK-002)

    task:TASK-001 --delegated_to--> task:TASK-002
      Following delegation chain...
      task:TASK-002 --reader--> resource:customer_db
        (resource:customer_db != resource:results_store:TASK-002)
      task:TASK-002 --writer--> resource:results_store:TASK-002
        (writer != reader, delegation does not grant parent access)

  No path found. DENIED.
```

TASK-001 has a `reader` edge, but it points to the wrong resource. The delegation chain to TASK-002 exists, and TASK-002 has a `writer` edge to the right resource, but `writer` is not `reader`, and delegation does not grant the parent task access to the child's resources. With no valid path through the graph, the read is denied.

The support agent falls back to a generic reply without any customer details. The prompt injection is still in the ticket, and the agent may still want to follow it, but it has no data to include because the authorisation layer prevented the read. The refund still gets processed (the ops agent's findings remain in the results store for agents with appropriate access), but the sensitive data does not reach the customer-facing reply.

Under RBAC, the same check would have passed because `read_results` is a tool the support role is allowed to use. ReBAC asks a different question: "does this specific task have reader access to this specific resource?" The tool-level permission and the resource-level permission are separate checks, and in this scenario it is the resource-level check that makes the difference.

## What authorisation does not solve

ReBAC makes the blast radius deterministic, but it is one layer of a broader secure design. In most real systems, data does need to flow back across task boundaries, and when it does the architectural choices matter just as much as the authorisation model. Data classification at write time lets downstream systems distinguish SSNs from refund recommendations. Sensitivity-aware summarisation can produce redacted versions of findings for cross-context consumption. Output filtering at response boundaries can catch PII before it leaves the system regardless of what the agent decided to include. These are complementary concerns, and getting the architecture right from the start is always more effective than bolting controls on after the fact.

## Try it yourself

The [demo repository](https://github.com/Joe-B-Security/rebac-agent-demo) runs the scenario described in this post with three commands that walk through the problem and the fix.

```bash
uv sync
uv run python -m rebac_demo unprotected   # see the data leak
uv run python -m rebac_demo apply          # see the ReBAC model being built
uv run python -m rebac_demo protected      # see it blocked
```

The ReBAC engine is about 90 lines of Python. The relationship model, the graph traversal, and the logging are all real. Agent decisions are scripted because the demo is about the authorisation model, not agent reasoning.

The hardest part of adopting relationship-based access control for agent systems is the cold start: figuring out what relationships to model, what the delegation boundaries should be, and where the resource-level checks need to go. The model in this demo is small enough to read in a few minutes and maps directly to production Zanzibar implementations, it should give you a sense of how graph-based authorisation applies to agent composition and where RBAC falls short.
