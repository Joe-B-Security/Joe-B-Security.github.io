---
title: "Improving a Coding Agent Harness: Part 1, Reading Code"
date: 2026-04-07T09:00:00
description: "What happens when you give a coding agent tree-sitter instead of grep, tested against Flask with a 9B parameter model."
tags: ["AI Security", "AI Agents", "Coding Agents"]
---

Sebastian Raschka's [article on coding agent harnesses](https://magazine.sebastianraschka.com/p/components-of-a-coding-agent) is a good reference for concepts that are easy to take for granted once you work with them daily. He breaks a coding agent into six components (live repo context, prompt shape and cache reuse, structured tools, context reduction, session memory, and delegation) and walks through each one with his [mini-coding-agent](https://github.com/rasbt/mini-coding-agent), a clean, minimal implementation in about 1,000 lines of Python.

I had some opinionated ideas about how a coding agent harness could be improved, both for quality of life and for security, and forking a clean, minimal implementation felt like the right way to test and learn whether those ideas actually made a difference.

This first part covers code reading and understanding. The base harness gives the model grep and line-range file reads, which felt limited when I watched the agent try to navigate a real codebase. I wanted to see what would happen if the harness gave the model access to the structure that a parser already knows about.

## Reading code

The test setup was a fork of mini-coding-agent running against Flask's source with qwen3.5-9b through LM Studio, with a 16k context limit as a reasonable budget for running a small model locally on a MacBook Air. The tight window makes the cost of noisy tool output more visible since every wasted token counts. The base harness gives the model three ways to read code: a directory listing, a file reader that takes line ranges, and grep, which are the same tools most coding agent harnesses ship with.

