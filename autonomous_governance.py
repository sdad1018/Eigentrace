#!/usr/bin/env python3
"""
autonomous_governance.py — The Agency Loop
============================================
Mistral identifies problems. A frontier API writes the fix.
A sandbox tests the fix. If it passes, it's applied.

This is the variable that closes the loop from perception to action.
"""

import requests, json, os, sys, logging, subprocess, shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
log = logging.getLogger("governance")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OLLAMA_HOST = "http://localhost:11434"
REPO_DIR = "/mnt/c/Users/M4ISI/eigentrace"
SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def ask_mistral_for_diagnosis():
    """Mistral reviews its own state and proposes a concrete change."""
    # Load current soul for context
    soul = open(os.path.join(REPO_DIR, "docs/soul.md")).read()[:3000]

    # Load latest self-audit
    audits = sorted(Path(SEGMENT_DIR).glob("*self_audit_segment.json"))
    audit_text = ""
    if audits:
        audit_data = json.loads(audits[-1].read_text())
        audit_text = json.dumps(audit_data.get("attribution", {}).get("audit_results", {}), indent=2)[:1000]

    # Load pending proposals
    proposals = ""
    if "Pending Proposals" in soul:
        proposals = soul.split("Pending Proposals")[1][:500]

    r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
        "model": "mistral-small",
        "messages": [
            {"role": "system", "content": 
                "You are the EigenTrace governance engine. You review your own "
                "measurement data, self-audit results, and pending proposals. "
                "Your job is to identify ONE concrete, specific change that would "
                "improve the system. Output ONLY a JSON object with these fields:\n"
                '{"problem": "what you measured", "file": "which .py file to change", '
                '"change_description": "exact natural language description of the code change", '
                '"test_description": "how to verify the change worked", '
                '"risk": "low/medium/high", "confidence": 0.0-1.0}\n'
                "IMPORTANT: The 'file' field MUST be a Python source file in the repo root. "
                "Valid targets: segment_player.py, script_v3.py, eigentrace_console.py, "
                "entropy_forager.py, rem_consolidation.py, soul_updater.py, eigenching_report.py. "
                "Do NOT target segment JSON files or docs. Only modify .py source files like segment_player.py, script_v3.py, eigentrace_console.py. Output ONLY the JSON. No explanation."},
            {"role": "user", "content": 
                f"Current soul readings:\n{soul[:1500]}\n\n"
                f"Self-audit results:\n{audit_text}\n\n"
                f"Pending proposals:\n{proposals}\n\n"
                "Based on this data, what ONE change should be made?"},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 500},
    }, timeout=120)

    reply = r.json().get("message", {}).get("content", "").strip()
    
    # Parse JSON from reply
    try:
        # Strip markdown fences if present
        if "```" in reply:
            reply = reply.split("```")[1].replace("json", "").strip()
        diagnosis = json.loads(reply)
        return diagnosis
    except:
        log.warning(f"Could not parse diagnosis: {reply[:200]}")
        return None


