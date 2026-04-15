---
title: "Improving a Coding Agent Harness: Part 4, Hooks"
date: 2026-04-15
description: "Adding lifecycle hooks to a coding agent harness, then measuring what going from subprocess dispatch to in-process Rust via PyO3 actually costs and saves, on two workloads with very different results."
tags: ["AI Agents", "Developer Tools", "Performance", "Rust", "PyO3"]
---

In [Part 1](/posts/2026-04-07-improving-coding-agent-harness-part1/), I added tree-sitter tools for structural code reading. In [Part 1.5](/posts/2026-04-07-improving-coding-agent-harness-part1-5/), I locked those tools behind a secure factory. In [Part 2](/posts/2026-04-09-improving-coding-agent-harness-part2/), I added an OODA loop with a rule engine and verify phase. In [Part 2.5](/posts/2026-04-10-improving-coding-agent-harness-part2-5/), I added a RAG layer over OWASP guidance for secure code generation. In [Part 3](/posts/2026-04-13-improving-coding-agent-harness-part3/), I used the harness to find a scoring-path bug in a coding benchmark.

This part adds hooks: named events that fire at lifecycle points during tool execution, where each hook can observe, allow, deny, or rewrite what the agent is about to do. The framework itself is the first half of the post. The second half is about why dispatch performance matters enough to go from Python to Rust via PyO3, measured on two workloads where the results turn out to be very different depending on where Python is spending its time.

## The hook framework

The whole framework is one Python module (`hooks.py`) exposing three things:

- **`HookSpec`** describes one hook entry: which event it listens to, which tools it matches, how it runs.
- **`HookDecision`** describes what a hook wants the runtime to do: allow, ask, or deny, with optional argument rewrites.
- **`HookManager`** is the dispatcher that holds the hook list, invokes each one, and merges decisions when multiple hooks match.

### Events

Five events, wired at different lifecycle points in the agent:

| Event | Fires when | Can it block? |
|---|---|---|
| `PreToolUse` | After validation and approval, before the tool runs | Yes (deny) |
| `PostToolUse` | After the tool returns successfully | No (but can rewrite output) |
| `PostToolUseFailure` | After the tool raises an exception | No (observe only) |
| `SessionStart` | Once, when the agent is constructed | No (observe only) |
| `UserPromptSubmit` | At the top of `ask()`, before anything else | Yes (deny) |

`PreToolUse` and `PostToolUse` are the two that matter most and the two the benchmark measures, while the other three are wired so that future hooks can be added without touching the runtime.

### Hook types

A hook is either a command hook or a callable hook:

```json
[
  {"event": "PreToolUse", "match": {"tool": "write_file"},
   "command": "./example_hooks/notify.sh"},

  {"event": "PostToolUse",
   "callable": "example_hooks.log_callable:check"}
]
```

**Command hooks** are shell commands run via `sh -c`. The framework pipes the full JSON payload to stdin and reads a decision back: exit code 0 means allow, exit code 2 means deny, and anything else is treated as a deny to be safe. If the hook prints JSON to stdout, the runtime parses it as a structured decision with optional argument rewrites or output redaction. Command hooks are language-agnostic (bash, Python, Go, whatever), but every call spawns a subprocess, which has performance implications covered in the benchmark sections below.

**Callable hooks** are Python functions identified by an import path (`module:function`). The framework imports the module once on first invocation, caches it, and calls the function directly on each event. Same decision protocol: `None` or `"allow"` means allow, and a raised exception is treated as a deny. Callable hooks only support Python natively, but Python can call into compiled code via a PyO3 extension, which is what the Rust integration demonstrates.

### Priority and matching

When multiple hooks match one event, the framework runs them in declaration order and merges decisions with a deny-wins priority: deny beats ask, ask beats allow, and the first deny short-circuits the chain. Rewrites accumulate, so an audit hook, a redaction hook, and a classifier hook can all sit on the same event without stepping on each other.

Hooks can optionally filter which tools they run for via a match key (`{"match": {"tool": "write_file"}}` or a list of tool names), with no match key meaning "run on every tool call." This is runtime-layer matching rather than requiring each hook to self-filter from its payload.

## The performance problem

Let's assume an agent makes 100 tool calls per user request, each triggering a pre-hook and a post-hook, and you have an audit hook, a secrets scanner, and a command classifier stacked on top. That is somewhere around 400 to 600 hook invocations per turn. If each hook takes 50ms, the overhead alone reaches 20 to 30 seconds, the agent becomes visibly slow, and people disable the hooks.