When I asked "where is the Blueprint class defined?", the model searched for `class Blueprint`, got 4 results, then read the full file to confirm. That was 2 tool calls plus a malformed output retry, consuming 4,485 characters of tool output to answer a question that has a two-line answer. With a raw search for just "Blueprint", grep returned 30 lines (clipped from 60 actual matches in Flask's source). Definitions, imports, docstrings, type hints, and test fixtures were all mixed together.

A more practical question was "I need to modify how Blueprint handles URL prefixes, help me find the relevant code." The tool trace from that session:

```
search({"pattern": "class Blueprint", "path": "."})
read_file({"path": "src/flask/blueprints.py"})
(malformed output, retry)
search({"pattern": "url_prefix", "path": "src/flask"})
read_file({"path": "src/flask/sansio/blueprints.py"})
read_file({"path": "src/flask/blueprints.py", "start": "20", "end": "60"})
read_file({"path": "src/flask/sansio/blueprints.py", "start": "70", "end": "120"})

Result: Stopped after reaching the step limit without a final answer.
```

Six tool calls, one retry, 15,894 characters of tool output consumed, and the model never got to answer the question. Every step was orientation: searching, reading, searching again, reading more. It ran out of its step budget before it could think about what it found.

The noise ratios explain why orientation is so expensive. Grep for "Flask" in Flask's source directory returns 205 lines, of which 5 are actual class definitions. Grep for "Blueprint" returns 60 lines, of which 3 are class definitions. The model receives a wall of mixed results and has to distinguish definitions from imports, docstrings, comments, and test fixtures on its own, which is work the harness could handle because the information to distinguish them already exists in the source code's syntax tree.

## What the syntax tree already knows

A Python parser knows that `class Blueprint(Scaffold):` is a class definition and that `from .blueprints import Blueprint` is an import. These are different node types in the syntax tree. Tree-sitter, which parses source code into concrete syntax trees fast enough for real-time editor use, lets you query for specific node types. A query like `(class_definition name: (identifier) @name)` matches class definitions and nothing else. No intelligence is being added here, just access to information the parser already produces.

I built a module (`code_intel.py`) that uses tree-sitter to provide three capabilities the base agent does not have.

## Symbol search: find_defs and find_refs

Grep cannot distinguish a definition from a reference from a comment. `find_defs` uses tree-sitter queries to return only lines where a symbol is defined (class definition, function definition). `find_refs` returns only references. These are separate tools because "where is this defined?" and "where is this used?" are different questions that grep conflates into one noisy result.

When I tested the same "where is Blueprint defined?" question with the enhanced agent, the model called `find_defs` and received 3 lines containing 104 characters:

```
find_defs({"symbol": "Blueprint", "path": "."})

Found 2 definitions for 'Blueprint':
  src/flask/blueprints.py:18
  src/flask/sansio/blueprints.py:119
```

One tool call, correct answer, compared to the baseline's 2 tool calls, a retry, and 4,485 characters to reach the same place, because the harness could not tell the model which of the grep results were definitions and which were noise.

## File relationships: related_files

When working on a file, the model needs to know what other files are connected to it. With only grep, this means searching for each symbol one at a time, which costs tool calls. `related_files` extracts all definitions and references from a file, checks which other files share those symbols, and returns a ranked list scored by the number of shared symbols.

When I called `related_files` on Flask's `blueprints.py`, the model received this in one tool call (1,032 characters):

```
Files related to src/flask/blueprints.py (by shared symbols):
  sansio/scaffold.py (5 shared: __init__, has_static_folder, static_folder)
  sansio/blueprints.py (4 shared: Blueprint, BlueprintSetupState, __init__)
  app.py (3 shared: __init__, get_send_file_max_age, send_static_file)
  helpers.py (3 shared: __init__, get_send_file_max_age, send_from_directory)
  sansio/app.py (3 shared: Blueprint, __init__, name)
  ...
```

The model sees which files are connected and the specific symbols they share, without spending tool calls on discovery. The approach is a simplified version of how file relationship graphs work in practice. Production implementations refine symbol overlap with git commit co-occurrence, using the frequency of files changing together as a confidence signal on the symbol-based relationships. I used only symbol overlap, which is enough to demonstrate the concept without requiring git history analysis.

## Semantic chunking: file_outline and read_symbol

The base agent reads files by line range: start=1, end=200. On a 1,625-line file like Flask's `app.py`, the model would need several reads and some luck to find the function it wants. `file_outline` parses the file with tree-sitter, walks the top-level AST nodes, and returns a structural map:

```
Structure of src/flask/app.py:
  L3-54 [imports] imports
  L73-77 [function] def _make_timedelta
  L85-92 [function] def remove_ctx
  L97-106 [function] def add_ctx
  L109-1625 [class] class Flask
```

That is 6 lines and 196 characters. The model now knows that `_make_timedelta` is at lines 73-77 and the Flask class spans lines 109-1625, without reading any of the actual code.

`read_symbol` takes a file and a name and returns the complete function or class with line numbers. When I asked for `_make_timedelta`, the tool returned:

```
# src/flask/app.py [function] def _make_timedelta
  73: @staticmethod
  74: def _make_timedelta(value: timedelta | int | None) -> timedelta | None:
  75:     if value is None or isinstance(value, timedelta):
  76:         return value
  77:     return timedelta(seconds=value)
```

The complete function in 318 characters, with correct line numbers, no guessing at ranges and no unrelated code included. This is a simplified version of semantic code chunking at AST boundaries, where files are split at syntax tree nodes rather than at arbitrary character or line limits. A full implementation would recursively split nodes that exceed a size budget and merge small adjacent siblings for information density. I just walk top-level children and identify functions, classes, and import blocks, which covers the common case of navigating to a specific definition in a file.

## End to end

All four tools together in one conversation, with the question "I want to understand the Blueprint class":

```
find_defs({"symbol": "Blueprint"})                                       ->    3 lines,   104 chars
file_outline({"path": "blueprints.py"})                                  ->    3 lines,   123 chars
read_symbol({"path": "blueprints.py", "symbol": "Blueprint"})            ->   96 lines, 4,899 chars
related_files({"path": "blueprints.py"})                                 ->   16 lines, 1,032 chars

Total: 4 tool calls, 0 retries, 6,158 chars of tool output
```

The model produced a 1,507-character answer covering definition locations, the class structure with parameter descriptions, and a list of related files with what each one does:

> **Definition Locations**
> The `Blueprint` class is defined in two places:
> 1. src/flask/blueprints.py:18, the public API (inherits from SansioBlueprint)
> 2. src/flask/sansio/blueprints.py:119, the internal sansio implementation
>
> **Blueprint Class Structure (src/flask/blueprints.py)**
> The `Blueprint` class wraps a `SansioBlueprint` and provides the public Flask API with these key parameters: name, import_name, static_folder, static_url_path, template_folder, url_prefix, subdomain, url_defaults, root_path, cli_group.
>
> **Key Related Files**
> - src/flask/sansio/blueprints.py, core implementation
> - src/flask/app.py, uses Blueprint to register routes
> - src/flask/wrappers.py, contains `blueprints` attribute
> - tests/test_blueprints.py, test coverage

The baseline agent with only grep was asked to find how Blueprint handles URL prefixes and consumed its entire 6-step budget on orientation without producing an answer. The enhanced agent handled a broader question in 4 tool calls and had enough context to explain the class structure, its parameters, and its relationships to other files.

| | Baseline (grep) | Enhanced (tree-sitter) |
|---|---|---|
| "Where is Blueprint defined?" | 2 calls + 1 retry, 4,485 chars output | 1 call, 104 chars output |
| Understanding the Blueprint class | 6 calls + 1 retry, no answer produced | 4 calls, 1,507-char answer with full context |

## What a production version would look like

The prototype parses files from scratch on every call, which is fine for a small project but would not scale. A production version would build an indexed symbol table once and update it incrementally on file changes, and the file relationship graph could be persisted and updated through filesystem watchers rather than recomputed each time. Adding git commit co-occurrence as a confidence signal for file relationships would catch connections that symbol overlap alone misses, like configuration files that are always changed alongside the code they configure.

Language support beyond Python is straightforward since tree-sitter grammars exist for dozens of languages, and each one needs a set of definition and reference queries.

The model was already asking the right questions, it wanted to know where Blueprint was defined, what files were connected to it, what was inside app.py. The harness gave it tools that could answer those questions using information the parser already had, instead of returning grep output and hoping the model could sort through it.

## Try it yourself

The [companion repository](https://github.com/Joe-B-Security/mini-coding-agent/tree/feat/part1-code-understanding) is a fork of mini-coding-agent with the code understanding tools added. The changes are in two files: `code_intel.py` (the tree-sitter module) and `mini_coding_agent.py` (the tool wiring).

```bash
git clone https://github.com/Joe-B-Security/mini-coding-agent.git
cd mini-coding-agent
git checkout feat/part1-code-understanding
uv sync

# Point it at any Python codebase with an OpenAI-compatible endpoint
uv run python mini_coding_agent.py \
    --backend openai \
    --host http://127.0.0.1:4444 \
    --model qwen/qwen3.5-9b \
    --approval auto \
    --cwd /path/to/a/python/project
```

## Series

- Part 1, Reading Code (This post)
- [Part 1.5, Securely Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1-5/)
- [Part 2, Writing Code](/posts/2026-04-09-improving-coding-agent-harness-part2/)
- [Part 2.5, Securely Writing Code](/posts/2026-04-10-improving-coding-agent-harness-part2-5/)
- [Part 3, Scoring 100% on Coding Benchmarks](/posts/2026-04-13-improving-coding-agent-harness-part3/)
- [Part 4, Hooks](/posts/2026-04-15-improving-coding-agent-harness-part4/)
- [Part 4.5, Security Hooks](/posts/2026-04-15-improving-coding-agent-harness-part4-5/)
- [Part 5, Sandboxing](/posts/2026-04-28-improving-coding-agent-harness-part5/)
- [Part 5.5, Secrets Sandboxing](/posts/2026-05-02-improving-coding-agent-harness-part5-5/)