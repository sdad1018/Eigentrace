#!/usr/bin/env python3
"""
shared_residual_experiment.py — STANDALONE. Tests whether CONVERGENT myths share a
coherent direction in embedding space MORE than UNRELATED folktales do.

This is the RIGHT instrument for the 'cross-cultural residue' question (the per-myth
donut from Stage 1 only found textual-genre vocab). Here we ask: do the convergent
universals (flood, world-tree, cosmic-giant, chaoskampf, sky/plasma) point along a
COMMON axis that unrelated folktales (animal/moral tales) do NOT?

SAFETY: read-only imports (embedder, VocabTensor). Writes only ./shared_residual_results.json.
No API calls (source embeddings only). No broadcast state touched.

METHOD:
  1. Embed each text (source, frozen bge-large).
  2. Shared direction TWO ways: (a) centroid, (b) PC1. Check they agree.
  3. Coherence metric = fraction of variance explained by PC1 (tight = shared direction).
  4. Compare convergent vs control coherence.
  5. PERMUTATION TEST: shuffle group labels, recompute coherence gap, 1000x.
     Real gap must exceed shuffles to claim the convergent set is specially coherent.
  6. Surface vocab words nearest each group's shared direction (what they point at).

HONEST: a coherent shared axis is a GEOMETRIC fact about how these texts sit in a
web-trained space. It is NOT evidence of a shared historical referent. Even a positive
result means 'these myths occupy a tighter common region than random folktales' —
which could be shared narrative structure, shared archetype, shared human psychology,
OR shared diffusion. The test cannot distinguish those.
"""
import sys, os, json
import numpy as np

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO); os.chdir(REPO)

# ============ CONVERGENT UNIVERSALS (share cross-cultural cosmic motif) ============
# Public-domain quotations where marked; others are neutral condensed paraphrases.
CONVERGENT = {
"flood_genesis": # KJV public domain
 "And God saw that the wickedness of man was great. I will destroy man whom I have created "
 "from the face of the earth. Make thee an ark of gopher wood; I will bring a flood of waters "
 "upon the earth, to destroy all flesh. And the rain was upon the earth forty days and forty "
 "nights, and the waters prevailed, and all the high hills under the whole heaven were covered.",
"flood_gilgamesh": # paraphrase of the Utnapishtim flood
 "The gods resolved to send a great flood to destroy mankind. Utnapishtim was told to tear down "
 "his house and build a boat, and take aboard the seed of all living things. For six days and "
 "nights the storm and flood swept the land, until all humanity had turned to clay. The boat "
 "came to rest on a mountain, and a dove was sent forth to find dry land.",
"world_tree_yggdrasil": # paraphrase of Norse cosmic tree
 "There stands an ash tree called Yggdrasil, the greatest and best of all trees. Its branches "
 "spread over all the world and reach above heaven. Three roots support it: one among the gods, "
 "one among the frost giants, one over the realm of the dead. An eagle sits in its branches and "
 "a serpent gnaws its roots; the tree joins the heavens, the earth, and the underworld.",
"cosmic_giant_ymir": # paraphrase of Ymir/Purusha sacrificed-creator
 "In the beginning was the giant Ymir, born of the meeting of fire and ice. From his slain body "
 "the gods fashioned the world: from his flesh the earth, from his blood the seas, from his bones "
 "the mountains, from his skull the dome of the sky, and from his brains the clouds. The whole "
 "ordered world was made from the body of the primordial being.",
"chaoskampf_marduk": # paraphrase of Marduk-Tiamat / Indra-Vritra
 "The young god went out to battle the ancient dragon of the primeval waters, the embodiment of "
 "chaos. With storm winds and a great weapon he slew the monster, and split its body in two. From "
 "one half he made the vault of the sky, from the other the earth and the deep. So order was "
 "established out of chaos, and the younger gods triumphed over the older powers.",
"squatterman_plasma": # neutral paraphrase of Peratt hypothesis
 "Across rock art on every continent appears a recurring figure flanked by circles, the squatting "
 "man. A plasma physicist proposed it records an intense auroral event in prehistory: a column of "
 "plasma develops doughnut-like rings bent by magnetic fields, resembling the carved form. If the "
 "solar wind had increased greatly millennia ago, a great discharge would have hung in the sky, "
 "witnessed by distant cultures who each carved what they saw overhead.",
"fire_from_sky_phaethon": # paraphrase of Phaethon / sky-fire catastrophe
 "Phaethon begged to drive the chariot of the sun across the heavens. But he could not control "
 "the horses, and the blazing chariot plunged near the earth, scorching the land, drying the "
 "rivers, and setting the world aflame. To save creation, the sky-god struck him down with a "
 "thunderbolt, and he fell flaming from the heavens into the river.",
}

