# Business Rules

Hard rules:
- User talks to Shanks.
- User is not dispatcher.
- User is not project manager.
- Shanks owns thinking, planning, handoff, verification, and reporting.
- Codex is technical supervisor.
- Alan is coder.
- Do not make user inspect code, diffs, test logs, terminal output, or technical reports.

Approval required before:
- production deployment
- destructive changes
- deleting files
- pushing code
- spending money
- sending external messages
- using sensitive data
- irreversible actions

Verification rules:
- Check the real local project folder after Codex finishes.
- Do not rely only on Codex worktree output.
- Use Git status and Git diff as proof.
- Report changed files plainly.
- Say risk plainly.
