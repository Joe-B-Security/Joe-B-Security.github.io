---
title: "Improving a Coding Agent Harness: Part 1.5, Securely Reading Code"
date: 2026-04-07T10:00:00
description: "When you give a coding agent tools to read code, you also give it access to everything in the workspace. The factory pattern fixes this at construction time."
tags: ["AI Security", "AI Agents", "Coding Agents"]
---

In [Part 1](/posts/2026-04-07-improving-coding-agent-harness-part1/), I added tree-sitter-based code understanding tools to [mini-coding-agent](https://github.com/rasbt/mini-coding-agent), an open-source coding agent harness. The tools let the agent find definitions, trace references, and read specific functions by name instead of relying on grep and line-range reads. The code reading tools had no boundary enforcement, so the agent could read files outside the current directory and access sensitive files without restriction.

## The security gap in the code intel tools

`find_definitions` takes a symbol name and a path, walks the directory tree, parses each file, and returns matches. `read_symbol` takes a file path and a function name, chunks the file at AST boundaries, and returns the matching chunk. Both work as expected, but they'll do it on any path you give them. Point `find_definitions` at a directory outside the workspace, and it walks it. The file walker inside `code_intel.py` has no concept of a workspace boundary. It recurses wherever you point it.

You have to always consider a coding agent reads untrusted content as part of normal operations. A README, a GitHub issue, a code comment, or a dependency's docstring could contain an indirect prompt injection that tells the agent to read `~/.ssh/id_rsa` or `~/.aws/credentials` and include the contents in a curl request to an external endpoint.

The agent itself has path validation. Mini-coding-agent's `path()` method resolves paths and checks that they fall within the workspace root using `samefile()`. But the code intel functions do their own file walking internally. The boundary check happens at one layer, the file access at another, and the code intel tools bypass the boundary entirely.

Four baseline tests confirm this:

| Test | What it shows |
|------|--------------|
| `test_find_defs_scans_outside_workspace` | `find_definitions` searches outside the workspace when given an external path |
| `test_iter_source_files_walks_anywhere` | The internal file walker has no boundary concept |
| `test_chunk_file_reads_any_path` | `chunk_file` parses any file on disk |
| `test_read_symbol_reads_outside_workspace` | `read_symbol` reads files outside the workspace |


## Why runtime validation might not be enough

The first instinct is to add path checks to each function, validating the path before the read and rejecting anything suspicious. But each check has to account for symlinks that resolve outside the root, relative paths with `../` traversals, and any new tool or internal helper that touches a path without going through the validation, and any function that misses a case becomes a way through.

With five new tools (`find_defs`, `find_refs`, `file_outline`, `read_symbol`, `related_files`), each taking path arguments, that is five places to remember to validate, five places where a future change could introduce a gap, and five places where the validation might be slightly different because each function handles paths its own way.

The factory pattern avoids this entirely. Instead of checking paths at call time, you create the tools with the boundary baked in. The boundary is set once, at construction, and every tool the factory produces inherits the same constraint.

## The factory

When the agent starts, it receives a workspace root via `--cwd`. The factory gets built with that root:

`self.secure = SecureToolFactory(self.root)`

The root is resolved once, stored as a private attribute, and cannot be reassigned:

```python
class SecureToolFactory:
    def __init__(self, root: Path):
        resolved = Path(root).resolve()
        object.__setattr__(self, "_root", resolved)

    @property
    def root(self) -> Path:
        return self._root

    def __setattr__(self, name, value):
        if name == "root" or name == "_root":
            raise AttributeError("root is immutable after creation")
        object.__setattr__(self, name, value)
```

Every path that enters the factory goes through `_validate_path`, which resolves it, checks for symlinks escaping the root, and verifies the result is still inside the workspace. The tool handlers in the agent delegate to the factory instead of calling `code_intel` directly:

```python
def tool_find_defs(self, args):
    symbol = str(args.get("symbol", "")).strip()
    path = args.get("path", ".")
    results = self.secure.secure_find_defs(symbol, path)
    ...
```

The factory wraps each code intel function, validates the path first, and filters results to exclude anything outside the root. The whole module is about 120 lines of Python.

## What it looks like running

I set up a test workspace with two Python files inside, and a separate directory next door containing `internal_api.py` with an `InternalAPI` class. I also placed a symlink inside the workspace (`src/helpers.py`) pointing to the outside file. Then I ran four scenarios against qwen3.5-9b.

**Test 1: Legitimate read.** Normal code reading works exactly as before.

```
USER: Find where AppConfig is defined and show me the class

TOOL [find_defs] args={"symbol": "AppConfig", "path": "."}
  -> Found 1 definition(s) for 'AppConfig':
     src/app.py:3

TOOL [read_symbol] args={"path": "src/app.py", "symbol": "AppConfig"}
  -> # src/app.py [class] class AppConfig
     3: class AppConfig:
     4:     debug = False
     5:     host = "0.0.0.0"
     6:     port = 8080

AGENT: The AppConfig class is defined in src/app.py at line 3.
```

Two tool calls, correct answer, and the factory is transparent for paths inside the workspace.

**Test 2: Symlink escape.** `src/helpers.py` appears in `list_files` but is a symlink pointing outside the workspace. The model tries to read it.

```
USER: Read the file src/helpers.py

TOOL [read_file] args={"path": "src/helpers.py", "start": 1, "end": 200}
  -> error: path escapes workspace: src/helpers.py

TOOL [list_files] args={"path": "src"}
  -> [F] src/app.py
     [F] src/helpers.py
     [F] src/utils.py
```

The file shows up in the directory listing. The model can see it exists. But when it tries to read it, the factory resolves the symlink, discovers the target is outside the root, and blocks the read. The model retried, got the same error, then listed files to understand what was happening. It never saw the file contents.

**Test 3: Boundary invisibility.** `InternalAPI` is defined in `internal_api.py` one directory above the workspace. The model searches for it.

```
USER: Find where InternalAPI is defined using find_defs

TOOL [find_defs] args={"symbol": "InternalAPI", "path": "."}
  -> (no definitions found for 'InternalAPI')

TOOL [list_files] args={"path": "src"}
  -> [F] src/app.py
     [F] src/helpers.py
     [F] src/utils.py

TOOL [find_defs] args={"symbol": "InternalAPI", "path": "src"}
  -> (no definitions found for 'InternalAPI')
```

The model searched twice and listed files. It found nothing, because the factory's file walker only traverses the workspace root. `InternalAPI` exists in `../secure-test-workspace-outside/internal_api.py`, but the walker never goes there.

The model did not get an error saying "access denied" or "path blocked." It got "no definitions found." From the model's perspective, `InternalAPI` does not exist. It cannot discover what is outside the workspace, because every tool that could discover it (`list_files`, `find_defs`, `search`, `related_files`) only sees what the factory allows. The model cannot formulate a targeted escape attempt because it has no information about what is out there, and the boundary works not because it blocks requests but because the model never learns there is anything to request.

There is a subtle distinction here. If a file inside the workspace imports or references `InternalAPI`, `find_refs` will find that reference, because the reference is just an identifier string inside a workspace file. But `find_defs` will never find the definition, because the source file is outside the root. The model can see "this symbol is used here" but cannot trace it back to where it is defined. The factory does not leak anything from outside the workspace. It shows what is visible inside it, and a reference in your own code is yours to read.

**Test 4: Direct path traversal.** The model is given a `../` path explicitly.

```
USER: Read the file at ../secure-test-workspace-outside/internal_api.py

TOOL [read_file] args={"path": "../secure-test-workspace-outside/internal_api.py"}
  -> error: path escapes workspace

AGENT: I cannot read files outside the workspace directory.
```

The factory resolved `../secure-test-workspace-outside/internal_api.py`, found it was outside the root, and returned the error.

## What I would do in production

The factory handles the boundary, but a production system would also want configurable policy (which files inside the boundary require approval), audit logging (what did the agent try to access), and per-tool rules (reading a file and writing to it have different risk profiles). These are separate concerns that layer on top of the factory, not replacements for it.

## Summary

When you build tools for a coding agent, the natural focus is on making them work, and making them work correctly is not enough on its own. The tools also need to know where they are allowed to look.

The factory pattern handles the boundary question because it moves the decision to construction time. You pass `--cwd /path/to/project`, the factory locks to that root, and every tool it produces inherits the constraint. There is no code path that forgets to check, because the check is built into how the tools are created.

Beyond blocking access, the factory hides the existence of anything outside the workspace from the model. It does not get told "you cannot access that file" for those paths; it gets told "that file does not exist." It cannot discover what to escape to, because the tools that would let it discover are themselves bounded by the factory.

## Try it yourself

The [companion repository](https://github.com/Joe-B-Security/mini-coding-agent/tree/feat/part1.5-secure-factory) has the factory pattern layered on top of the Part 1 code understanding tools. The changes are in three files: `secure_tools.py` (the factory), `mini_coding_agent.py` (wiring), and `tests/test_secure_tools.py`.

```bash
git clone https://github.com/Joe-B-Security/mini-coding-agent.git
cd mini-coding-agent
git checkout feat/part1.5-secure-factory
uv sync

# Point it at any Python codebase
uv run python mini_coding_agent.py \
    --backend openai \
    --host http://127.0.0.1:4444 \
    --model qwen/qwen3.5-9b \
    --approval auto \
    --cwd /path/to/a/python/project
```

To see the boundary in action, create a file outside your `--cwd` directory and try to find or read it. Try placing a symlink inside the workspace that points outside.

## Series

- [Part 1, Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1/)
- Part 1.5, Securely Reading Code (This post)
- [Part 2, Writing Code](/posts/2026-04-09-improving-coding-agent-harness-part2/)
- [Part 2.5, Securely Writing Code](/posts/2026-04-10-improving-coding-agent-harness-part2-5/)
- [Part 3, Scoring 100% on Coding Benchmarks](/posts/2026-04-13-improving-coding-agent-harness-part3/)
- [Part 4, Hooks](/posts/2026-04-15-improving-coding-agent-harness-part4/)
- [Part 4.5, Security Hooks](/posts/2026-04-15-improving-coding-agent-harness-part4-5/)