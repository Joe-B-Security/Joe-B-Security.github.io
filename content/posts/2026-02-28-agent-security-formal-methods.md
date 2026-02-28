---
title: "Can Formal Methods Apply to Agent Security?"
date: 2026-02-28
description: "Exploring how Formal Methods apply to understanding risk in agentic systems and complex logical chains"
tags: ["AI Security", "Agent Security"]
---

The orchestration layer in agentic systems is where most of the interesting security problems live. Tool registries, routing logic, permission checks, and the technical plumbing that decides what gets called with what arguments in what scenario. That is where you get confused deputy bugs, privilege escalation, and data exfiltration. It also happens to look a lot like a problem formal methods were built for, which is what made me want to think through whether they actually apply.

### Safety vs. Liveness

The useful split for security work is between safety and liveness. Liveness is *"does the system eventually do the right thing."* Safety is *"does the system ever do a bad thing."* For security, safety properties are the tractable ones, and they map directly to what you care about in an orchestrator:

- Never invoke a write-capable tool with untrusted input as an argument
- Never escalate privileges without cryptographic attestation
- Every tool call gets logged before it executes

You state those formally and the tooling tries to falsify them by finding an explicit trace of state transitions that ends in the bad state.

[TLA+](https://www.learntla.com/) does this through its model checker TLC, which performs an exhaustive search through the reachable state space including all orderings and interleavings. [SMT](https://en.wikipedia.org/wiki/Satisfiability_modulo_theories) solvers like [Z3](https://github.com/z3prover/z3) operate at a different level entirely. Rather than enumerating states, they check whether a logical formula is satisfiable. In verification, you negate your safety property and ask the solver if the negation can be satisfied. If it comes back unsatisfiable, the property holds. They are not competing alternatives for the same job. Z3 is also used as a backend inside the TLA+ proof system for discharging proof obligations deductively, so they can show up in the same pipeline. If neither approach finds a violation, you get something stronger than *"tests passed."* You get a proof that under the model's assumptions, the bad state is unreachable.​

### The Non-Determinism Problem

The obvious objection is non-determinism. LLMs are non-deterministic, and verifying neural agents in non-deterministic environments is undecidable in the general case. End-to-end model checking of the whole agent is not a realistic goal.

In a TLA+ spec, the LLM can be modeled as a nondeterministic process that returns any possible string at every step, essentially representing the worst possible output every time. That is conceptual shorthand rather than a single TLA+ construct, but the modeling approach is real. You are not verifying that the model behaves well. You are verifying that the orchestration logic holds regardless of what the model outputs. When your primary concern is tool misuse or confused-deputy attacks through the orchestrator, that is the guarantee that matters.

#### Where It Gets Harder

TLA+ proves properties of a specification, not your code. If you abstract away a codepath, a data flow, or a corner case in tool registration, the proof does not cover it.

There is also a problem with the adversarial black-box model being almost too conservative. Modeling the LLM as fully adversarial means the traces you get may not correspond to realistic attack paths, because no real model output might actually follow them. The underlying concern is real and you still get value from those traces, but telling apart a genuine architectural flaw from an artifact of the model feels hard in practice.

#### The Bigger Structural Issue

Agent architectures also rely on probabilistic trust boundaries in a way that formal methods are not really designed for. In traditional AppSec, you pushed the likelihood of bad states toward zero with hard gates. In multi-agent workflows, capabilities compose dynamically. If a data analyst agent pulls PII and passes it downstream to an agent with write access to a public channel, the vulnerability is not a bug in any individual component. It is an emergent property of the composition.​

The dangerous paths in agent systems are often not logic bugs in the orchestration layer. They are mismatched assumptions between agents about what kind of data they are handling, and those are very hard to capture in a static spec.

Rather than trying to prove a full state machine correct, treating the architecture itself as a graph seems like a better fit. Agents, tools, permissions, data flows, and trust boundaries become facts and relations. You write declarative rules to search for risky patterns in that graph.

This feels like it's more in the spirit of deductive database programming, designed to run recursive queries over large relational graphs. Instead of asking *"is it mathematically impossible for untrusted input to reach a write-capable tool"* you ask *"given what I know about my system right now, is there any transitive path from an untrusted source to a high-privilege tool."* You can run that query continuously as the system changes.​

You are not proving the absence of all bad states. You are checking your architecture's structure against a set of known dangerous compositions, the kind of thing good threat modeling would surface if you had time to do it manually every time something changed.

If you are building agents in a high-assurance, compliance-driven environment then the formal verification argument gets stronger, though I am not sure many organisations that fall into that category are currently deploying agents yet. For everything else, the declarative graph approach seems like a better match for how these systems actually behave and change.
