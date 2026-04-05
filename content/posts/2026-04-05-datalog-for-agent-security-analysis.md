---
title: "Datalog for Agent Security Analysis"
date: 2026-04-05
description: "How Datalog's recursive queries and negation-as-failure make it a natural fit for reasoning about security properties in agent architectures."
tags: ["AI Security", "Agent Security", "Formal Methods"]
---

In an [earlier post](https://joe-b-security.github.io/posts/2026-02-28-agent-security-formal-methods/) I looked at whether formal methods apply to agent security and concluded that modeling the architecture as a graph and running declarative queries over it was a better fit than state-machine verification. That left the question of which formalism to actually use. After working with this in practice, what I have found is that Datalog is a surprisingly good fit.

### The problem

The security risks in agent systems come from composition. A support agent escalates to an account management agent, which delegates to an operations agent, which has access to a customer database. The question is whether untrusted input can travel through that chain and reach something sensitive without hitting a check along the way. With a handful of agents and tools you can trace these paths manually, but the number of paths grows faster than you might expect.

Consider a small system: five agents that can delegate to each other, each connected to three or four tools, with those tools reading from and writing to a few shared data stores. That is around 20 nodes and 35 edges. If each agent can delegate to two others, the delegation chains alone form a tree with a branching factor of two, giving you 15 possible delegation sequences through four steps (1 + 2 + 4 + 8). Each sequence ends at an agent with three or four tools, each of which connects to one or two data stores. Multiply those together and you are looking at well over a hundred distinct paths from the entry point to a sensitive resource, in a system with only five agents. For each of those paths, you need to determine whether anything along the way enforces a security property. Double the number of agents and the path count grows into the thousands.

If you can model the architecture as a set of facts (which agents exist, what tools they can call, what data flows between them) and write rules that describe the patterns you consider dangerous, the question becomes whether there is an engine that will exhaustively check every one of those paths against those rules and tell you which ones match.

### Why Datalog

Datalog is a declarative query language designed for recursive reasoning over structured facts. It has been around since the 1980s and has a long track record in program analysis and security tooling, where the core problem is the same: query a large set of relational facts for structural properties that indicate risk.

What makes it useful here is that it gives you exhaustive evaluation with guaranteed termination. You give it facts and rules, and it computes every derivable conclusion by evaluating the rules to a fixed point. It is guaranteed to terminate because Datalog operates over a finite set of constants, so the set of things it can derive is bounded. You do not need to worry about cycles in the graph causing infinite loops, which is a real concern with recursive SQL CTEs or hand-written graph traversals.

The pattern I have used most is transitive reachability. In the agent security context, the question you keep coming back to is: can some entity A reach some other entity B through any sequence of connections, however indirect? Can user input reach a customer database through a chain of agent delegations and tool calls that you did not anticipate when you designed the system? In Datalog, you express this as two rules:

```prolog
reachable(A, B) :- edge(A, B).
reachable(A, C) :- edge(A, B), reachable(B, C).
```

The first rule says A can reach B if there is a direct connection between them. The second says A can reach C if A connects to some intermediate node B, and B can reach C. That second rule references itself, which is what makes it recursive. The engine applies both rules repeatedly, discovering new reachable pairs at each step, until there is nothing new to derive. The result is the complete set of every node that can reach every other node through any chain of edges. For the five-agent system described above, these two rules compute that full set across all of those hundred-plus paths in a single evaluation, including paths you did not think to check manually.

The other feature that I found maps well to security analysis is negation-as-failure. A lot of the interesting security questions about agent architectures are about absence: not just "can A reach B?" but "can A reach B without passing through something that enforces a check?" Under the closed-world assumption, if a fact cannot be derived from what is known, it is treated as false. You can use this to express rules like "flag any path where this property is missing," and the engine will find every path that matches.

```prolog
reachable_unchecked(A, B) :- edge(A, B), not verified(B).
reachable_unchecked(A, C) :- edge(A, B), not verified(B), reachable_unchecked(B, C).
```

Because each rule is independent, you can build these up incrementally as you learn more about what matters in your specific architecture. New rules do not require changing existing ones, and when the architecture changes you update the facts and everything re-evaluates.

### Where this stops

Datalog tells you the path exists in the architecture, not whether the agent will actually take it. An agent with a reachable path to a sensitive data store might never follow that path in normal operation, but could be steered onto it through a prompt injection. Understanding whether the agent takes the dangerous path under adversarial pressure is a different problem that requires behavioural testing, which I wrote about in [evaluating prompt injection through tool call traces](https://joe-b-security.github.io/posts/2026-04-04-evaluating-prompt-injection-in-agent-systems/).

It also does not amount to full formal verification. You are checking the architecture against a set of known dangerous patterns, not proving the absence of all possible bad states. In my experience that is the right trade-off for systems that change as frequently as agent architectures do.
