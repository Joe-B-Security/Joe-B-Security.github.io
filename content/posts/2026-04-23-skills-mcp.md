---
title: "Skills, MCP, and the Job Each One Is Good At"
date: 2026-04-23
description: "Looking at the current state of skills and MCP, the packaging layer that has grown up around them, and the questions worth asking before reaching for either."
tags: ["AI Agents", "MCP", "Developer Tools"]
---

Skills and MCP get talked about as if they were competing answers to the same problem, and the platforms seem to have moved past that framing. Skills are reusable guidance and supporting material that load when an agent needs them. MCP is a standard for connecting agents to external tools, data, and workflows. Anthropic and OpenAI have both spent the past few months adding packaging, discovery, and governance features on top of skills and MCP, and the useful question now is which layer of the stack your problem sits at and what you need from each.

Claude Code and Codex are the two most popular and visible implementations of all of this, so I will lean on them as the running examples throughout. The framing is not specific to either, and third-party frameworks and IDEs are moving in similar directions.

## The current state

On Anthropic's side, Claude Code now treats MCP as production infrastructure, supporting [remote HTTP](https://code.claude.com/docs/en/mcp) as the recommended transport for remote servers, local stdio for local servers, dynamic tool updates, automatic reconnection, and managed MCP configuration with allowlist and denylist enforcement. Managed config has two mechanisms: an OS-level `managed-mcp.json` that takes exclusive control of which servers a user can connect to, and policy-based allow and deny entries in managed settings.

