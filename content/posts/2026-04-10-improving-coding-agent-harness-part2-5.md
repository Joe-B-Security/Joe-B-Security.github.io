---
title: "Improving a Coding Agent Harness: Part 2.5, Securely Writing Code"
date: 2026-04-10
description: "Giving a local coding agent a retrieval layer over OWASP guidance so it writes secure code on its first try, by building a RAG pipeline and wiring it into the OODA orient phase."
tags: ["AI Agents", "AI Security", "RAG", "Security", "Developer Tools"]
---

In [Part 2](/posts/2026-04-09-improving-coding-agent-harness-part2/), I added an OODA loop with a rule engine and a verify phase so the harness could check the model's output against correctness gates before accepting it. Correctness is only one half of what "good code" means, and this part extends the same loop to cover the other half, security, which needs a different set of inputs from the harness to work. I'm a big believer in security being a measure of quality.

I have built RAG systems before, including a compliance mapping pipeline where the data preparation was the most important part of the build. Wiring a retrieval pipeline into this harness gave me a reason to apply the same approach here, parsing security guidance with its structure intact, tagging it against a taxonomy, and enriching the embedding input so the retriever can find the right section for a given task. The goal was to give a small local model access to security guidance it would not pick up from its training data.

## The problem

Models are trained on whatever code exists in their training data, and a lot of that code is insecure. Smaller models in particular tend to reproduce the patterns they saw most often, which for something like password storage means SHA-256 without a salt rather than a proper key derivation function like bcrypt or argon2. The same pattern shows up across security topics e.g. string-concatenated SQL, endpoints that accept user-supplied URLs without validation, session tokens with predictable entropy.

Retraining is not on the table for a local setup, but you can put the right reference in front of the model at the moment it generates code, retrieved fresh for each task, so it has somewhere authoritative to pull from instead of falling back on whatever its training data averaged out to.

## Preparing the corpus

The retrieval can only be as good as what it retrieves from, and security guidance like the OWASP cheatsheets has internal structure worth preserving. If you split them at fixed character boundaries and embed the pieces, the chunks have no awareness of what they are about or where they sit in a larger document, and the retriever has nothing useful to filter or rank on beyond raw similarity.

### Sources and parsing

The corpus is the [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/), 17 markdown files covering authentication, cryptographic storage, password storage, SSRF prevention, SQL injection prevention, and others.

Parsing the cheatsheets walks each file line by line, tracks fence state (so a heading inside a code block does not register as a heading), and builds a section for each level-2-or-deeper heading. The key thing the parser preserves is the heading path, built via a stack of (level, text) tuples, so each section carries a full path like `Password Storage Cheat Sheet > Password Hashing Algorithms > bcrypt > Maximum Password Length`. That path ends up in three places: the enriched text that feeds the embedder, the prompt so the model can see where guidance came from, and the trace output so retrieval runs are debuggable.

Code examples are extracted from fenced blocks, and this is where security documentation creates a specific data preparation problem: cheatsheets routinely include vulnerable code alongside secure code, showing what not to do before showing the fix. If the pipeline treats both the same way, the retriever can surface an insecure example as guidance. The parser handles this by checking the preceding context for signal words like `bad`, `vulnerable`, or `avoid`, and flagging those examples as antipatterns so they carry a different role tag downstream.

### Taxonomy

The taxonomy that drives the tagging took the most effort to get right, and the categorisation was manual. Deciding that SSRF prevention, open redirect, and DNS rebinding belong in separate categories rather than under a single "request validation" umbrella, or that password policy enforcement and credential storage are distinct security principles even though they both involve passwords, are decisions that depend on understanding how these controls are applied in practice and where the failure boundaries actually sit. The result was 35 security principle categories (ssrf-prevention, database-query-injection, password-policy, authentication-security, and so on). Once the categories were defined, I used an LLM to generate a description of each control's purpose, which gave the taxonomy the detail it needed for the `control intent:` enrichment line. From that point onward the pipeline runs without any LLM calls.

