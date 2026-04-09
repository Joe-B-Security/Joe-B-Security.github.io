---
title: "Improving a Coding Agent Harness: Part 2, Writing Code"
date: 2026-04-09
description: "Adding an OODA loop with a rule engine and verify phase to a coding agent harness, so the model proposes code and the harness checks it deterministically before accepting."
tags: ["AI Agents", "Developer Tools", "Code Quality"]
---

In [Part 1](/posts/2026-04-07-improving-coding-agent-harness-part1/), I added tree-sitter tools that let our mini coding agent find definitions and trace references structurally. In [Part 1.5](/posts/2026-04-07-improving-coding-agent-harness-part1-5/), I locked those tools behind a secure factory that makes files outside the workspace invisible for security. Both parts were about reading code, and this part will look into some approaches to improve the writing of code.

## Creativity vs determinism

Models tend to handle creativity and synthesis well, the parts of coding that involve reading a problem, understanding what needs to change, and generating code that addresses it. Where they struggle is consistency, memory, and self-evaluation, the parts that require remembering organisation-specific requirements across sessions, checking whether output broke existing tests, or deciding whether their own work is correct.

The idea behind this part was to bring determinism to the non-creative parts of the workflow by combining three concepts. 
- The first is injecting context that the model doesn't have, like security standards, compliance rules, or internal conventions that aren't in its training data, so the model writes code that meets actual organisational requirements rather than producing plausible output that misses them. 
- The second is test-driven development as a verification gate, a well-established practice where tests must pass before changes are accepted, applied here so the harness catches regressions the model isn't aware of. 
- The third is a Datalog-style rule engine that makes structured, deterministic claims about the workspace, which is a less common approach but works well here because decisions like "should I run tests after this file was modified?" are logical consequences of facts, not creative judgments that need a model. I discuss using Datalog for agent security here: [Datalog for Agent Security Analysis](https://joe-b-security.github.io/posts/2026-04-05-datalog-for-agent-security-analysis/) (As you can probably tell I'm a big fan.)

These three fit inside an OODA loop (observe, orient, decide, act), a structured decision cycle originally from US military strategy, with a verify phase added after act (more determinism!). The model generates code, the harness verifies it meets invariants before accepting the output, and failed verification loops back as feedback so the model retries rather than judging its own work.

## The OODA loop

The agent's flat ask-execute-record cycle becomes five explicit phases:

| Phase | What it does | Who does it |
|-------|-------------|-------------|
| **Observe** | Capture the task and current agent state | Harness |
| **Orient** | Retrieve relevant code from the workspace index and inject knowledge entries (org standards, conventions, previous session context) | Harness (vector search) |
| **Decide** | Derive which verify gates apply from workspace facts (syntax check, TDD gate) | Rule engine (deterministic) |
| **Act** | Model generates code, harness executes tools | Model + harness |
| **Verify** | Run the derived gates: parse modified files, run tests if coverage exists. If they fail, loop back with feedback | Harness (deterministic) |

{{< mermaid >}}
flowchart TD
    REQ[User request] --> O[Observe]
    O --> OR[Orient]

    KS[Knowledge store] --> OR
    CS[Code index] --> OR

    OR --> D[Decide]

    RE[Datalog rule engine] --> D

    D --> A[Act: model generates code]
    A --> V{Verify}

    SYN[Syntax check] --> V
    TDD[TDD gate] --> V

    V -->|pass| OUT[Accept output]
    V -->|fail| FB[Feedback to model]
    FB --> A

    style O fill:#d4edda
    style OR fill:#d4edda
    style D fill:#d4edda
    style V fill:#d4edda
    style A fill:#ffeeba
    style OUT fill:#d4edda
    style FB fill:#f8d7da
    style KS fill:#d4edda
    style CS fill:#d4edda
    style RE fill:#d4edda
    style SYN fill:#d4edda
    style TDD fill:#d4edda
{{< /mermaid >}}

The verify-retry loop is the key addition. When the model says "done," the harness runs the verify gates before accepting the answer. If verification fails, the model gets the failure output and tries again. The green phases are deterministic (handled by the harness), the yellow phase is where the model does its creative work, and the red path is the feedback loop when verification fails.

## The rule engine

The rule engine is a simplified [Datalog](https://en.wikipedia.org/wiki/Datalog) with a fact store, pattern-matching rules with variable binding, and forward-chaining to a fixed point. Facts are tuples, rules match patterns against facts and derive new facts, and variables (prefixed with `?`) unify across conditions in a rule.

At startup, the harness scans the workspace for test files and asserts coverage facts:

`[facts] assert test_covers('test_auth.py', 'auth.py')`

`[facts] assert has_tests`

When the model modifies a file, the harness asserts the modification and derives verify gates. The TDD gate (since it enforces that tests pass before changes are accepted) is where the variable binding matters:

`[rules] tdd_gate: file_modified('auth.py') + test_covers('test_auth.py', 'auth.py') -> verify_gate('run_tests')`

The `?file` variable binds to `'auth.py'` in the first condition and must match in the second. If the model modifies a file that has no test coverage, the rule doesn't fire, and if it modifies a covered file, tests run automatically without any model judgment involved.

## What it looks like running

I set up a test workspace with an `AuthService` class and five existing tests, then ran three scenarios against qwen3.5-9b. Each one exercises a different phase of the OODA loop. The observe phase kicks off every iteration by capturing the user's request and the current agent state, and the scenarios below focus on the phases that follow it.

**Orient: injecting organisational context.** The orient phase pulls in two kinds of context before the model starts generating: relevant code from the workspace (indexed at startup) and knowledge entries like organisational standards and conventions. In practice, an organisation might have dozens of security standards, API conventions, compliance requirements, and internal documentation that need to be followed across all code generation and review. You can't prompt for all of them every time, and expecting developers to remember which standards apply to which task doesn't scale. The orient phase handles this transparently by pulling in whatever is relevant to the current task. In this scenario, the organisation's security standards require that passwords are at least 8 characters and contain a digit. I asked the agent to add a `change_password` method, once without the OODA loop and once with that standard loaded as a knowledge entry.

Without OODA, the model wrote a working method with no input validation:

```python
def change_password(self, username, old_password, new_password):
    user = self.users_db.get(username)
    if user is None:
        return False
    if not self.authenticate(username, old_password):
        return False
    user["password"] = new_password
    user["attempts"] = 0
    user["locked"] = False
    return True
```

With OODA, the knowledge store contained one entry: `password_rules: Passwords must be at least 8 chars and contain a digit.` The model produced:

```python
def change_password(self, username: str, old_password: str, new_password: str) -> bool:
    user = self.users_db.get(username)
    if user is None:
        return False
    if user["locked"]:
        return False
    if user["password"] != old_password:
        return False
    if len(new_password) < 8:
        return False
    if not any(c.isdigit() for c in new_password):
        return False
    user["password"] = new_password
    user["attempts"] = 0
    return True
```

The second version has password validation matching the org rule, type hints, a locked-state check, and no `self.authenticate()` call (which would have incremented the attempts counter as a side effect), all from a single knowledge entry in the orient phase.

**Decide and verify: the TDD gate.** When the model modifies a file, the decide phase checks the rule engine to determine what verification is needed. The model doesn't decide whether to run tests, the rule engine derives it from workspace facts: if a modified file has test coverage, the TDD gate fires and the verify phase runs those tests before accepting the output. If tests fail, the verify phase feeds the failure back to the model as context for a retry.

I asked the agent to change the lockout threshold from 3 to 5. Without OODA, the model patched `max_attempts`, said "done," and left. The test `test_lockout_after_max_attempts` now fails because it only tries 3 wrong passwords but the threshold is 5, and the agent has no way of knowing.

```
Without OODA:
  TOOL [patch_file] auth.py: self.max_attempts = 3 -> 5
  AGENT: The lockout threshold has been updated.

  Tests: 1 failed (test_lockout_after_max_attempts)
  Agent: unaware
```

With OODA, the model made the same patch. But when it said "done," the decide phase had already derived two verify gates from the single fact `file_modified('auth.py')`:

```
syntax_on_modify: file_modified('auth.py') -> verify_gate('syntax_check')
tdd_gate: file_modified('auth.py') + test_covers('test_auth.py', 'auth.py') -> verify_gate('run_tests')
```

The syntax gate fires for any modified Python file. The TDD gate fires because the rule engine knows `test_auth.py` covers `auth.py` (asserted at startup from the workspace scan). The verify phase ran both gates, and the TDD gate caught the regression:

```
With OODA:
  TOOL [patch_file] auth.py: self.max_attempts = 3 -> 5

  VERIFY: Tests failed (exit code 1):
    test_lockout_after_max_attempts FAILED
    assert svc.authenticate("bob", "hunter2") is False

  TOOL [read_file] test_auth.py     <- model reads test to fix it
  TOOL [patch_file] test_auth.py    <- model starts updating test
```

The verify phase injected the test output as feedback, and the model started fixing the test. The model didn't decide to run tests or notice the regression on its own, because that decision was derived by the rule engine and enforced by the verify phase based on workspace facts.

**Orient across sessions: knowledge persistence.** Without persistence, the agent rediscovers the same information every session: which test command to use, which conventions to follow, which files are related. That costs tool calls and context window budget each time. The knowledge store fixes this by persisting what the agent learns to disk, so the orient phase in a new session already has context from previous ones.

I told the agent to remember the test command, and it persisted the entry alongside the password standard from the first scenario. When a new session starts, the orient phase loads these entries automatically and injects them into the prompt before the model generates anything:

```
Session 1:
  TOOL [remember] key="test_command" content="python -m pytest test_auth.py -v"
  -> remembered 'test_command' (workspace)

  Persisted: .mini-coding-agent/knowledge/entries.json

Session 2 (new session, same workspace):
  Knowledge loaded automatically:
  - test_command: python -m pytest test_auth.py -v
  - password_rules: Passwords must be at least 8 chars and contain a digit.
```

The knowledge store has two tiers: workspace entries that stay with the project, and global entries that follow you across projects. Both persist to disk and load automatically on startup, so the orient phase in a new session already has the context that previous sessions accumulated.

Across all three scenarios, the model's creative work didn't change, it generated the same kind of code in each case. What changed was what the OODA loop did around it. Orient injected context the model couldn't know about, decide and verify caught a regression the model wasn't aware of, and persistent knowledge meant orient started informed in future sessions. Each of these is a deterministic operation that the harness handles without the model needing to be better at self-evaluation or memory.

## What a production version would look like

The rule engine is a simplified Datalog. Full Datalog solvers support policy enforcement, intent routing, and verification in production. The full version supports negation, aggregation, and tiered governance where some rules are immutable kernel axioms and others are learned from data, but the shape of facts being asserted, rules firing, and decisions being derived is the same.

The orient phase finds relevant knowledge by comparing the current task against stored entries using basic keyword-frequency matching, and persists entries as JSON files. Production would use an embedding model and vector database for faster, more accurate retrieval, with the entries themselves coming from automated workflows that pull standards and conventions from existing organisational tooling like policy management systems, internal wikis, or compliance platforms rather than relying on someone to type them in.

The verify phase runs `ast.parse()` and pytest. Production would add linting, type checking, security scanning, and coverage thresholds as additional gates that must pass before output is accepted, but the loop of proposing, checking, and feeding failures back stays the same.


## Try it yourself

The [companion repository](https://github.com/Joe-B-Security/mini-coding-agent/tree/feat/part2-writing-code) has the OODA loop layered on top of the Part 1 code understanding tools and Part 1.5 secure factory.

```bash
git clone https://github.com/Joe-B-Security/mini-coding-agent.git
cd mini-coding-agent
git checkout feat/part2-writing-code
uv sync

uv run python mini_coding_agent.py \
    --backend openai \
    --host http://127.0.0.1:4444 \
    --model qwen/qwen3.5-9b \
    --approval auto \
    --cwd /path/to/a/python/project
```

To see the verify loop in action, point it at a project with tests and ask it to make a change that affects tested code. The rule engine will derive `verify_gate("run_tests")` and the verify phase will catch any regressions.

To see knowledge entries change output, add an entry with the `remember` tool or create `.mini-coding-agent/knowledge/entries.json` directly:

```json
[{"key": "convention", "content": "your org rule here", "scope": "workspace",
  "source_project": "/path/to/project", "tags": [], "created_at": ""}]
```

To compare with and without OODA, use the `--no-ooda` flag:

```bash
# Without OODA (baseline)
uv run python mini_coding_agent.py --no-ooda --cwd /path/to/project

# With OODA
uv run python mini_coding_agent.py --cwd /path/to/project
```

The `/rules` command in the REPL shows the current fact store and derived conclusions. The rule engine traces print to stderr so they appear alongside the agent output.
