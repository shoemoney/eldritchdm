<!-- GSD:project-start source:PROJECT.md -->
## Project

**EldritchDM**

EldritchDM is a local-first, self-hostable Discord bot that runs full D&D 5e games end-to-end with an AI Dungeon Master persona called **ShoeGPT**. It splits the DM job across three brains — a local quantized MoE LLM (MLX) for narration, a Python rules engine for math/state, and a `discord.py` orchestrator for real-time UI — so the AI can never hallucinate HP, miscalculate AC, or break turn order. It's for tabletop players who want a "forever DM" available on demand without paying for hosted AI or surrendering the rule integrity that makes 5e actually feel like 5e.

**Core Value:** **Mechanically honest AI DM.** Narration is evocative, but every die roll, HP change, AC check, and turn boundary is enforced by deterministic Python code — the LLM never touches the math.

### Constraints

- **Runtime:** Python 3.11+
- **Platform:** macOS Apple Silicon primary target (Linux/CUDA secondary if not in conflict)
- **Inference backend:** `oMLX (`omlx serve`)` exposing OpenAI-compatible API at `http://localhost:8765/v1` (model id `ShoeGPT`, Gemma 4 4-bit quantized under the hood). Tool calls are reliable on this combo — confirmed by user. Structured-output fallback parser remains as a defensive safety net but native `tool_calls` is the primary path.
- **Discord library:** `discord.py` v2.3.2+ (Views, Modals, Select Menus required)
- **Database:** SQLite3 with WAL journaling — no external DB server
- **Rules source:** Open5e REST API (`https://api.open5e.com/`) with local fallback cache
- **OCR:** EasyOCR (English, GPU/Metal where available)
- **PDF:** pypdf
- **Performance:** Character ingest <6s; narration responses <150 words; Discord interaction acks within 3s; rate-limit-aware embed updates
- **Reliability:** Full resume across bot restarts (room, turn order, HP, memory, views rebuilt from DB)
- **Integrity rule:** The LLM is forbidden from computing math; all numerical effects originate in Python and are passed *to* the LLM as facts to narrate
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR
## Recommended Stack
### Core Technologies
| Technology | Version (pinned) | Purpose | Why | Confidence |
|---|---|---|---|---|
| Python | `>=3.11,<3.13` | Runtime | 3.11 for `TaskGroup`, `tomllib`, faster CPython; 3.13 deferred until ML wheels stabilize | HIGH |
| `discord.py` | `==2.7.1` | Discord bot framework | Rapptz resumed active dev; 2.7.1 shipped 2026-03-03; Views/Modals/Selects mature. Forks (py-cord/nextcord) no longer warranted | HIGH |
| `mlx-lm` | `==0.31.3` | Local LLM inference + server | Ships `mlx_lm.server` with OpenAI-compatible `/v1/chat/completions`. Native Apple Silicon, 4-bit quant support | HIGH |
| `openai` (client only) | `>=1.55,<2.0` | OpenAI-compatible API client | Talk to `mlx-lm.server` via `OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")`. Standardized, well-supported | HIGH |
| SQLite (stdlib `sqlite3`) | Python 3.11 bundled (3.45+) | Persistence | WAL mode enables concurrent channel writes; zero ops; local-first | HIGH |
| `aiosqlite` | `>=0.20,<0.22` | Async SQLite wrapper | Keeps event loop unblocked; serializes writes through one thread (which is what you want with WAL anyway) | HIGH |
### Supporting Libraries (missing from PRD)
| Library | Version | Purpose | When to Use |
|---|---|---|---|
| `httpx` | `>=0.27,<0.29` | Async HTTP client | Open5e API calls, any non-OpenAI HTTP. Used by OpenAI/Anthropic SDKs themselves. Don't mix `aiohttp` in unless you hit extreme concurrency (you won't — this is one bot) |
| `pydantic` | `>=2.8,<3.0` | Schema validation | Validate LLM JSON output (character ingest, tool calls), Open5e response shapes, config files. v2 Rust core is 5–50x v1 |
| `tenacity` | `>=8.5,<10.0` | Retry/backoff | Open5e API resilience, LLM call retries on timeout/malformed JSON. Use `@retry` decorators on network boundaries |
| `structlog` | `>=24.4,<26.0` | Structured logging | JSON logs with bound context (session_id, channel_id, player_id). Stdlib `logging` is fine for one-off scripts; structlog is a force multiplier when debugging a stateful game across restarts |
| `python-dotenv` | `>=1.0,<2.0` | Config | `.env` for `DISCORD_TOKEN`, `MLX_BASE_URL`. Self-hosters expect it |
| `ocrmac` | `>=1.0,<2.0` | **Primary OCR (macOS)** | Apple Vision via PyObjC. Zero model download, faster than EasyOCR on printed text. macOS 10.15+ only |
| `easyocr` | `>=1.7,<2.0` | **Fallback OCR (cross-platform)** | Linux/CUDA users. Conditional install via extras: `pip install 'eldritchdm[linux]'` |
| `pymupdf` | `>=1.24,<2.0` | PDF text + render | Faster and more accurate than pypdf for printed character sheets; also rasterizes pages for OCR fallback. **License caveat:** AGPL — fine for a self-hostable open project; flag if relicensing later |
| `pypdf` | `>=4.3,<6.0` | PDF fallback | Pure-Python, no native deps, MIT-license. Keep as a fallback if AGPL becomes a problem |
| `Pillow` | `>=10.4,<12.0` | Image manipulation | Pre-OCR resize/contrast for character sheet PNGs. Transitive dep of EasyOCR anyway |
### Development Tools
| Tool | Purpose | Notes |
|---|---|---|
| `ruff` | Lint + format | Replaces black/isort/flake8. Set `target-version = "py311"`, enable `E,F,I,B,UP,SIM` |
| `mypy` or `pyright` | Type check | Pyright is faster and the discord.py types are upstream — prefer pyright |
| `pytest` + `pytest-asyncio` | Test runner | Async tests for the three test suites named in the PRD |
| `pytest-vcr` or `respx` | Mock HTTP | Record Open5e responses; `respx` integrates cleanly with `httpx` |
| `uv` | Package manager | 10–100x faster than pip; `uv pip install -r requirements.txt` works as drop-in. Optional but recommended for self-hosters |
## PRD Decision Audit
### Confirmed
- **discord.py 2.3.2+** → bump floor to `2.7.1`. Same maintainer (Rapptz), library is active again as of late 2025/early 2026. **HIGH confidence.**
- **SQLite + WAL** → correct. Single-writer is fine because aiosqlite serializes anyway, and WAL allows concurrent readers (your embed refreshes). **HIGH confidence.**
- **Qwen MoE 4-bit** → correct. `Qwen3.5-35B-A3B` (or 3.6) is the right tier — MoE keeps tok/s high while sitting in ~20 GB. **HIGH confidence.**
- **`mlx-lm.server` at `localhost:8080/v1`** → correct, OpenAI-compatible endpoint exists in `mlx-lm >= 0.20`. Default port is indeed 8080. **HIGH confidence.**
- **Open5e API** → correct, no good alternative for open SRD content. **HIGH confidence.**
### Pushback
#### 1. "MLX over Ollama" — rationale is stale (MEDIUM-pushback)
- One fewer daemon to install/document/configure for self-hosters
- No model registry abstraction — you load a HF Hub repo path directly
- Ollama still wraps in Go, adding marginal overhead at the HTTP layer
- Tighter control over MLX kwargs (quantization, sampling, KV cache)
- Easier model swapping for non-technical self-hosters
- Better Linux story if you ever expand off Apple Silicon
- Mature concurrent-request handling (mlx-lm.server is single-request-ish)
#### 2. "EasyOCR for character sheets" — wrong default on macOS (HIGH-pushback)
- Requires PyTorch (~2 GB install) — painful for self-hosters
- Downloads ~64 MB of model weights on first run
- Slower than Apple's Vision framework on the exact hardware you're targeting
- Doesn't use the Neural Engine
#### 3. "pypdf" — fine, but PyMuPDF is materially better (LOW-pushback)
## Installation
# Core (self-hosters run this)
# macOS-only OCR (primary)
# Linux/CUDA OCR fallback (extras)
# Dev
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| `discord.py` 2.7.1 | `py-cord` / `nextcord` | Only if discord.py upstream pauses again. Currently no reason to switch in 2026 |
| `mlx-lm.server` | Ollama 0.19+ with MLX backend | Self-hoster wants a one-command model registry; willing to run a daemon |
| `mlx-lm.server` | LM Studio | Non-technical self-hoster who wants a GUI for model management |
| `mlx-lm.server` | `mlx-omni-server` / Rapid-MLX | Want tool-calling support that vanilla mlx-lm.server lacks. Re-evaluate if your MCP tool-registry needs structured tool-calls |
| `ocrmac` | PaddleOCR | Cross-platform deployment, accuracy on noisy scans matters more than install simplicity |
| `httpx` | `aiohttp` | Sustained >300 concurrent connections (irrelevant here) |
| `aiosqlite` | `sqlmodel` / SQLAlchemy async | Schemas get complex enough to want an ORM. Probably not for this scope |
| `tenacity` | `backoff` | No real reason; tenacity is the standard |
| PyMuPDF | `pdfplumber` | You need *table* extraction specifically (D&D sheets do have stat tables — possible reason to add it later) |
## What NOT to Use
| Avoid | Why | Use Instead |
|---|---|---|
| `requests` | Synchronous; blocks the event loop in a bot | `httpx` async client |
| `aiohttp` | Heavier API, async-only, no HTTP/2; overkill for one bot | `httpx` |
| `sqlalchemy` (sync) | Sync ORM in an async bot is a footgun | `aiosqlite` raw, or `sqlalchemy[asyncio]` if you really need an ORM |
| `discord-py-slash-command` | Deprecated since discord.py absorbed app commands | Use discord.py's built-in app commands |
| `nextcord` / `py-cord` | Forks made sense in 2022; discord.py is active again | `discord.py` 2.7.1 |
| `tesseract` / `pytesseract` | Outdated quality vs modern OCR; binary install pain | `ocrmac` (macOS) or `paddleocr` (Linux) |
| `langchain` | Heavyweight, churny API; you have a hand-rolled three-brain architecture already | Direct `openai` client calls with `pydantic` schemas |
| `pydantic-ai` / `instructor` | Tempting for structured LLM output, but couples you to a framework's prompt patterns. The PRD's "MCP-style tool registry" already implies a hand-rolled approach | Plain `pydantic` models + `openai` client + JSON schema in the system prompt |
| `logging` (stdlib) bare | No structure; unusable when debugging multi-session state | `structlog` JSON renderer to stdout |
| `asyncio.sleep` for rate limit | discord.py has its own rate limiter; don't reinvent | Trust `discord.py`'s `HTTPClient` and use `tenacity` only for *upstream* APIs (Open5e, MLX) |
## Version Compatibility Notes
| Constraint | Detail |
|---|---|
| `mlx-lm` | Requires macOS 13.5+ and Apple Silicon. Will not install on Intel Mac or Linux |
| `ocrmac` | macOS 10.15+; uses PyObjC. Linux self-hosters MUST install `easyocr` extras |
| `discord.py 2.7.x` | Requires Python 3.9+; we require 3.11+ anyway |
| `pydantic v2` | Incompatible with v1 patterns — do not copy/paste old `@validator` decorators |
| `PyMuPDF` | AGPL — fine for an open-source self-hosted bot; flag if anyone ever wants to fork-and-close |
| `mlx-lm.server` | Single-request friendly. If you ever serve multiple Discord guilds from one bot at >1 req/s sustained, switch to `mlx-omni-server` or Ollama 0.19+ |
## Stack Patterns by Variant
- Model: `Qwen3.5-35B-A3B-MLX-4bit` (or 3.6 when stable)
- OCR: `ocrmac`
- Expect: ~90 tok/s, ~6s character ingest
- Model: `Qwen3.5-7B-MLX-4bit` or `Qwen3.5-4B-MLX-4bit`
- OCR: `ocrmac`
- Expect: lower-quality narration but mechanically equivalent (the rules engine is the actual DM)
- Inference: Ollama 0.19+ (no MLX, falls back to llama.cpp/CUDA) at `localhost:11434/v1`
- OCR: `easyocr` (the `linux-ocr` extra)
- Acknowledge: this is best-effort, not the primary supported config
## Confidence Assessment
| Choice | Confidence | Verified Via |
|---|---|---|
| discord.py 2.7.1 | HIGH | PyPI page fetched 2026-05-21 |
| mlx-lm 0.31.3 | HIGH | PyPI page fetched 2026-05-21 |
| Qwen3.5/3.6-35B-A3B MLX 4-bit | HIGH | mlx-community HF org + 2026 benchmarks |
| openai client for MLX server | HIGH | Multiple 2026 tutorials + mlx-lm docs |
| ocrmac over EasyOCR | HIGH | ocrmac repo + Vision framework docs + 2026 OCR comparisons |
| PyMuPDF over pypdf | MEDIUM-HIGH | 2026 PDF library benchmarks; AGPL caveat noted |
| Ollama 0.19+MLX as defensible alternative | MEDIUM | Multiple 2026 blog/benchmark posts (not yet in Context7-grade sources) |
| Supporting lib selections (httpx/pydantic/tenacity/structlog) | HIGH | Mainstream 2026 Python production stack consensus |
## Sources
- [discord.py on PyPI](https://pypi.org/project/discord.py/) — version 2.7.1 verified, released 2026-03-03
- [mlx-lm on PyPI](https://pypi.org/project/mlx-lm/) — version 0.31.3 verified, released 2026-04-22
- [Ollama MLX backend announcement](https://ollama.com/blog/mlx) — confirms 2026 backend shift
- [MLX vs Ollama benchmarks 2026 (willitrunai)](https://willitrunai.com/blog/mlx-vs-ollama-apple-silicon-benchmarks) — quantifies the gap collapse
- [Ollama 0.19 MLX review (andrew.ooo)](https://andrew.ooo/posts/ollama-mlx-apple-silicon-review/) — 2x speedup numbers
- [unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit on HF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit) — current 4-bit MoE quant
- [mlx-community/Qwen3.5-4B-MLX-4bit on HF](https://huggingface.co/mlx-community/Qwen3.5-4B-MLX-4bit) — fallback small model
- [Qwen 3.5 MLX guide (willitrunai)](https://willitrunai.com/blog/qwen-3-5-mlx-apple-silicon-guide) — memory + tok/s
- [Qwen 3.6 35B-A3B local guide (codersera)](https://codersera.com/blog/how-to-run-qwen-3-6-locally-2026/) — sizing
- [ocrmac on PyPI](https://pypi.org/project/ocrmac/) — Apple Vision Python wrapper
- [Apple Vision via PyObjC tutorial (yasoob.me)](https://yasoob.me/posts/how-to-use-vision-framework-via-pyobjc/) — implementation reference
- [Best open-source OCR 2026 (unstract)](https://unstract.com/blog/best-opensource-ocr-tools/) — landscape
- [PaddleOCR vs EasyOCR vs Tesseract benchmark](https://tildalice.io/ocr-tesseract-easyocr-paddleocr-benchmark/) — speed comparison
- [MLX-LM server + OpenAI client tutorial (Medium/Levtcheva)](https://medium.com/@levchevajoana/a-job-postings-tool-a-guide-to-mlx-lm-server-and-tool-use-with-the-openai-client-edb9a5d75b4c) — confirms `base_url` pattern
- [Serving local LLMs with MLX (kconner)](https://kconner.com/2025/02/17/running-local-llms-with-mlx.html) — mlx-lm.server intro
- [HTTPX vs Requests vs AIOHTTP (decodo)](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp) — async client comparison 2026
- [aiosqlite repo](https://github.com/omnilib/aiosqlite) — asyncio bridge details
- [Pydantic v2 production guide (devtoolbox)](https://devtoolbox.dedyn.io/blog/pydantic-complete-guide) — v2 perf notes
- [PyMuPDF vs pypdf comparison (nutrient.io)](https://www.nutrient.io/blog/best-python-pdf-libraries/) — PDF library landscape 2026
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