# ============ UNRELATED CONTROL (folktales, NO cosmic/flood/sky motif) ============
CONTROL = {
"jataka_monkey_croc": # paraphrase of Jataka
 "A monkey lived in a tree by the river and ate its fruit. A crocodile wished to eat the monkey's "
 "heart, and offered to carry him across the water on his back. Midstream the crocodile revealed "
 "his plan. The clever monkey said his heart was left hanging in the tree, and asked to go back "
 "for it. The foolish crocodile turned around, and the monkey leapt to safety in the branches.",
"aesop_lion_mouse": # paraphrase of Aesop
 "A lion caught a mouse who ran across his paws, but let him go. Later the lion was caught in a "
 "hunter's net and roared in anguish. The little mouse heard him, came, and gnawed through the "
 "ropes until the lion was free. The mouse reminded the lion that even the small may help the "
 "great, and that a kindness is never wasted.",
"aesop_north_wind_sun": # paraphrase of Aesop
 "The north wind and the sun argued over which was stronger, and agreed to test their power on a "
 "traveller's cloak. The wind blew hard, but the colder it blew the tighter the man wrapped his "
 "cloak. Then the sun shone warmly, and soon the traveller took off his cloak of his own accord. "
 "Gentleness and warmth had done what force could not.",
"jataka_turtle_talk": # paraphrase of Jataka
 "A turtle could not stop talking. Two geese offered to carry him to their mountain home, holding "
 "a stick in their beaks for him to bite. They warned him to keep his mouth shut. As they flew "
 "over a town, people pointed and laughed, and the turtle opened his mouth to answer them. He let "
 "go of the stick, fell to the ground, and that was the end of the talkative turtle.",
"grimm_broken_pot": # paraphrase of the daydreamer-with-pot folktale
 "A poor girl carried a pot of milk on her head to market, and as she walked she dreamed. With "
 "the milk she would buy eggs, the eggs would hatch chickens, the chickens she would sell for a "
 "fine dress, and in the dress she would toss her head proudly at the dance. As she tossed her "
 "head at the thought, the pot fell and broke, and all the milk was spilled.",
"jataka_ox_forfeit": # paraphrase of Jataka
 "An ox was raised with kindness by a poor man, and grew very strong. To repay his master, the ox "
 "offered to pull a hundred loaded carts to win a wager. But at the contest the master shouted at "
 "him harshly, and the ox, hurt, would not pull. The master realized his fault, spoke gently, and "
 "the ox pulled all hundred carts and won the forfeit. Harsh words break the willing heart.",
"anansi_cleverness": # paraphrase of an Anansi trickster tale (no cosmology)
 "Anansi the spider wanted all the wisdom in the world, and gathered it into a great pot to keep "
 "for himself. He tried to climb a tall tree to hide the pot at the top, clutching it against his "
 "belly, but he could not climb. His young son suggested he tie the pot on his back instead. "
 "Angry that the child was wiser, Anansi let the pot fall, and wisdom scattered across the world.",
}

def coherence(embs):
    """Fraction of variance explained by PC1 = how tightly texts share one direction."""
    X = embs - embs.mean(0)
    # SVD for PCA
    U,S,Vt = np.linalg.svd(X, full_matrices=False)
    var = S**2
    pc1_frac = float(var[0]/var.sum())
    pc1_dir = Vt[0]
    centroid_dir = embs.mean(0); centroid_dir /= (np.linalg.norm(centroid_dir)+1e-8)
    # agreement between centroid direction and PC1
    agree = abs(float(centroid_dir @ (pc1_dir/np.linalg.norm(pc1_dir))))
    return pc1_frac, pc1_dir, centroid_dir, agree