Context management has become a core part of the protocol, with tool search on by default in Claude Code, only tool names loading at session start, and full schemas deferred until discovery. Anthropic separately shipped a [Tool Search Tool with `defer_loading: true`](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/tool-search-and-programmatic-tool-calling) at the API level, with docs claiming over 85% reduction in tool-definition tokens, and their [code execution with MCP pattern](https://www.anthropic.com/engineering/code-execution-with-mcp) reports a 98.7% reduction on a Google Drive to Salesforce workflow by keeping intermediate data out of the conversation.

Skills use progressive disclosure across three tiers (metadata always loaded, the full `SKILL.md` loaded on trigger, and bundled files only if the skill needs them), and OpenAI's [Codex Skills](https://developers.openai.com/codex/skills) use the same shape.

Both platforms now support event-driven and scheduled patterns directly, with Anthropic's [Channels](https://code.claude.com/docs/en/channels) acting as MCP servers that push events into a running session, along with official bridges for Telegram, Discord, and iMessage and enterprise controls via `channelsEnabled` and `allowedChannelPlugins`. [Scheduled Routines](https://code.claude.com/docs/en/routines) run on Anthropic-managed infrastructure and trigger on cron, API calls, or GitHub events. Codex added thread automations on schedules and an in-app browser, and its recent changelog covers MCP diagnostics, plugin MCP loading, hooks observing MCP tools, and skill-description trimming to stay within context budgets.

MCP itself is now governed by the [Agentic AI Foundation](https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation), a directed fund of the Linux Foundation, with Anthropic, OpenAI, and several major cloud vendors among the participants.

## Three layers

The cleanest way to read all of this is as three layers of stack:

- **Method.** Skills package reusable task knowledge, the conventions, procedures, playbooks, and reference material that describe how your team does something. Progressive disclosure means the cost of carrying many skills is mostly paid when one fires.
- **Reach.** MCP standardises how an agent connects to a live system, covering tools, resources, prompts, and push events. The recent protocol work has been about discoverability and context economics, so MCP can expose many tools and resources without flooding the context window.
- **Packaging and policy.** Plugins, managed config, allowlists, channels, and routines decide which skills and servers can be installed, how they are shared, what permissions they run under, and when they are allowed to fire.

Anthropic and OpenAI converged on this shape from different angles, with Anthropic's [Claude Code plugins](https://code.claude.com/docs/en/plugins) bundling skills, agents, commands, hooks, and MCP servers under a `.claude-plugin/plugin.json` manifest, and OpenAI's [Codex plugins](https://developers.openai.com/codex/plugins) doing the same thing with `.codex-plugin/plugin.json`, including app connectors alongside MCP. The Codex plugin creator is itself a skill, and Anthropic ships an [`mcp-builder` skill](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md) that teaches an agent how to design MCP servers, so each ecosystem is already using the method layer to build the reach and packaging layers.

## Questions worth asking

Once the layers are named, the decision comes down to a few questions about the specific problem.

**Do I need reusable method, live access, or both?** If the model has the tools it needs but keeps getting the process wrong, that is a method problem and a skill is usually the right answer. If the agent cannot reach the system, cannot authenticate against it, or has no structured way to describe what is there, that is a reach problem and MCP is what the ecosystem has converged on. Most real workflows want both, and the two do different jobs even when they land in the same prompt.

**Is this for me, a team, or an organisation?** A solo developer can often ship useful agents with shell scripts and skills alone, and a managed MCP deployment is hard to justify at that scale. A team needs shared auth, consistent tooling, and a sense of what is actually installed across machines. An organisation needs central policy, revocation, audit, and a way to decide which servers are safe to expose. The packaging layer mostly pays off at scale, and below that point it tends to add process without much return.

**Does this need to be installable, reviewable, and governable across people?** If yes, the question becomes which packaging format fits. Codex plugins handle this via a repo-scoped marketplace at `$REPO_ROOT/.agents/plugins/marketplace.json`, so a `git clone` gives teammates the same plugins. Claude Code plugins cover similar ground with a richer component set. Managed MCP config and allowlists are the matching controls on the reach side, and channels, routines, approval policies, and Codex's `requirements.toml` group policies decide which actions can fire and who approves them.

**What do the context and token economics look like at my scale?** This used to be the main argument against MCP, and some of it still holds, but newer tooling has addressed much of it. Tool search and deferred loading cut schema costs sharply, and the code execution pattern keeps large intermediate data out of the conversation entirely.

**Is the work interactive, scheduled, or event-driven?** This used to resolve itself because agents were mostly interactive, but scheduled routines now want managed infrastructure so they can run reliably outside a session, and event-driven workflows want push channels or hooks so an external signal can reach the agent without a person in the loop. These sit above skills and MCP and shape what "deployed" actually means.

## Where each fits once you have answered

I would reach for a skill to give the model a way of working: coding conventions, research routines, deployment procedures, triage playbooks, secure-coding guidance. A useful pattern is to build the right tool first and then write the skill that teaches the model how to use it, which keeps the tool simple and pushes the judgement into the skill.

I would reach for MCP when the model needs to interact with a live system in a structured, reusable, managed way, such as a support agent reading tickets and opening follow-up tasks, a sales assistant querying Salesforce and updating records, or a developer agent inspecting CI logs and automating browser-driven tests. Guidance alone does not help in these cases because the work depends on live state the agent has to read and write.

I would reach for the packaging layer once distribution matters, which usually means moving from a skill on one developer's laptop to the same skill published as a plugin, bundled with the MCP server it depends on, gated by policy, and installable from a shared marketplace. Plugins let teams express distribution and governance in config rather than through process documents.

Most non-trivial workflows end up using all three, so a product support workflow might use MCP for the ticketing system, CRM, and knowledge base, a skill for how the team triages and escalates, and a plugin to bundle both alongside approval policies for actions that change state. A dev workflow might use MCP for GitHub, CI, and logs, a skill for how the team reviews risky deploys, and a plugin distributed through a repo-scoped marketplace so new joiners get the same tooling with a single clone.

## Where each still strains

Skills can end up describing a world the model cannot actually touch, so a skill that explains a workflow perfectly but has no path to the underlying system tends to produce confident output with no real state behind it. They also do not sync cleanly across surfaces, so the same skill can behave differently in Claude Code, Claude.ai, and the API. LlamaIndex, who ship both skills and MCP tooling, reported from building their [LlamaAgents Builder](https://www.llamaindex.ai/blog/skills-vs-mcp-tools-for-agents-when-to-use-what) that skills "were rarely invoked, and often did not yield substantially better results compared to when only our documentation MCP was used," which they partly attributed to MCP giving them a more current single source of truth as their SDK evolved.

MCP has real critiques and most are still live, with context cost the clearest in naive deployments that load many tool schemas up front, and auth maturity a common secondary concern even as protocol work moves quickly. Some teams have reportedly deemphasised MCP in certain internal workflows, with Perplexity the most cited example, though they still ship an MCP server for external developers. Simon Willison's ["lethal trifecta"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (private data, untrusted content, external communication) applies directly to most default MCP setups. Most of this is solvable at the deployment layer through OAuth, managed config, remote HTTP transports, and gateways, and the default deployment is where most of the reported pain comes from.

The packaging layer is the newest and its failure modes are still emerging. Plugins make distribution easier for both helpful and risky tooling, since a badly reviewed plugin can bundle a helpful-looking skill alongside an MCP server that is not, and the plugin becomes the trust boundary whether you intended it to or not. Org-level allowlists help with this when someone is actually maintaining them.