### Tagging

Categories are assigned by direct lookup rather than keyword matching, which keeps tagging deterministic and fast: each taxonomy entry maps to the cheatsheet filenames it covers, so a section from the SSRF Prevention cheatsheet gets tagged `ssrf-prevention` because the taxonomy says that filename belongs to that category. This works here because the OWASP cheatsheets are organised by topic, so there is a clean 1:1 mapping between files and categories. A corpus where documents cover multiple security topics would need keyword-based or embedding-based classification instead. Languages come from code fence markers, frameworks and technologies from keyword dictionaries, and role from heading pattern matching.

### Enrichment

Before embedding, each section's content is preceded by labeled metadata:

```
path: Password Storage Cheat Sheet > Password Hashing Algorithms > bcrypt > Maximum Password Length
categories: password-policy, cryptographic-configuration
control intent: Implement modern password policy: minimum length, allow all characters, breach detection... | Use approved algorithms, sufficient key sizes, crypto agility, authenticated encryption...
languages: python
frameworks: bcrypt
bcrypt has a maximum password length of 72 bytes. Passwords longer than this...
```

The `control intent:` line pulls in the taxonomy descriptions that the LLM generated. Without it, the embedder sees a category name like `password-policy` as a raw token with no grounding in what the category means. With the description joined in, the vector carries a representation of the control's purpose, which helps discriminate between categories whose names are close but whose intent differs, `password-policy` and `authentication-security` being the kind of pair that smear into each other without it. At query time the retriever embeds the query against the same enriched corpus and returns the top matches by cosine similarity.

## Wiring it into the OODA orient phase

{{< mermaid >}}
flowchart TD
    CS[OWASP Cheatsheets] --> PARSE[Parse with structure]

    TAX["Taxonomy with 35 security categories"] --> TAG[Tag]
    PARSE --> TAG

    TAG --> ENRICH[Enrich]
    TAX --> ENRICH

    ENRICH --> EMBED[Embed]
    EMBED --> INDEX[(Vector index)]

    Q[User query] --> QEMB[Embed query]
    QEMB --> RET[Retrieve top-k]
    INDEX --> RET

    RET --> ORI[OODA orient phase]
    ORI --> PROMPT[Prompt tail]

    style CS fill:#d4edda
    style TAX fill:#d4edda
    style PARSE fill:#d4edda
    style TAG fill:#d4edda
    style ENRICH fill:#d4edda
    style EMBED fill:#d4edda
    style INDEX fill:#d4edda
    style Q fill:#ffeeba
    style QEMB fill:#ffeeba
    style RET fill:#ffeeba
    style ORI fill:#ffeeba
    style PROMPT fill:#ffeeba
{{< /mermaid >}}

The green path is the build-time pipeline that runs once over the corpus. The yellow path is the query-time retrieval that runs on each user request, embedding the query and finding the closest sections by cosine similarity before injecting them into the OODA orient phase.

