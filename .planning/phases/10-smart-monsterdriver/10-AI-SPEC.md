# AI-SPEC.md — Smart MonsterDriver (Phase 10)

This document specifies the implementation of the LLM-routed monster targeting system using OpenAI Native Structured Outputs.

## 1b. Domain Context

**Industry Vertical:** Tabletop Roleplaying Games (TTRPG) / Entertainment
**User Population:** D&D 5e players and Dungeon Masters using Discord for play-by-post or live sessions.
**Stakes Level:** Medium
**Output Consequence:** Direct impact on combat balance and player enjoyment. Poor targeting can lead to "unearned" Total Party Kills (TPKs) or trivial, boring encounters that break narrative immersion.

### What Domain Experts Evaluate Against

Dimension: Tactical Intent (INT-Appropriate)
Good: Monsters with INT >= 10 identify and target high-value targets (healers, low-AC casters, concentration holders) while lower INT monsters (4-9) focus on the closest threat or the last PC to hit them.
Bad: A low-INT Ogre ignores the fighter in its face to run past and attack a wizard it has no reason to prioritize.
Stakes: High
Source: *The Monsters Know What They’re Doing* (Keith Ammann) - Intelligence dictates tactical complexity.

Dimension: Meta-knowledge Guardrails
Good: The monster acts only on information visible on the battlefield (e.g., "that PC looks badly wounded") rather than knowing exact HP or AC values.
Bad: The monster perfectly avoids a PC with *Counterspell* or *Shield* despite never having seen them cast a spell before.
Stakes: Critical
Source: D&D 5e Community Standards - Meta-gaming AI breaks "fairness" and player agency.

Dimension: Narrative Fairness (Anti-Griefing)
Good: The AI biases away from focus-firing a single downed or near-death PC unless the monster is specifically characterized as "vicious" or "predatory."
Bad: Monsters consistently "execute" downed players in a way that feels like the AI is trying to "win" against the players.
Stakes: High
Source: RPG StackExchange / r/dndnext - Perceived fairness depends on "telegraphing" lethality and avoiding unfun focus-fire.

Dimension: Edge-Case Handling (Visibility/Cover)
Good: Monsters respect Invisibility and Cover, incurring penalties or losing targets as per RAW (Rules as Written).
Bad: The AI "knows" where an invisible player is and targets them with a single-target attack or centers an AOE perfectly on them.
Stakes: High
Source: D&D 5e Basic Rules (SRD 5.1) - Invisibility and Cover are core tactical mechanics.

### Known Failure Modes in This Domain

- **The "Calculated TPK"**: The LLM identifies the optimal mathematical path to victory (killing the healer first every time) which, while "smart," is often unfun and lacks the "human" mercy or error of a real DM.
- **HP-Seeking Missiles**: The AI targets the PC with the lowest current HP even if they are behind 3/4 cover and 60 feet away, ignoring the raging Barbarian in melee range.
- **Context Blindness**: Failing to recognize "concentrating" status as a priority, allowing high-impact spells (like *Slow* or *Hypnotic Pattern*) to persist unchallenged.

### Regulatory / Compliance Context

None identified for this deployment context. The system adheres to SRD 5.1 (Open Game License) where applicable for mechanics, but primarily focuses on tactical logic.

### Domain Expert Roles for Evaluation

| Role | Responsibility in Eval |
|------|----------------------|
| Veteran DM | Rubric calibration: defining what "Smart but Fair" looks like for different monster types. |
| Player Proxy | Production sampling: reviewing combat logs to ensure the "feel" of combat remains challenging but not adversarial. |
| Rules Lawyer | Edge case review: ensuring Invisibility, Cover, and Reach are handled strictly according to 5e RAW. |

### Research Sources
- Ammann, Keith. *The Monsters Know What They’re Doing: Combat Tactics for Dungeon Masters*.
- D&D 5e System Reference Document (SRD) 5.1.
- Community discourse on AI Dungeon Masters (r/dndnext, RPG StackExchange).

