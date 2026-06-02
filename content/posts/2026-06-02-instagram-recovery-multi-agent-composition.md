---
title: "Imagining the Instagram Recovery Exploit as a Multi-Agent Composition Issue"
date: 2026-06-02
description: "A reported account-recovery takeover at Instagram, reconstructed as several agents each behaving correctly while the original intent erodes across their handoffs."
tags: ["AI Security", "Agent Security"]
---

Over the past few days a [reported account-recovery flaw](https://krebsonsecurity.com/2026/06/hackers-used-metas-ai-support-bot-to-seize-instagram-accounts/) let attackers take over Instagram accounts, including high-profile ones like the Obama White House account, by getting the Meta AI Support Assistant (which they call "MAISA") to link a new, attacker-controlled email to the account and reset the password through it. The attack needs little more than the target's username, which is public, plus a VPN near the victim's city so the location looks normal to the platform's risk checks. The attacker asks the support assistant to link a new email they control, one that was never associated with the account, and the assistant sends a verification code to it. The attacker reads the code from their own inbox and enters it; the relink completes, and the platform issues a fresh password reset link. Existing sessions are revoked and the password changes, and the real owner gets no notification because the account's email now points at the attacker.

The natural way to read this is that one credulous chatbot was given too much authority and too little judgement. I think it is more interesting to imagine the same outcome produced by several agents that were each behaving correctly within their own scope. This pattern, where each agent behaves correctly and the composition does not, is one I keep seeing when work is split across agents, and I expect more vulnerabilities like it as multi-agent systems become common. What follows is a reconstruction of an architecture that could produce this outcome.

## Imagining the Architecture

A recovery flow like this has to understand what the user is asking for, decide whether the request looks legitimate, issue new credentials, and clear the old sessions. In a support system built from LLM agents, recovery is one workflow among many.

A reasonable version routes the request through several specialised agents, each owning one part of the job:

- A **front-line support agent** reads the conversation, recognises an account-recovery request, gathers the details it needs, and delegates the task downstream. One of those details is the contact address the codes should go to.
- A **risk check agent** scores the session on signals like location and device, and returns a verdict.
- A **recovery agent** takes the delegated task, gets a clean risk verdict, links the new contact after verifying it with a code, and then resets the password and revokes the existing sessions.

The recovery agent makes its changes through two backend services: an account service that stores the contact and sessions, and an email service that delivers the code to whatever address it is handed.

{{< mermaid >}}
flowchart TD
    U[User or attacker]
    subgraph agents["Agents"]
        FA[Front-line support agent]
        RK[Risk check agent]
        RA[Recovery agent]
    end
    subgraph backend["Backend services"]
        CS[Email service]
        AS[Account service]
    end
    U <--> FA
    FA --> RA
    RA <--> RK
    RA --> CS
    RA --> AS
    CS --> U
{{< /mermaid >}}

Look at each agent on its own and it is hard to point at the one that is broken. The front-line agent recognised a genuine recovery request and passed on the contact address the user gave it, leaving any vetting of that address to the steps downstream. The risk check agent saw a session from the expected region and returned a normal score, assuming the new email had already been validated since it was passed in by another agent. The recovery agent received a task that said an account needed recovering and a contact to send the code to, and it did exactly that. Each of those decisions could be defended in isolation.

## Where the Original Intent Gets Lost

A few facts together should have stopped this request, but no single agent ever holds all of them at once.

- The front-line agent knows the contact address is new, supplied in this conversation by the person asking for the reset.
- The account service holds the address already on file, and it differs from the new one, but the recovery agent never asks it to check, assuming the new email was validated before the task reached it.
- The recovery agent knows the reset it performs hands full control of the account to whoever holds the newly linked email.

Put those facts next to each other and the request is hard to defend, since it is a brand-new contact address, never seen on the account, being used to grant a complete takeover. Spread across the agents and services, each fact looks harmless, and each step has good reason to keep going.

Part of why this happens is that handoffs tend to pass conclusions rather than evidence. The recovery agent receives a task that reads "recover this account and send the code to this contact," not the conversation that produced it, so it never learns that the contact was supplied by the same person requesting the reset. The risk check agent's verdict comes back as a bare "risk acceptable," which the recovery agent reads as the whole request being fine, including the new email, though all the agent actually examined was the session's location. As each step summarises its work for the next, the qualifications that would have mattered downstream are lost.

The scope of the task drifts the same way, starting out narrow as a way to help a genuine locked-out owner regain access. By the time it reaches the recovery agent, the operative instruction has quietly widened into something closer to "issue a reset and send the code to the contact in the task." No step chose to broaden the goal; each handoff carried a slightly more general version of it, and the original intent that would have kept the next step in bounds was left behind.

The recovery agent then links the attacker's email to the account and revokes the existing sessions, having taken the new address as already vetted. Any warning that would have reached the real owner now goes to the attacker's address, so the owner hears nothing. By the time they think to check, the email recovery relies on already points at the attacker.

{{< mermaid >}}
flowchart TD
    U[User or attacker] --> FA[Front-line support agent]
    FA -->|escalate: this is the owner, link email X| RA[Recovery agent]
    RA -->|check this session| RK[Risk check agent]
    RK -->|risk acceptable, location only| RA
    RA -. assumed validated upstream, never checked .-> VAL[Does email X belong to the account?]
    RA -->|send code to email X| CS[Email service]
    CS -->|code lands in the attacker's own inbox| U
    U -->|returns the code| RA
    RA -->|email X treated as validated, link and reset| RESET[Relink and password reset]
    RESET --> OUT[Account taken over]
{{< /mermaid >}}

## Where a Fix Would Sit

Because each agent is already doing its job, a fix means adding deterministic checks where they are currently missing, at the handoffs between agents and inside the agents that take privileged actions. This is the Zero Trust reflex, that where a task comes from is not a reason to trust it. The recovery agent trusted the task because it arrived from another agent, so the correction is to carry the original request far enough down the chain that the privileged step can confirm the new email actually belongs to the account, rather than inherit that conclusion from upstream.

None of this is new security thinking, and the old primitives apply directly here. Least privilege scopes what the recovery capability can touch, and the check itself should be a deterministic gate, code that runs before the reset rather than a call the agent makes. The agent's reasoning runs on the same input the attacker controls and can be steered by it, whereas a fixed comparison does not depend on that input at all.

## How Much to Read Into This

I have no visibility into Meta's actual implementation, so the architecture above is a reconstruction chosen because it produces the reported outcome, and I am interested in the pattern it shows. It is fair to ask whether splitting the work across agents is really to blame, since a single monolithic prompt with the same tools could make the same mistake. The split seems to make the mistake easier to fall into and harder to notice, because the brand-new contact, the address already on file, and the reset about to hand the account over never land in one place where they could be weighed together.

This kind of failure tends not to live inside any one agent, so reviewing each agent on its own will usually tell you everything is fine. It is a business-logic problem spread across a chain of handoffs, and that kind of problem has traditionally been harder to surface than an ordinary bug.
