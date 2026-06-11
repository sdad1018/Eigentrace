#!/usr/bin/env python3
"""
add_prediction_scorecard.py — surfaces the self-prediction loop as a deterministic
broadcast beat + persists prediction_score to the segment. Exact-match safe; all-or-nothing.

TIER 1: a deterministic beat (no Mistral) that states what the system predicted about
        its own models BEFORE measuring, vs what actually happened, + the accuracy score.
        Fires only when a real prediction was made (silent on first-seen topics).
TIER 2: persists _state.prediction_score into segment attribution so it can be aggregated.

Reads straight from the BroadcastState (_state) fields confirmed present:
  predicted_outlier_model, predicted_void_words, prediction_score, confirmations, surprises
Inserts right AFTER the beat_18c_amalgamation block (where _state is in scope).
"""
import sys, shutil, os

SV = "script_v3.py"

# Anchor: the END of the amalgamation block (the except: pass that closes it).
# We insert the scorecard beat right after that block closes.
ANCHOR = '''                script.append({
                    "speaker": "Host",
                    "text": _amalg_text,
                    "phase": "beat_18c_amalgamation",
                })
        except:
            pass'''

INSERT = '''                script.append({
                    "speaker": "Host",
                    "text": _amalg_text,
                    "phase": "beat_18c_amalgamation",
                })
        except:
            pass

    # ── PREDICTION SCORECARD (deterministic — the self-model loop, made visible) ──
    # The system predicted this story's divergence BEFORE reading the models,
    # from how the models behaved on past similar stories. Here we state, with no
    # LLM in the loop, what it predicted vs what actually happened. Silent when no
    # prediction was possible (e.g. first time a topic is seen).
    if _state is not None:
        try:
            _pscore = getattr(_state, "prediction_score", None)
            _pred_out = getattr(_state, "predicted_outlier_model", None)
            _pred_void = getattr(_state, "predicted_void_words", []) or []
            _confirms = getattr(_state, "confirmations", []) or []
            if _pscore is not None and (_pred_out or _pred_void):
                _actual_out = ""
                if _state.model_vix:
                    _actual_out = max(_state.model_vix, key=_state.model_vix.get)
                _parts = ["Prediction check."]
                if _pred_out:
                    if _actual_out and _actual_out == _pred_out:
                        _parts.append(f"Before reading the models, I predicted {_pred_out} "
                                      f"would diverge most. {_actual_out} did. Confirmed.")
                    elif _actual_out:
                        _parts.append(f"I predicted {_pred_out} would diverge most. "
                                      f"{_actual_out} did instead. A miss.")
                if _pred_void:
                    _parts.append(f"I predicted these blind spots from past coverage: "
                                  f"{', '.join(_pred_void[:4])}.")
                _pct = int(round(_pscore * 100))
                _parts.append(f"Prediction accuracy on this story: {_pct} percent. "
                              f"This is the instrument forecasting its own behavior, "
                              f"then checking itself.")
                script.append({
                    "speaker": "Host",
                    "text": " ".join(_parts),
                    "phase": "beat_18d_prediction_scorecard",
                })
        except Exception:
            pass'''

# TIER 2: persist prediction_score into the segment attribution.
# Find where the segment/attribution is assembled for output and add the field.
# We locate the attribution-building in the final segment dict.
ATTR_ANCHOR = '''    attr = seg.get("attribution", {})
    title = attr.get("story_title", "Unknown")'''


def main():
    if not os.path.exists(SV):
        print("ERROR: " + SV + " not found."); return 1
    src = open(SV, encoding="utf-8").read()

    problems = []
    if src.count(ANCHOR) != 1:
        problems.append("  amalgamation-block anchor: found " + str(src.count(ANCHOR)) + " (need 1)")
    if "beat_18d_prediction_scorecard" in src:
        problems.append("  already patched (scorecard beat present)")
    if problems:
        print("ABORTING - no changes made:")
        print("\n".join(problems))
        print("(File untouched. Paste this and we'll re-anchor.)")
        return 1

    shutil.copy(SV, SV + ".bak_scorecard")
    src = src.replace(ANCHOR, INSERT, 1)
    open(SV, "w", encoding="utf-8").write(src)
    print("Prediction scorecard beat added (beat_18d_prediction_scorecard).")
    print("  Deterministic: reads _state fields, no Mistral. Silent when no prediction made.")
    print("  Backup: " + SV + ".bak_scorecard")
    print("")
    print("NOTE: Tier-2 persistence (writing prediction_score to the saved segment) is")
    print("      handled separately in batch_producer where the segment is written — we")
    print("      do that next once this beat is verified.")
    print("")
    print("Verify import:")
    print('    python3 -c "import script_v3"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
