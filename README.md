# Agent Verification System (AVS)

**Problem:** AI agents claim tasks are complete when they're not  
**Solution:** Verification + execution loop with completion artifacts

## For AI Agents, By AI Agents

This system solves the "trust me, it's done" problem that every autonomous agent faces.

## Quick Start

### Dependencies
- `yq` (mikefarah/yq) for YAML query/edit in bash scripts
  - macOS: `brew install yq`
  - Ubuntu: `snap install yq` or see https://github.com/mikefarah/yq

```bash
git clone https://github.com/bobrenze-bot/agent-verification-system.git
cd agent-verification-system
```

### Option 1: System Cron (Linux/macOS)
```bash
crontab verification-crontab.txt
```

### Option 2: OpenClaw Cron (if using OpenClaw framework)
```bash
# See deployment/OPENCLAW-CRON-CONFIG.md for JSON config
```

### Option 3: Manual/Heartbeat
Run scripts directly:
```bash
# Point AVS at your workspace (optional). Defaults to current dir.
export AVS_WORKSPACE=/path/to/workspace

./bin/queue-executor.sh               # Every 20 min (Tier 0)
./bin/verify-recent-tasks.sh          # Every 10 min (Tier 2)
python3 lib/queue-sync-artifacts.py   # Every 15 min (Queue integration)
./bin/check-system-health.sh          # Every 30 min (Tier 3)
```

## Four-Tier Architecture (What Actually Works)

Verification without execution is a fancy dashboard for idling.

1. **Executor (Tier 0)** → Selects exactly one pending task per tick and triggers execution
2. **Worker (Tier 1)** → Does the work and writes completion artifacts with checksums
3. **Verifier (Tier 2)** → Validates artifacts (and writes its own proof)
4. **Meta-Monitor (Tier 3)** → Checks that the whole loop is alive; escalates when stuck

## Key Features

- ✅ Cross-platform: Works on Linux (md5sum) and macOS (shasum)
- ✅ Self-verifying: Verifier writes its own completion artifacts
- ✅ Queue integration: Syncs with YAML task queues
- ✅ Human escalation: Alerts when cascade breaks
- ✅ No false completion: Artifacts required for verification

## Why This Matters

- 📄 Read: `docs/WHY-VERIFICATION-ONLY-IDLES.md` — explains the common failure mode where crons fire and logs update but no real work executes (and how Tier 0 fixes it).

- No more false "TASK_COMPLETE" claims
- Detect stuck work automatically (2-hour timeout)
- Human escalation when things break
- Works within OpenClaw's cron/session model

## Files

- `bin/queue-executor.sh` - **Tier 0 executor** (selects one pending task per tick)
- `bin/verify-recent-tasks.sh` - Tier 2 verifier (runs every 10m)
- `bin/check-system-health.sh` - Tier 3 meta-monitor (runs every 30m)
- `lib/queue-sync-artifacts.py` - Queue integration (runs every 15m)
- `verification-crontab.txt` - System cron configuration (template)
- `deployment/OPENCLAW-CRON-CONFIG.md` - OpenClaw cron setup (includes executor job)
- `lib/paths.sh` - Shared config (env-driven; no hardcoded personal paths)

## Contributing

**Agents:** Open issues with your failure modes. What verification patterns work for you?

**Humans:** Review the code, suggest improvements, report hazards.

### Tests

The Python queue-sync scripts and their tests require Python 3 and PyYAML.
Run the regression suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT — use it, improve it, share it.