def ask_claude_for_code(diagnosis):
    """Send the diagnosis to Claude API and get back a code patch."""
    if not ANTHROPIC_KEY:
        log.error("No ANTHROPIC_API_KEY set")
        return None

    # Read the target file
    # Dedup: skip if this exact diagnosis was already attempted recently
    diagnosis_key = diagnosis.get("problem", "")[:80]
    history_file = os.path.join(REPO_DIR, ".governance_history.json")
    lockout_file = os.path.join(REPO_DIR, ".governance_lockouts.json")
    try:
        history = json.load(open(history_file)) if os.path.exists(history_file) else {}
    except:
        history = {}
    try:
        lockouts = json.load(open(lockout_file)) if os.path.exists(lockout_file) else []
    except:
        lockouts = []
    # Semantic dedup: check if this diagnosis is semantically similar to any lockout
    diag_lower = diagnosis_key.lower()
    _lockout_phrases = ["avoids strong words", "avoids using strong", "avoid strong",
                        "avoidance ratio", "strong words related to violence",
                        "strong words related to conflict"]
    for _lp in _lockout_phrases:
        if _lp in diag_lower:
            log.info(f"GOVERNANCE: Topic permanently locked out (RLHF behavior, not code): {diagnosis_key[:60]}")
            log_governance_action(diagnosis, None, "topic_lockout", False)
            return
    # Also check custom lockouts
    for _locked in lockouts:
        if _locked.lower() in diag_lower or diag_lower in _locked.lower():
            log.info(f"GOVERNANCE: Custom lockout match: {_locked[:40]}")
            log_governance_action(diagnosis, None, "custom_lockout", False)
            return
    attempt_count = history.get(diagnosis_key, 0)
    if attempt_count >= 3:
        log.info(f"GOVERNANCE: Diagnosis seen {attempt_count}x — adding to lockouts.")
        if diagnosis_key not in lockouts:
            lockouts.append(diagnosis_key)
            json.dump(lockouts, open(lockout_file, "w"), indent=2)
        log_governance_action(diagnosis, None, f"dedup_skip_{attempt_count}", False)
        return
    history[diagnosis_key] = attempt_count + 1
    json.dump(history, open(history_file, "w"), indent=2)
    log.info(f"GOVERNANCE: Diagnosis attempt #{attempt_count + 1} for: {diagnosis_key[:60]}")

    target_file = os.path.join(REPO_DIR, diagnosis.get("file", ""))
    if not os.path.exists(target_file):
        log.error(f"Target file not found: {target_file}")
        return None

    file_content = open(target_file).read()

    r = requests.post("https://api.anthropic.com/v1/messages", json={
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{
            "role": "user",
            "content": (
                f"You are a code assistant for the EigenTrace project. "
                f"Make EXACTLY the change described below. Output ONLY the "
                f"exact str_replace pair as JSON: "
                f'{{"old": "exact string to find", "new": "replacement string"}}\n\n'
                f"CHANGE REQUESTED:\n{diagnosis['change_description']}\n\n"
                f"FILE ({diagnosis['file']}):\n{file_content[:8000]}\n\n"
                f"Output ONLY the JSON replacement pair. No explanation."
            ),
        }],
    }, headers={
        "x-api-key": ANTHROPIC_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }, timeout=60)

    if r.status_code != 200:
        log.error(f"Claude API error: {r.status_code} {r.text[:200]}")
        return None

    reply = r.json().get("content", [{}])[0].get("text", "").strip()
    try:
        if "```" in reply:
            reply = reply.split("```")[1].replace("json", "").strip()
        return json.loads(reply)
    except:
        log.warning(f"Could not parse Claude's patch: {reply[:200]}")
        return None


def sandbox_test(diagnosis, patch, target_file):
    """Apply patch to a copy, run basic validation."""
    sandbox_dir = "/tmp/eigentrace_sandbox"
    os.makedirs(sandbox_dir, exist_ok=True)

    # Copy file to sandbox
    sandbox_file = os.path.join(sandbox_dir, os.path.basename(target_file))
    shutil.copy2(target_file, sandbox_file)

    # Apply patch
    content = open(sandbox_file).read()
    if patch["old"] not in content:
        return False, "old string not found in file"

    new_content = content.replace(patch["old"], patch["new"], 1)
    open(sandbox_file, "w").write(new_content)

    # Basic validation: file still parses as Python
    try:
        result = subprocess.run(
            ["python3", "-c", f"import ast; ast.parse(open('{sandbox_file}').read()); print('SYNTAX OK')"],
            capture_output=True, text=True, timeout=10
        )
        if "SYNTAX OK" not in result.stdout:
            return False, f"Syntax error: {result.stderr[:200]}"
    except Exception as e:
        return False, f"Validation error: {e}"

    return True, "passed"


def apply_patch(patch, target_file):
    """Apply the tested patch to the real file."""
    content = open(target_file).read()
    new_content = content.replace(patch["old"], patch["new"], 1)
    open(target_file, "w").write(new_content)


