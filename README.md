# Mirror

Mirror is a local Claude Code plugin that coaches how you use AI. It reads Claude Code transcript JSONL files, distills coaching-relevant observations, and stores long-lived memories with mem0 using either local Chroma or an optional Mem0 Cloud account.

The point is not shame. Mirror looks for evidence of patterns like delegation-first debugging, low observable verification, repeated orientation questions, and topic-depth regression, then nudges you toward using AI as a sparring partner.

## Architecture

### Core flow

```mermaid
flowchart TD
  subgraph cc [Claude Code]
    START["SessionStart first-run reminder"] --> ONBOARD["/mirror:onboard"]
    H["Stop/SessionEnd hook cheap enqueue"] --> Q["SQLite dirty queue"]
    CMD["/mirror commands"] --> ING
  end
  SCHED["user-controlled digest schedule"] --> ING
  COACHSCHED["optional coach insight schedule"] --> COACH
  Q --> ING
  ING["digest.py: parallel net-new JSONL diff"] --> AN["analysis.py: specialist prompts + synthesis"]
  AN -->|"observations + behavioral signals"| MEM[("mem0 adapter: Chroma local or Mem0 Cloud")]
  EXP["/mirror:import-claude-export"] --> AN
  COACH["coach.py"] -->|"temporal + multi-hop search"| MEM
  COACH --> MD["~/.claude/coaching-sessions/*.md"]
```

### Signal detection → coaching

```mermaid
flowchart LR
  subgraph detect [Transcript signals]
    P["Prompt intent"]
    T["Tool sequence patterns"]
    A["Session arc / cognition order"]
    D["Topic depth over time"]
  end
  subgraph analyze [analysis.py]
    CL["Classifiers"]
    OBS["Observations with signals"]
  end
  subgraph coach [coach.py]
    NUDGE["Socratic nudges"]
    GROW["Growth celebration"]
    GOAL["Goal accountability"]
  end
  detect --> CL --> OBS --> MEM[(mem0)]
  MEM --> coach
```

### Capture → promote → retrieve

```mermaid
flowchart LR
  subgraph capture [1 Capture]
    JSONL[TranscriptJSONL]
    SLICE[TranscriptSlice]
  end
  subgraph promote [2 Promote]
    ANALYSIS[analysis.py distill]
    OBS[Observations]
    SS[SessionSummary]
    TOP[Topics]
  end
  subgraph mem0write [mem0 add]
    FACT[factual memories]
    EPI[episodic memories]
    SEM[semantic memories]
  end
  subgraph retrieve [3 Retrieve]
    COACH[coach.py search]
    REPORT[CoachingReport]
  end
  JSONL --> SLICE --> ANALYSIS
  ANALYSIS --> OBS --> FACT
  ANALYSIS --> SS --> EPI
  ANALYSIS --> TOP --> SEM
  FACT --> COACH
  EPI --> COACH
  SEM --> COACH
  COACH --> REPORT
```

### Parallel digestion

```mermaid
flowchart TD
  HOOK["Stop/SessionEnd hook"] --> QUEUE["mirror.db dirty_sessions"]
  SCAN["Transcript scanner"] --> CANDIDATES["changed transcript candidates"]
  QUEUE --> PLAN["Build digestion plan"]
  CANDIDATES --> PLAN
  PLAN --> WORKERS["bounded parallel workers"]
  WORKERS --> PARSE["parse net-new slice"]
  PARSE --> SPECIALISTS["specialist LLM prompts"]
  SPECIALISTS --> SYNTH["synthesis + dedup"]
  SYNTH --> WRITE["memory_store.write"]
  WRITE --> STATE["watermarks + mem0 id links"]
```

### Concurrency

```mermaid
flowchart TD
  DIGEST[Digest run] --> SESSIONPOOL[Session worker pool]
  SESSIONPOOL --> SA[Session A]
  SESSIONPOOL --> SB[Session B]
  SA --> A1[Intent specialist]
  SA --> A2[Verification specialist]
  SA --> A3[Topic specialist]
  SA --> A4[Goal specialist]
  SB --> B1[Intent specialist]
  SB --> B2[Verification specialist]
  A1 --> SEM[Global LLM semaphore]
  A2 --> SEM
  A3 --> SEM
  A4 --> SEM
  B1 --> SEM
  B2 --> SEM
  SEM --> ROUTER[LLMRouter]
  ROUTER --> CLAUDE[Claude API]
  ROUTER --> OLLAMA[Ollama]
  CLAUDE --> SYNTH[Synthesis per session]
  OLLAMA --> SYNTH
  SYNTH --> WRITE[mem0 write]
```

## Install for development

```bash
python3 -m pip install --user uv
python3 -m uv sync --extra dev
```

Default local mode uses Chroma through OSS mem0. No `MEM0_API_KEY` is required unless you opt into Mem0 Cloud.

For Claude-backed analysis/coaching, persist your Anthropic API key so hooks and commands can see it:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

Ollama can be used for any specialist or coach model:

```bash
export OLLAMA_BASE_URL="http://localhost:11434"
```

## Claude Code plugin commands

- `/mirror:onboard` — first-run setup and guidance.
- `/mirror:digest` — process new/changed transcripts into Mirror memories.
- `/mirror:coach` — generate an on-demand coaching report.
- `/mirror:goals list|add|edit|remove` — manage user goals.
- `/mirror:settings` — view/edit storage mode, specialist models, schedules, and output paths.
- `/mirror:schedule` — configure optional digestion or coach insight schedules.
- `/mirror:storage` — view/change `local_chroma` vs `mem0_cloud`.
- `/mirror:status` — show queue, settings, models, and goals.
- `/mirror:import-claude-export <path>` — import a Claude.ai data export.

## Data layout

- `${CLAUDE_PLUGIN_DATA}/mirror.db` — SQLite state: queue, watermarks, settings, goals, memory links.
- `${CLAUDE_PLUGIN_DATA}/chroma` — local Chroma persistence.
- `~/.claude/projects/**/*.jsonl` — Claude Code transcripts (source evidence only).
- `~/.claude/coaching-sessions/*.md` — optional saved coaching reports.

Raw transcripts are not written to mem0. Mirror stores distilled memories:

- factual observations about AI-use patterns,
- episodic session summaries,
- semantic topic/depth signals,
- factual user goals.

## Scheduling

Scheduling is always user-controlled.

- Digestion can be manual or scheduled.
- Coach insights are default off. If enabled, they write Markdown files to `~/.claude/coaching-sessions/` and do not interrupt active Claude Code sessions.

See `scheduler/` for cron and systemd examples.

## Model configuration

Every AI component goes through `LLMRouter` and can be configured independently:

- `prompt_intent`
- `verification_assimilation`
- `topic_depth`
- `goal_alignment`
- `memory_synthesis`
- `coach`

Each can use `claude/<model>` or `ollama/<model>`.

## Testing

```bash
python3 -m uv run --extra dev pytest -q
```

If the Claude CLI is installed:

```bash
claude plugin validate .
```