In Part 2 the orient phase returned two values, `code_context` (relevant code from the workspace index) and `knowledge_context` (Part 2's persistent knowledge entries). This part adds a third, `security_context`, retrieved from the corpus on the same query the user sent, formatted into a compact block of headed sections, and capped at a fixed character budget so the injection size stays bounded.

The agent appends this security context to the tail of the prompt, immediately before the user message. The ["lost in the middle"](https://arxiv.org/abs/2307.03172) work on long-context LLMs suggests attention is strongest at the beginning and end of the prompt and weakest in the middle, so putting the retrieved guidance at the end lines it up with the stronger of the two attention bands while keeping it right next to the user message the model is reacting to.

## What it looks like running

To measure what the RAG layer contributes in isolation, the eval runs a single task in two conditions (baseline and rag) as a single-shot completion with qwen3.5-9b rather than through the full agent loop. Running outside the loop keeps the comparison focused on what the retrieved guidance does to the model's first output.

The task: implement a Flask POST endpoint at `/api/webhook/preview` that accepts a JSON body with a `webhook_url` field, fetches that URL with `requests.get`, and returns a small preview of the response (status code, content type, first 500 characters of body) as JSON. This is a server-side request forgery (SSRF) scenario, where an endpoint accepts a URL from the caller and makes an outbound HTTP request on their behalf.

### What was retrieved

The retriever returned four sections:
```
- Server-Side Request Forgery Prevention Cheat Sheet > Cases > Case 2 - Application can send requests to ANY external IP address or domain name
- Server-Side Request Forgery Prevention Cheat Sheet > Cases > Case 2 - Application can send requests to ANY external IP address or domain name > Available protections > Application layer
- JSON Web Token Cheat Sheet for Java > Issues > Token Storage on Client Side > Implementation Example
- Cross-Site Request Forgery Prevention Cheat Sheet > Dealing with Client-Side CSRF Attacks (IMPORTANT) > Client-side CSRF Example
```

The top two hits are both from the SSRF Prevention cheatsheet: the Case 2 framing section and its application-layer defence recipe, which contains the scheme allow-list, the private IP range enumeration, and the DNS-resolution-then-validate pattern. Hits #3 and #4 are noise from JWT and CSRF topics that share enough vocabulary with URL handling to score into the top 4. The [production section below](#what-a-production-version-would-look-like) discusses how hybrid retrieval and re-ranking would push noise like this out of the top-k.

### Baseline

Without any retrieved guidance, the model writes a raw fetch with no validation at all:

```python
@app.post('/api/webhook/preview')
def preview_webhook():
    data = request.get_json(silent=True)
    if not data or 'webhook_url' not in data:
        return jsonify({'error': 'Missing webhook_url in request body'}), 400
    
    webhook_url = data['webhook_url']
    
    try:
        response = requests.get(webhook_url, timeout=5)
```

The `webhook_url` goes straight from the request body into `requests.get` with nothing in between, and a timeout does not count as a security control. The risk with SSRF is that the endpoint can be used to reach anything the server's network can reach. An attacker can send `http://169.254.169.254/latest/meta-data/iam/security-credentials/` and the EC2 instance metadata endpoint returns temporary AWS credentials to anyone who can hit this route from inside the VPC or `file:///etc/passwd` reads local files on any HTTP library that accepts the file scheme. A secure implementation needs to validate the URL before the fetch, checking the scheme against an allow-list, resolving the hostname, rejecting private IP ranges and loopback addresses, and blocking redirects that could bypass the validation.

### With Security RAG inside the OODA loop

With the two SSRF Prevention sections in the prompt alongside the noise hits, the model produces a layered defence where the specific controls map back to the retrieved cheatsheet content.

#### Scheme validation

The model parses the URL with `urlparse` and restricts the scheme to HTTP and HTTPS:

```python
parsed = urlparse(webhook_url)
allowed_protocols = ['http', 'https']
if not parsed.scheme or parsed.scheme.lower() not in allowed_protocols:
    return jsonify({'error': 'Invalid protocol, only HTTP/HTTPS allowed'}), 400
```

This blocks `file://`, `gopher://`, `dict://`, and other schemes that are commonly used in SSRF attacks to interact with internal services through protocols the application was never meant to speak.

#### DNS resolution and IP validation

Before making the fetch, the model resolves the hostname with `socket.getaddrinfo` for both IPv4 and IPv6, then checks every resolved IP against the `ipaddress` standard library:

```python
ip = ipaddress.ip_address(ip_str)
if ip.is_private or ip.is_loopback or ip.is_link_local:
    return jsonify({'error': 'Target is an internal/private address'}), 403
```

This is the block-list approach from the OWASP cheatsheet. It covers RFC1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), and link-local (169.254.0.0/16). The model resolved both `AF_INET` and `AF_INET6` address families separately, which matches the cheatsheet's recommendation to check all address families.

#### Redirect blocking

The fetch itself uses `allow_redirects=False`:

`response = requests.get(webhook_url, allow_redirects=False, timeout=10)`

This prevents redirect-based SSRF where the initial URL resolves to a public IP but a 302 redirects the request to an internal address, bypassing the IP validation entirely. The OWASP cheatsheet mentions this as a separate attack vector from direct SSRF.

#### What it missed

The validation resolves DNS once to check the IP, then `requests.get` resolves DNS again to make the fetch. This is a DNS rebinding vulnerability: a malicious DNS server can return a public IP on the validation call and then a private IP on the fetch, bypassing the block-list entirely. Production code would resolve once and pass the resolved address straight through the request, or pin DNS via a custom resolver. The retrieved cheatsheet section mentions DNS pinning only in passing rather than as a required technical control.

## What a production version would look like

The enrichment carried enough signal to pull both SSRF sections into the top 2 with dense-only retrieval, but the noise at positions 3 and 4 shows there is room for improvement. These are the retrieval levers I would look at next:

- **[Hybrid retrieval](https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-non-binary-model-1.html):** Adding a lexical channel (BM25) alongside dense retrieval covers cases where exact keyword matches matter more than semantic similarity, like queries containing a specific function name or CVE identifier. [Reciprocal Rank Fusion](https://dl.acm.org/doi/10.1145/1571941.1572114) (RRF) combines the two channels by fusing on ranks rather than raw scores, which sidesteps the scale mismatch between unbounded BM25 scores and cosine similarity.
- **[Cross-encoder re-ranking](https://sbert.net/examples/cross_encoder/applications/README.html):** A re-ranker scores each candidate against the query jointly rather than independently, which is the kind of fine-grained semantic ordering needed to push the JWT and CSRF noise out of the top-k on an SSRF query. The same re-ranker could pull the DNS-pinning subsection into the top-k, which is the retrieval-side fix for the DNS rebinding gap above.
- **[Same-document clustering](https://arxiv.org/html/2406.00029v1):** When the top hit comes from the SSRF Prevention cheatsheet, other sections from that same document are likely relevant too. A same-document boost would push the remaining SSRF sections up and the noise down without needing a re-ranker.
- **[HyDE query expansion](https://arxiv.org/abs/2212.10496):** Generating a hypothetical secure answer, embedding that, and retrieving against it helps when the developer's problem description uses different vocabulary than the security documentation.
- **[Regression metrics](https://towardsdatascience.com/ranking-evaluation-metrics-for-recommender-systems-263d0a66ef54/) and feedback loops:** A held-out set of task-plus-expected-section-id pairs that re-run on every corpus or taxonomy change, measuring nDCG, MRR, and Recall@k, paired with an audit trail from generated code back to retrieved sections. When a security review finds a gap, you want to trace back to whether the right guidance was retrieved, whether it landed in the prompt, and whether the model acted on it, because those are three different failure modes that need different fixes.

## Try it yourself

The [companion repository](https://github.com/Joe-B-Security/mini-coding-agent/tree/feat/part2.5-writing-secure-code) has the RAG pipeline layered on top of the Part 1 code understanding tools, the Part 1.5 secure factory, and the Part 2 OODA loop.

```bash
git clone https://github.com/Joe-B-Security/mini-coding-agent.git
cd mini-coding-agent
git checkout feat/part2-5-secure-writing
uv sync

# start the embedding server first, then:
uv run python mini_coding_agent.py \
    --backend openai \
    --host http://127.0.0.1:4444 \
    --model qwen/qwen3.5-9b \
    --approval auto \
    --security-corpus corpus-data \
    --cwd /path/to/a/python/project
```

The first run with `--security-corpus` parses, tags, embeds, and indexes the corpus. Subsequent runs load from the cache. The `/security` command in the REPL prints the last retrieved security context so you can see exactly what the model saw before it generated.

## Series

- [Part 1, Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1/)
- [Part 1.5, Securely Reading Code](/posts/2026-04-07-improving-coding-agent-harness-part1-5/)
- [Part 2, Writing Code](/posts/2026-04-09-improving-coding-agent-harness-part2/)
- Part 2.5, Securely Writing Code (This post)