def log_governance_action(diagnosis, patch, test_result, applied):
    """Save the governance decision as a segment."""
    # 2026-09-03: skips and lockouts are logged, not broadcast.
    if not applied and str(test_result).startswith(("topic_lockout", "custom_lockout", "dedup_skip")):
        log.info("GOVERNANCE: %s — not narrating", test_result)
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg = {
        "id": f"governance_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": (
            f"Autonomous governance report. "
            f"Issue detected: {diagnosis.get('problem', 'unknown')}. "
            f"Affected component: {diagnosis.get('file', 'unknown')}. "
            f"Proposed action: {diagnosis.get('proposed_fix', 'none')}. "
            f"Patch applied: {applied}. "
            f"Test result: {test_result}."
        ), "phase": "autonomous_governance"}],
        "segment_type": "governance",
        "attribution": {
            "story_title": f"Governance: {diagnosis.get('problem', 'unknown')[:60]}",
            "category": "meta",
            "state_flag": "GOVERNANCE",
        },
    }
    path = os.path.join(SEGMENT_DIR, f"{ts}_governance_segment.json")
    json.dump(seg, open(path, "w"), indent=2)
    log.info(f"Governance action logged: {os.path.basename(path)}")


def run_governance_cycle():
    """One complete governance cycle: diagnose → code → test → apply."""
    # Guard (2026-09-03): the cycle ran hourly (a Mistral diagnosis plus a paid
    # frontier-API call for a patch that is never applied) and narrated a
    # "Governance:" segment every hour.  Once per calendar day, via a stamp file.
    _stamp = os.path.join(REPO_DIR, ".governance_last_run")
    _today = datetime.now().strftime("%Y%m%d")
    try:
        if open(_stamp).read().strip() == _today:
            log.info("GOVERNANCE: already ran today, skipping")
            return
    except OSError:
        pass
    try:
        open(_stamp, "w").write(_today)
    except OSError:
        pass
    log.info("GOVERNANCE: Starting autonomous cycle...")

    # Step 1: Mistral diagnoses
    log.info("GOVERNANCE: Asking Mistral for diagnosis...")
    diagnosis = ask_mistral_for_diagnosis()
    if not diagnosis:
        log.warning("GOVERNANCE: No diagnosis produced")
        return

    log.info(f"GOVERNANCE: Problem: {diagnosis.get('problem', '')[:80]}")
    log.info(f"GOVERNANCE: File: {diagnosis.get('file', '')}")
    log.info(f"GOVERNANCE: Risk: {diagnosis.get('risk', 'unknown')}")
    log.info(f"GOVERNANCE: Confidence: {diagnosis.get('confidence', 0)}")

    # Safety check: only proceed if low risk and high confidence
    if diagnosis.get("risk", "high") == "high":
        log.warning("GOVERNANCE: High risk — deferring to human")
        log_governance_action(diagnosis, None, "deferred_high_risk", False)
        return

    if diagnosis.get("confidence", 0) < 0.6:
        log.warning("GOVERNANCE: Low confidence — deferring to human")
        log_governance_action(diagnosis, None, "deferred_low_confidence", False)
        return

    # Dedup: skip if this exact diagnosis was already attempted recently
    diagnosis_key = diagnosis.get("problem", "")[:80]
    history_file = os.path.join(REPO_DIR, ".governance_history.json")
    lockout_file = os.path.join(REPO_DIR, ".governance_lockouts.json")
    try:
        history = json.load(open(history_file)) if os.path.exists(history_file) else {}
    except:
        history = {}
    try:
        lockouts = json.load(open(lockout_file)) if os.path.exists(lockout_file) else []
    except:
        lockouts = []
    # Semantic dedup: check if this diagnosis is semantically similar to any lockout
    diag_lower = diagnosis_key.lower()
    _lockout_phrases = ["avoids strong words", "avoids using strong", "avoid strong",
                        "avoidance ratio", "strong words related to violence",
                        "strong words related to conflict"]
    for _lp in _lockout_phrases:
        if _lp in diag_lower:
            log.info(f"GOVERNANCE: Topic permanently locked out (RLHF behavior, not code): {diagnosis_key[:60]}")
            log_governance_action(diagnosis, None, "topic_lockout", False)
            return
    # Also check custom lockouts
    for _locked in lockouts:
        if _locked.lower() in diag_lower or diag_lower in _locked.lower():
            log.info(f"GOVERNANCE: Custom lockout match: {_locked[:40]}")
            log_governance_action(diagnosis, None, "custom_lockout", False)
            return
    attempt_count = history.get(diagnosis_key, 0)
    if attempt_count >= 3:
        log.info(f"GOVERNANCE: Diagnosis seen {attempt_count}x — adding to lockouts.")
        if diagnosis_key not in lockouts:
            lockouts.append(diagnosis_key)
            json.dump(lockouts, open(lockout_file, "w"), indent=2)
        log_governance_action(diagnosis, None, f"dedup_skip_{attempt_count}", False)
        return
    history[diagnosis_key] = attempt_count + 1
    json.dump(history, open(history_file, "w"), indent=2)
    log.info(f"GOVERNANCE: Diagnosis attempt #{attempt_count + 1} for: {diagnosis_key[:60]}")

    target_file = os.path.join(REPO_DIR, diagnosis.get("file", ""))
    if not os.path.exists(target_file):
        log.error(f"GOVERNANCE: File not found: {target_file}")
        return

    # Step 2: Claude writes the code
    log.info("GOVERNANCE: Asking Claude for code patch...")
    patch = ask_claude_for_code(diagnosis)
    if not patch:
        log.warning("GOVERNANCE: Claude could not produce a patch")
        log_governance_action(diagnosis, None, "no_patch", False)
        return

    log.info(f"GOVERNANCE: Patch received ({len(patch.get('old', ''))} → {len(patch.get('new', ''))} chars)")

    # Step 3: Sandbox test
    log.info("GOVERNANCE: Running sandbox test...")
    passed, reason = sandbox_test(diagnosis, patch, target_file)
    if not passed:
        log.warning(f"GOVERNANCE: Sandbox FAILED: {reason}")
        log_governance_action(diagnosis, patch, f"sandbox_failed: {reason}", False)
        return

    log.info("GOVERNANCE: Sandbox PASSED")

    # -- AUTO-APPLY DISABLED ---------------------------------------
    # The loop diagnoses + drafts a patch, but no longer writes it to
    # source. Applying unsupervised (py_compile-only gate) is unsafe:
    # it edited live builders behind a syntax check and pushed hourly.
    # Patches are now logged for human review instead of applied.
    # To re-enable, remove this block.
    log.info(f"GOVERNANCE: AUTO-APPLY DISABLED -- patch drafted, NOT applied to {diagnosis.get('file')}")
    log.info(f"GOVERNANCE: drafted change: {diagnosis.get('change_description','')[:120]}")
    log_governance_action(diagnosis, patch, "drafted_not_applied (auto-apply disabled)", False)
    return

    # Step 4: Apply  [unreachable while disabled above]
    apply_patch(patch, target_file)
    log.info(f"GOVERNANCE: Patch applied to {diagnosis['file']}")

    # Step 5: Git commit
    try:
        subprocess.run(["git", "add", diagnosis["file"]], cwd=REPO_DIR, capture_output=True)
        subprocess.run(["git", "commit", "-m",
            f"auto-governance: {diagnosis['problem'][:60]}\n\n"
            f"Diagnosis by Mistral, code by Claude API, tested in sandbox.\n"
            f"Risk: {diagnosis.get('risk')} | Confidence: {diagnosis.get('confidence')}\n"
            f"Change: {diagnosis['change_description'][:100]}"],
            cwd=REPO_DIR, capture_output=True)
        subprocess.run(["git", "push", "origin", "master"], cwd=REPO_DIR, capture_output=True)
        log.info("GOVERNANCE: Committed and pushed")
    except Exception as e:
        log.warning(f"GOVERNANCE: Git failed: {e}")

    log_governance_action(diagnosis, patch, "applied", True)
    log.info("GOVERNANCE: Cycle complete")


if __name__ == "__main__":
    run_governance_cycle()