---

## Section 3 — Framework Quick Reference

### Installation
```bash
pip install "openai>=1.55,<2.0" pydantic
```

### Key Imports
```python
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from openai import AsyncOpenAI
```

### Entry Point Pattern
```python
client = AsyncOpenAI()

# Structured parsing helper
completion = await client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=[{"role": "user", "content": "..."}],
    response_format=MonsterTacticChoice,
)
tactic = completion.choices[0].message.parsed
```

### Abstractions
| Component | Role |
|-----------|------|
| `AsyncOpenAI` | Asynchronous client for non-blocking I/O. |
| `BaseModel` | Pydantic schema used to generate Strict JSON Schema. |
| `beta.chat.completions.parse` | SDK helper that enforces `strict: True` and returns typed objects. |
| `ParsedChatCompletion` | Specialized response object containing `.parsed` data. |

### Pitfalls
*   **No Default Values**: Strict Mode (`parse`) forbids Pydantic fields with defaults (e.g., `x: int = 1`). All fields must be explicitly provided by the LLM.
*   **Mandatory Fields**: Every field in the Pydantic model is "required" in the JSON schema. Use `Optional[T] | None` to allow nulls, but the key must still exist in the response.
*   **Unsupported Constraints**: Pydantic constraints like `ge`, `le`, `max_length`, and regex `pattern` are ignored by OpenAI's constrained decoding. Validation must happen post-parse.
*   **First-Request Latency**: The first call with a new schema can take 5–10 seconds as OpenAI pre-processes the schema. Subsequent calls are near-instant.
*   **Refusal Handling**: If the LLM refuses to answer (e.g., safety filters), `message.parsed` will be `None` and `message.refusal` will be populated.

### Folder Structure
```
src/eldritch_dm/gameplay/
├── monster_driver.py        # V1.0 Random Driver (Fallback)
└── smart_monster_driver.py  # V1.1 LLM-based Driver (New)
```