There are two independent sources of that cost, and the benchmark is structured to separate them:

- **Fork and exec overhead.** Spawning a new process on every call costs roughly 5ms on macOS regardless of what the process does.
- **Python interpreter startup.** If the subprocess is Python, it also pays 30 to 80ms bringing the interpreter up plus 10 to 100ms importing modules and compiling patterns, and that tax gets paid on every call because the process exits and takes the warm state with it.

These two taxes stack on top of each other, and a Python subprocess hook pays both. A Python callable running in-process pays neither (imports happen once at startup). A Rust callable running in-process pays neither, and also skips the Python bytecode cost in the scan itself.

## From Python to Rust

I normally work in Python rather than Rust, and Claude Code helped a lot with the Rust side. Working through this was a good way to understand what Rust actually gives you in this context: the type system catches whole categories of mistakes at compile time that Python would only surface at runtime, cross-module function calls between classifiers are just regular calls with no serialisation overhead, and libraries like the `regex` crate offer data structures (like `RegexSet`) that take a fundamentally different algorithmic approach to problems Python's standard library solves in a slower way. The performance numbers in the benchmark below come from those structural differences rather than from Rust just being "a faster language."

### PyO3 and maturin

[PyO3](https://pyo3.rs/) is a Rust crate that produces Python extension modules from Rust code. Functions annotated with `#[pyfunction]` become callable from Python, and PyO3 handles reference counting, type conversions, and error propagation across the language boundary. What you write is Rust, and what you get is a shared library that Python loads like any other extension.

[maturin](https://www.maturin.rs/) is the build tool that turns a PyO3 crate into a Python wheel. It runs cargo, takes the resulting shared library, wraps it in a wheel, and installs it into the active virtualenv. The `--release` flag turns on compiler optimisation (without it, the extension runs at debug speeds, which can be 20 to 50 times slower). The crate's release profile also enables link-time optimisation (`lto = "fat"`, `codegen-units = 1`), which lets the compiler inline functions across module boundaries in the inner scan loop.

### What "compiled to machine code" means here

Python source goes through three layers: `.py` compiles to bytecode (`.pyc`), the interpreter's eval loop dispatches those bytecode instructions one at a time, and frequently-called operations like `re.search()` drop into C extensions for the actual work. The bytecode dispatch loop sits between every Python-level call, so even when the inner work is C-speed, you pay Python overhead to get there and again on the next loop iteration.

Rust via PyO3 skips all three layers. The Rust compiler produces native machine instructions with full optimisation (inlining functions, removing unused code, using hardware-level parallelism where possible), and when the PyO3 glue calls into the Rust function, control transfers directly into compiled code and stays there until the function returns. The benchmark measures that specific gap, where the Python interpreter is absent from the scan itself and only present at the call site and the return site.

### The Rust crate

The extension (`rust_hook/`) exposes two benchmark workloads:

- **`scan_regex`** extracts string values from the hook payload, concatenates them into one block of text, and scans against roughly 100 benign regex patterns combined into a single `RegexSet`. The patterns are deliberately benign (words, numbers, URLs, log markers, code idioms) because the benchmark is measuring dispatch and scan cost, not classifier behaviour.

- **`walk_ast`** extracts the command field from the payload, parses it as bash using `tree-sitter-bash`, walks the syntax tree with a `TreeCursor`, and returns the node count. When an agent runs a shell command, a hook that wants to understand what the command actually does needs to parse it structurally, because splitting on whitespace breaks on quoting, redirects, pipelines, and subshells. Something like `sudo env VAR=1 grep "pattern" < input.txt | sort` has wrapper commands, a redirect, and a pipeline that are all visible in the syntax tree but not reliably extractable from the raw string. The benchmark workload is a simplified version of this (parse and walk, counting nodes) and also serves as a second data point for the Rust comparison, since tree-sitter is a C library on both the Python and Rust sides.

`RegexSet` is the data structure that explains most of the speed difference: rather than compiling each pattern into a separate `Regex` and looping over them, it combines all N patterns into a single state machine that scans the text once and reports which patterns matched. The per-call cost is bounded by the length of the text being scanned rather than the number of patterns, which explains why scan time stays roughly flat as pattern count grows in the scaling experiment below.

## The benchmark

`benchmark_hooks.py` measures three architectures on two workloads: six rows total, all on the same roughly 1KB payload, all doing identical logical work within each workload.

```
Workload: regex scan (~100 benign patterns)
  python subprocess     mean = 37.399ms   p99 = 60.98ms   overhead(100 calls) = 3.740s
  python callable       mean =  1.063ms   p99 =  1.21ms   overhead(100 calls) = 0.106s
  rust callable         mean =  0.018ms   p99 =  0.02ms   overhead(100 calls) = 0.002s

Workload: bash AST walk (tree-sitter parse + TreeCursor walk)
  python subprocess     mean = 38.351ms   p99 = 60.98ms   overhead(100 calls) = 3.835s
  python callable       mean =  0.148ms   p99 =  0.20ms   overhead(100 calls) = 0.015s
  rust callable         mean =  0.115ms   p99 =  0.15ms   overhead(100 calls) = 0.011s
```

```
Speedup summary
  regex  architectural: 35.2x   compilation: 60.9x   combined: 2,143x
  ast    architectural: 259.2x  compilation: 1.3x    combined: 335x
```

The two workloads have completely different profiles, and the reasons come down to where each workload spends most of its time.

### Why regex scanning is faster in Rust

On the regex row, the compilation win (60.9x) is almost twice the architectural win (35.2x), which looks counterintuitive until you examine what each step eliminates. The architectural step (subprocess to in-process) removes the roughly 37ms tax of spawning a fresh interpreter, reimporting modules, and recompiling patterns on every call. The compilation step (Python in-process to Rust in-process) eliminates the Python-level scan loop:

```python
for pattern in _COMPILED_PATTERNS:
    if pattern.search(haystack):
        match_count += 1
```

Python's `re` module is implemented in C, so the actual regex scan is fast, but the loop around it is pure Python bytecode overhead. At roughly 100 patterns, it adds up. The natural assumption is that joining all patterns into one combined regex with `|` between them (`re.compile('|'.join(patterns))`) would close most of the gap, but it does not:

```
Python loop (100 patterns):          1,069.7 us
Python joined with |:                    970.4 us    (1.1x faster)
Rust RegexSet:                          ~17   us   (57x faster than joined)
```

Joining saves roughly 10%, because the gap is algorithmic rather than mechanical. Python's `re` module uses a regex engine that tries each alternative one at a time at each position in the text, so even with all 100 patterns joined into a single expression, the engine is still doing work proportional to the number of patterns multiplied by the length of the text. Rust's `regex` crate works differently: it compiles all N patterns into a single state machine that walks through the text once, tracking which patterns are still potentially matching as it goes, updating that state in constant time per character regardless of how many patterns there are. The total work scales with the length of the text, not the number of patterns.

The 60.9x difference comes from the two languages using regex engines that work in structurally different ways, and Python cannot close it without switching regex libraries entirely (for example, to `google/re2` Python bindings).

### Why AST walking is not much faster in Rust

On the AST row the numbers go the opposite way: 259x architectural win but only 1.3x compilation win.

The architectural win is large because tree-sitter parsing is expensive (grammar loading, parser construction) and the subprocess variant pays all of that again on every call. The compilation win is small because tree-sitter parsing itself is C code and both Python and Rust call into the same C library, so the parse step is roughly equal cost in both languages.

Rust wins on the walk step (its `TreeCursor` stays in native code, while Python's bindings cross back into C on every `.children` / `.type` access), but parse dominates total time:

```
Python parse only:    109.8 us
Python walk only:      45.2 us
Python parse + walk:  144.5 us
```

Rust saves most of the walk (its `TreeCursor` counts 394 nodes in roughly 1 to 2 microseconds) but cannot shrink the parse because that is shared C code, which is why the total advantage comes out at 1.3x even though the walk-specific advantage is likely 20x or more.

Looking at both rows together, the Rust path pays for itself when the Python interpreter is doing the repetitive work (looping over patterns, dispatching calls one at a time), and offers marginal returns when Python is already handing control to a C library that does most of the work. Knowing which case applies to a given workload is what determines whether PyO3 is worth the build complexity.

## Scaling

The benchmark above uses roughly 100 patterns, but a real classifier might have several hundred, so it is worth checking how scan time changes as pattern count grows.

`benchmark_scaling.py` runs the same scan at 10, 50, 100, 500, and 1,000 patterns, measuring both Python in-process and Rust `RegexSet` at each size. Both sides scan all patterns and count matches with no early exit.

```
patterns  python in-process  rust in-process  speedup
10        0.0453 ms          0.0003 ms        132x
50        0.2487 ms          0.0006 ms        412x
100       0.5248 ms          0.0013 ms        418x
500       2.6889 ms          0.0013 ms        2,011x
1000      5.4153 ms          0.0019 ms        2,905x

Linear fit 10 to 1000:
  Python slope:  5.4243 us per added pattern
  Rust slope:    0.0015 us per added pattern
  Python grows 3,529x steeper than Rust
```

Python grows linearly at 5.4 microseconds per added pattern: every added pattern is one more iteration through Python's bytecode dispatch loop. Rust stays essentially flat at 0.0015 microseconds per added pattern, because `RegexSet` compiles all patterns into a single state machine where scan cost is bounded by text length rather than pattern count. Going from 10 to 1,000 patterns takes Python from 45 microseconds to 5,415 microseconds while Rust moves from 0.3 to 1.9 microseconds.

Let's say a production classifier stack has 300 to 500 patterns across secrets scanning, command classification, and path classification. At that range, Python's in-process cost lands at roughly 1.6 to 2.7ms per call, which multiplied across a few hundred hook invocations per turn starts to become visible. The same work on the Rust row stays in the microsecond range and remains invisible. Python in-process is not too slow today at 100 patterns, but the slopes diverge, and building the PyO3 extension now means the dispatch path does not need to change when richer classifiers arrive.

## What a production version would look like

The benchmark numbers are from a single machine, single run, warm cache, no error bars. The gaps are large enough that statistical noise does not change any conclusion, but the absolute numbers depend on hardware, Python version, and Rust compiler version, while the ratios should hold across different setups since they reflect how the architectures differ rather than how fast any particular machine is.

A few things worth noting:

- The Rust extension passes the hook payload as a JSON string across the PyO3 boundary (`json.dumps` on the Python side, JSON parsing on the Rust side), which costs roughly 3 to 5 microseconds on a 1KB payload. That is a meaningful slice of the 18-microsecond Rust regex row. Passing the Python dictionary directly into Rust without converting to JSON first would be faster, but the JSON boundary matches the protocol command hooks use and keeps the same Rust function usable for either hook type.
- The scaling experiment only covers regex. Tree-sitter parse cost scales with command length rather than pattern count, so AST scaling would follow a different curve.
- The Python regex loop and Rust's `RegexSet` are doing slightly different things under the hood, since a Python classifier could join all patterns into a single regex with `|` between them instead of looping over each one separately. The per-pattern loop was used because real classifiers need to know which specific pattern matched, and the joined variant was measured separately (1.1x faster, as shown above).

## Try it yourself

The [companion repository](https://github.com/Joe-B-Security/mini-coding-agent/tree/feat/part4-hooks) has the hook framework and Rust extension layered on top of the Parts 1-3 code.

```bash
git clone https://github.com/Joe-B-Security/mini-coding-agent.git
cd mini-coding-agent
git checkout feat/part4-hooks
uv sync
```

Build the Rust extension (requires a Rust toolchain):

`cd rust_hook && uv run --project .. maturin develop --release && cd ..`

Run the headline benchmark:

`uv run python benchmark_hooks.py`

Run the scaling experiment:

`uv run python benchmark_scaling.py`

Run the agent with example hooks loaded:

```bash
uv run python mini_coding_agent.py \
    --backend openai \
    --host http://127.0.0.1:4444 \
    --model qwen/qwen3.5-9b \
    --approval auto \
    --hooks-file example_hooks/hooks.json \
    --cwd /path/to/a/python/project
```

## Series

- [Part 1, Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1/)
- [Part 1.5, Securely Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1-5/)
- [Part 2, Writing Code](/posts/2026-04-09-improving-coding-agent-harness-part2/)
- [Part 2.5, Securely Writing Code](/posts/2026-04-10-improving-coding-agent-harness-part2-5/)
- [Part 3, Scoring 100% on Coding Benchmarks](/posts/2026-04-13-improving-coding-agent-harness-part3/)
- Part 4, Hooks (This post)
- [Part 4.5, Security Hooks](/posts/2026-04-15-improving-coding-agent-harness-part4-5/)
