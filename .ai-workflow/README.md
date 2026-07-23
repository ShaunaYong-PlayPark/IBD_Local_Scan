# .ai-workflow

This folder is the local handoff layer between Shanks, Codex, and Alan.

Roles:
- Shanks = user-facing orchestrator
- Codex = technical supervisor
- Alan = coder
- User = decision-maker, not dispatcher

Hard rules:
- User talks to Shanks.
- Shanks handles back office.
- User does not relay prompts between agents.
- User does not inspect code, diffs, test logs, terminal output, or technical reports.
- No deploy, delete, push, spend, external send, or irreversible action without user approval.
- Proof required before saying work is done.

Git rule:
- Each project must be Git-backed before Codex handoff.
- If the folder is not a Git repo, stop and ask to initialize Git first.
- Commit clean baseline before real work.

Codex worktree rule:
- Codex may use a separate worktree.
- Worktree result is not enough.
- Final proof must be checked from the real local project folder.
- Use Git status and Git diff from the real project folder as proof.

Evidence rule:
- Do not trust another agent summary alone.
- Verify actual files.
- Verify exact files changed.
- Verify no forbidden files changed.