def main():
    print("=== Shared-Residual Experiment (convergent myths vs unrelated folktales) ===\n")
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    ge = get_engine()
    def embed(texts): return np.array(ge.embed_texts(texts))
    vt = VocabTensor("vocab")

    conv_keys=list(CONVERGENT); ctrl_keys=list(CONTROL)
    conv_emb = embed([CONVERGENT[k] for k in conv_keys])
    ctrl_emb = embed([CONTROL[k] for k in ctrl_keys])
    conv_emb = conv_emb/ (np.linalg.norm(conv_emb,axis=1,keepdims=True)+1e-8)
    ctrl_emb = ctrl_emb/ (np.linalg.norm(ctrl_emb,axis=1,keepdims=True)+1e-8)

    print(f"Convergent set: {len(conv_keys)} texts | Control set: {len(ctrl_keys)} texts\n")

    cpc, cdir, ccen, cagree = coherence(conv_emb)
    kpc, kdir, kcen, kagree = coherence(ctrl_emb)

    print("=== COHERENCE (PC1 variance fraction — higher = tighter shared direction) ===")
    print(f"  Convergent myths : PC1={cpc:.4f}   (centroid/PC1 agreement={cagree:.3f})")
    print(f"  Control folktales: PC1={kpc:.4f}   (centroid/PC1 agreement={kagree:.3f})")
    print(f"  Gap (convergent - control): {cpc-kpc:+.4f}")
    print(f"  -> {'convergent set shares a TIGHTER common direction' if cpc>kpc else 'control is as/more coherent — no special convergent structure'}")

    # PERMUTATION TEST
    print("\n=== PERMUTATION TEST (is the gap beyond chance?) ===")
    allemb = np.vstack([conv_emb, ctrl_emb]); nC=len(conv_keys)
    rng=np.random.default_rng(0); gaps=[]
    for _ in range(2000):
        idx=rng.permutation(len(allemb))
        g = coherence(allemb[idx[:nC]])[0] - coherence(allemb[idx[nC:]])[0]
        gaps.append(g)
    gaps=np.array(gaps); real=cpc-kpc
    p=float(np.mean(gaps>=real))  # one-sided: convergent MORE coherent
    print(f"  real gap={real:+.4f} | null gap mean={gaps.mean():+.4f} std={gaps.std():.4f}")
    print(f"  p(convergent more coherent by chance)={p:.4f}")
    print(f"  -> {'SIGNAL: convergent myths share structure beyond chance' if p<0.05 and real>0 else 'NO SIGNAL: shared structure is within chance (the residue is not special)'}")

    # what does each shared direction POINT AT? (vocab nearest the centroid direction)
    print("\n=== what the shared directions point at (nearest vocab words) ===")
    conv_words = vt.nearest_concepts(ccen, k=15)
    ctrl_words = vt.nearest_concepts(kcen, k=15)
    print(f"  CONVERGENT shared direction -> {', '.join(w for w,_ in conv_words)}")
    print(f"  CONTROL shared direction    -> {', '.join(w for w,_ in ctrl_words)}")

    json.dump({
        "convergent_pc1":cpc,"control_pc1":kpc,"gap":cpc-kpc,
        "convergent_centroid_agreement":cagree,"control_centroid_agreement":kagree,
        "permutation_p":p,"null_gap_mean":float(gaps.mean()),
        "convergent_words":[w for w,_ in conv_words],"control_words":[w for w,_ in ctrl_words],
    }, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"shared_residual_results.json"),"w"), indent=2)
    print("\nSaved: shared_residual_results.json")
    print("\nHONEST: even a positive result = 'these myths occupy a tighter common region")
    print("than random folktales' — could be shared narrative structure, archetype, psychology,")
    print("or diffusion. The geometry cannot tell you WHICH, and says nothing about literal history.")
    return 0
if __name__=="__main__": sys.exit(main())