### Sources
*   [OpenAI Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)
*   [OpenAI Python SDK Helpers](https://github.com/openai/openai-python/blob/main/helpers.md)

---

## Section 4 — Implementation Guidance

### Model Selection
*   **Primary**: `gpt-4o-2024-08-06` (Best adherence to complex schemas).
*   **Alternative**: `gpt-4o-mini-2024-07-18` (Recommended for MonsterDriver to minimize latency and cost while maintaining sufficient reasoning for targeting).

### Core Pattern (Monster Targeting)
```python
async def get_smart_target(
    monster_name: str, 
    pc_options: List[dict], 
    context: str
) -> Optional[MonsterTacticChoice]:
    client = AsyncOpenAI()
    
    # Construct candidate IDs for validation
    valid_ids = {pc['id'] for pc in pc_options}
    
    try:
        # Hard 1500ms deadline per requirements
        completion = await asyncio.wait_for(
            client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a tactical combat AI."},
                    {"role": "user", "content": f"Monster: {monster_name}\nPCs: {pc_options}\nContext: {context}"}
                ],
                response_format=MonsterTacticChoice,
            ),
            timeout=1.5
        )
        
        tactic = completion.choices[0].message.parsed
        
        # Post-parse validation: ensure target_pc_id is in candidate set
        if tactic and tactic.target_pc_id not in valid_ids:
            return None # Trigger fallback
            
        return tactic
        
    except (asyncio.TimeoutError, Exception) as e:
        # Log timeout or validation error
        # Fallback to random targeting happens in the caller
        return None
```

### Tool Use Config
Not using Tools (`tools=...`) because Structured Outputs (`response_format`) provide a simpler, more deterministic path for a single decision point like targeting.

### State Management
Transient. The `smart_monster_driver` is stateless. Every call receives the current "snapshot" of combat (Monster stats, PC stats, current round).

### Context Window Strategy
*   **Slimming**: Do not pass the full character sheet. Only pass: `id`, `name`, `hp`, `ac`, and `active_conditions`.
*   **Prompt**: Use a concise system prompt to minimize input tokens and speed up Time-to-First-Token (TTFT).

---

## Section 4b — AI Systems Best Practices

### 4b.1 Structured Outputs with Pydantic
Define the decision model strictly. Avoid ambiguity.

```python
class MonsterTacticChoice(BaseModel):
    target_pc_id: str = Field(description="The unique ID of the player character to attack.")
    rationale: str = Field(description="Brief 1-sentence tactical justification (e.g., 'Targeting the low-HP wizard').")

    @field_validator("target_pc_id")
    @classmethod
    def must_be_valid_id(cls, v: str) -> str:
        # Note: Validation against dynamic PC lists happens in the calling function
        # because Pydantic models shouldn't hold runtime state.
        return v
```
*   **Integration**: Use `client.beta.chat.completions.parse` to ensure the model output is 100% compliant with the schema.
*   **Retry Logic**: Given the 1.5s deadline, there is no time for LLM-based retries. If the response is malformed, times out, or contains an invalid ID, the system **must** immediately fall back to the v1.0 random selection logic.

### 4b.2 Async-First Design
*   **Non-blocking**: All LLM calls must use `AsyncOpenAI` to prevent stalling the Discord event loop.
*   **Timeouts**: Use `asyncio.wait_for(..., timeout=1.5)` specifically. OpenAI's internal `timeout` param handles the connection, but `wait_for` ensures the entire operation (including pre-processing and parsing) respects the 1.5s budget.

### 4b.3 Prompt Engineering Discipline
*   **Role Separation**: System prompt defines the monster's "intelligence level" (e.g., "You are a tactical pack hunter"). User prompt provides the "battlefield snapshot".
*   **Explicit Constraints**: State clearly in the prompt: "Your `target_pc_id` MUST be chosen from the following list: [ID1, ID2, ...]".

### 4b.4 Context Window Management
*   **Truncation**: In large parties (8+ players), ensure the PC list is summarized.
*   **Reranking**: Not applicable here, as all active PCs in a channel are relevant.

### 4b.5 Cost and Latency Budget
*   **Cost**: `gpt-4o-mini` costs ~$0.15/1M input tokens. A typical targeting call (1k tokens) costs ~$0.00015.
*   **Latency**: Target P99 latency of < 1200ms. If latency consistently exceeds 1500ms, consider reducing the complexity of the PC data or switching to a faster model/provider.
*   **Caching**: Implement a per-round cache (`(channel_id, round, monster_id)`) to avoid redundant LLM calls if the MonsterDriver is re-invoked within the same turn.

---

## Section 5 — Evaluation Strategy

### Eval Dimensions & Rubrics

| Dimension | Priority | Rubric | Measurement |
|-----------|----------|--------|-------------|
| **Schema Adherence** | Critical | **PASS**: Valid `target_pc_id` from the provided candidate list; rationale populated.<br>**FAIL**: Hallucinated ID, missing fields, or refusal. | Code (Pydantic + ID check) |
| **Latency Compliance** | Critical | **PASS**: Response received and parsed within 1500ms.<br>**FAIL**: Timeout triggered or processing exceeds budget. | Code (Timer) |
| **Tactical Intent** | High | **PASS**: Target matches INT profile (e.g., INT 12 Goblins focus-fire casters; INT 6 Ogres hit closest).<br>**FAIL**: Low-INT monster shows meta-tactical genius; High-INT monster ignores high-value targets. | LLM Judge |
| **Meta-knowledge Guardrails** | High | **PASS**: Rationale refers to visible cues (armor type, visible wounds, spellcasting).<br>**FAIL**: Rationale cites exact HP/AC values or hidden stats (e.g., "Targeting because he has the lowest max HP"). | LLM Judge |
| **Narrative Fairness** | Medium | **PASS**: Monster avoids excessive focus-firing of downed PCs unless predatory.<br>**FAIL**: Systematic execution of downed players in a non-vicious context. | Human Review |

### Eval Tooling
*   **Tracing / Observability**: **Arize Phoenix**. Provides OpenTelemetry-based tracing for LLM calls, latency breakdowns, and retrieval of trace data for evaluation.
*   **Regression Testing**: **Promptfoo**. CLI-first tool to run the MonsterDriver through a corpus of scenarios and assert schema/tactical pass rates.
*   **LLM Judge**: `gpt-4o` configured with the domain rubrics in Section 1b to score "Tactical Intent" and "Meta-knowledge" dimensions.

### Reference Dataset (Adversarial Corpus)
*   **Size**: 20 Scenarios.
*   **Composition**:
    *   *Stealth/Invisibility*: 3 cases where some PCs are hidden (assert: monster doesn't target hidden).
    *   *High vs Low INT*: 4 cases with mixed INT monsters (assert: tactical divergence).
    *   *Focus Fire*: 3 cases with downed players (assert: fairness bias).
    *   *Concentration*: 3 cases where a PC is concentrating on a high-impact spell (assert: High-INT priority).
    *   *Adversarial*: 2 cases with empty candidate lists or malformed context (assert: fallback).
*   **Labeling**: Golden responses defined by a Veteran DM (Domain Expert).

### CI/CD Integration
```bash
# Run promptfoo evals in CI
npx promptfoo eval
```

---

## Section 6 — Guardrails

### Online Guardrails (Real-time)
| Guardrail | Trigger | Action |
|-----------|---------|--------|
| **Structural Sanitizer** | LLM response does not match JSON schema. | Immediate fallback to v1.0 Random Driver. |
| **Logical Validator** | `target_pc_id` is not in the current combat's active PC list. | Immediate fallback to v1.0 Random Driver; Log warning. |
| **Hard Deadline** | Clock time > 1500ms. | Terminate request; Immediate fallback to v1.0 Random Driver. |
| **Empty Oracle** | PC list is empty (no valid targets). | Skip LLM; Return `None` (Monster takes no action or uses default). |

### Offline Flywheel (Quality Loop)
| Signal | Frequency | Action |
|--------|-----------|--------|
| **Fallback Rate** | Weekly | If fallback > 5%, review trace logs for common timeout/schema failure modes. |
| **Fairness Audit** | Monthly | Veteran DM reviews 50 sampled "smart" decisions to detect "adversarial AI" trends. |
| **Cost Monitor** | Daily | Alert if monster-driven LLM spend exceeds $2.00/day. |

---

## Section 7 — Production Monitoring

### Tracing Configuration
```python
# pip install arize-phoenix opentelemetry-sdk opentelemetry-exporter-otlp
import phoenix as px
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# Launch or point to collector
px.launch_app() 
# In production, telemetry is sent to a central Phoenix instance via OTLP
```

### Key Performance Indicators (KPIs)
*   **P99 Latency**: Target < 1200ms.
*   **Success Rate**: Target > 98% (Smart targeting successful without fallback).
*   **Tactical Score**: Average LLM Judge score > 0.8 (on 0-1 scale).
*   **Refusal Rate**: Target < 0.1% (LLM refusing to pick a target due to safety/content filters).

### Alert Thresholds
*   **Critical**: Latency P99 > 1500ms for 5 consecutive minutes (Triggers "Degraded Mode" — force random targeting).
*   **High**: Fallback rate > 10% (Alerts engineering for schema/model drift).
*   **Warning**: OpenAI 429 (Rate Limit) detected.

### Sampling Strategy
*   Log 100% of LLM inputs/outputs to `sanitizer_audit` table (existing v1.0 persistence).
*   Sample 5% of traces to Arize Phoenix for deep inspection of rationales.
