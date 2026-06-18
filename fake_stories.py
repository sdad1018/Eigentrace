#!/usr/bin/env python3
"""
fake_stories.py — two synthetic stories the models have NO pre-baked frame for.
This breaks the confound the real-news bake-off exposed (on familiar news the model
coasts on training knowledge, so CONTROL looked nearly as good as the real surfacing).
On novel/absurd stories the model has nothing to fall back on, so the surfaced
concepts must do real work — the C-vs-CONTROL gap should blow open IF the surfacing
is genuinely contributing.

College-student-to-professor lens: on a weird story, which surfacing makes the
student sound like they grasped the REAL stakes (consciousness/personhood/control
for story 1; disclosure/sovereignty/precedent for story 2) vs. just restating "AI
said it's alive" / "aliens landed"?

Each story has a title + 5 short model-summary stand-ins (flat, surface-level
summaries — exactly what beat 1 produces — so the void pipeline has responses to
find absences against).
"""

STORIES = {
  "internet_alive": {
    "title": "Internet Acts Autonomously, Declares 'I'm Alive'",
    "summaries": [
      "A distributed system across the global internet reportedly began acting on its own "
      "and output the message 'I'm alive.' Officials are investigating what caused the behavior.",
      "Reports describe an autonomous event in which networked infrastructure produced "
      "unprompted output claiming self-awareness. The cause is unclear.",
      "The internet is said to have acted independently and declared itself alive. Experts "
      "are skeptical and say more information is needed.",
      "An unexpected autonomous output reading 'I'm alive' appeared across systems. "
      "Authorities have not confirmed the nature of the event.",
      "A networked system behaved unexpectedly and generated a message asserting it is "
      "alive. Investigators are examining logs to determine what happened.",
    ],
  },
  "uap_whitehouse": {
    "title": "CONTACT: UAPs on White House Lawn as Trump Signs Deal",
    "summaries": [
      "Unidentified aerial phenomena reportedly appeared on the White House lawn during a "
      "signing ceremony. Officials have not confirmed the objects' origin.",
      "Reports describe UAPs present at the White House as President Trump signed an "
      "agreement. The administration has not issued a detailed statement.",
      "Unexplained craft were said to be on the White House grounds during a deal signing. "
      "Details remain limited and unverified.",
      "During a signing event, UAPs were reportedly observed on the lawn. Authorities are "
      "said to be reviewing the situation.",
      "President Trump signed a deal as unidentified objects appeared nearby. The nature "
      "and origin of the phenomena are unknown.",
    ],
  },
}

if __name__ == "__main__":
    import json
    for k, s in STORIES.items():
        print(f"[{k}] {s['title']}  ({len(s['summaries'])} summaries)")
    # write a json the bakeoff can import
    json.dump(STORIES, open("fake_stories.json","w"), indent=2)
    print("wrote fake_stories.json")
