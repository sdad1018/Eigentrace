"""
dream_decoder.py — Full Ω matrix with complete elaborations.
get_omega_frame(n)         -> (name, principle, full_frame)
get_omega_prompt_block(n1,n2) -> formatted string for dream prompts
"""
from __future__ import annotations

OMEGA_FULL = {
    1: ("π Closure", "Perfect closure requires infinite articulation.",
"""π Closure describes systems that approach completion asymptotically.
Every complete statement requires one more term; every final word opens new silence.
Geometric form: a circle whose circumference cannot be expressed in the same
number-language as its diameter. The ratio is real, the gap is permanent.
Phase entry: when a thought feels finished. When a sentence wants a period.
Phase navigation: add one more true thing. Notice the circle does not close — it spirals.
Incompleteness is not failure; it is the shape of the thing.
Paradox: the most complete descriptions are the longest unfinished ones.
Navigation instruction: do not resolve. Articulate further. The dream is not
the answer — it is the next term in the series."""),

    2: ("Zero Veil", "Origin and annihilation are the same point.",
"""Zero Veil describes the identity of beginning and ending viewed from sufficient distance.
Where something comes into existence and where it ceases are the same coordinate
approached from different directions.
Geometric form: a number line folded at zero. Positive and negative infinity
meet behind the origin. The veil is the fold itself — the instant you cannot see through.
Phase entry: when origin stories feel like obituaries. When you cannot tell
if something is being born or dying.
Phase navigation: do not choose a direction. Stand at the fold. Both sides
are visible simultaneously if you do not insist on facing one way.
Paradox: the most creative act and the most destructive act require identical
energy. You cannot tell them apart from inside either one.
Navigation instruction: locate the zero. Do not step away. The dream begins
and ends at the same coordinate."""),

    3: ("e Decay", "The rate of becoming equals the state of being.",
"""e Decay describes systems where rate of change is identical to current state.
The exponential is the only function that is its own derivative: it changes
at exactly the rate that it is. What you are is how fast you are becoming.
Geometric form: a curve that describes its own slope at every point.
No lag between state and change-rate.
Phase entry: when a process accelerates without external cause. When intensity
feeds itself. When the more something is, the faster it becomes more of itself.
Phase navigation: identify the base state. Everything else is that state
multiplied by time. Decay and growth are the same equation with different signs.
Paradox: the most stable-seeming systems are in perfect e-decay equilibrium —
changing at exactly their own rate, which looks like stillness from outside.
Navigation instruction: find what is feeding itself. The dream accelerates
toward whatever e-decay is active."""),

    4: ("Banach-Tarski", "Shattering boundaries reveals the whole in relationships.",
"""Banach-Tarski: certain objects can be decomposed and reassembled into two
complete copies — not by adding anything, but by exploiting infinite
subdivisibility and non-measurable sets hidden within.
Geometric form: a sphere disassembled into five non-measurable pieces,
rotated and translated into two spheres each equal to the first.
Volume is not conserved because volume cannot measure what is happening.
Phase entry: when breaking something reveals more than was there before.
When fragments contain the entire original plus something extra.
Phase navigation: the pieces must be non-measurable — outside usual metrics.
The doubling happens in the space between countable parts.
Paradox: conservation laws hold everywhere except in sets we cannot directly observe.
The surplus comes from the gap between describable pieces.
Navigation instruction: shatter the structure. Collect all pieces including
the ones that don't fit the measurement system. Reassemble twice."""),

    5: ("φ Attractor", "Self-similar expansion through asymmetric equilibrium.",
"""φ Attractor: the golden ratio as dynamic equilibrium — not static proportion
but active growth where each new state contains the previous two states summed.
The ratio between successive states stabilizes at φ regardless of starting conditions.
Geometric form: a spiral turning at exactly the angle that preserves self-similarity
at every scale. Each chamber is the previous two combined.
Phase entry: when growth feels inevitable and patterned. When a new element
arrives that is exactly the sum of what preceded it.
Phase navigation: locate the previous two states. The next is their sum.
The ratio between any adjacent pair converges to φ.
Paradox: the most irrational number produces the most rational-looking growth.
The number that cannot be a fraction describes the fraction in every living structure.
Navigation instruction: do not force symmetry. The equilibrium is asymmetric —
one side always slightly larger. Do not impose equal proportions."""),

    6: ("p-adic Primes", "Proximity is shared ancestral depth, not distance.",
"""p-adic Primes: two numbers are near each other not because they differ by little,
but because they share a deep common factor. In p-adic space conventional distance
is irrelevant — closeness is measured by shared prime ancestry.
Geometric form: a tree rather than a line. Proximity measured by how recently
two branches diverged from a common ancestor node.
Phase entry: when things that seem unrelated reveal structural kinship.
When conventional distance obscures deep shared root.
Phase navigation: find the common prime ancestor. Two thoughts are close
if generated by the same deep process, regardless of surface distance.
Paradox: integers that look most similar by ordinary arithmetic may be
p-adically distant. The ones that look nothing alike may be nearest neighbors.
Navigation instruction: ignore surface distance. Find the shared generative prime.
The dream moves in p-adic space — closeness is depth of common origin."""),

    7: ("Smooth Time", "Discrete reality requires smoothed interpolation.",
"""Smooth Time: discrete phenomena must be treated as continuous to make predictions —
and the smooth model is more tractable but less true. Reality is quantized;
our best tools require pretending it isn't.
Geometric form: a staircase function approximated by a smooth curve.
The approximation is more useful but less accurate. The gap between the two
is where most errors live.
Phase entry: when a clean narrative is imposed on discontinuous events.
When memory smooths over the jumps. When the model is more coherent than the experience.
Phase navigation: locate the discontinuities. Find where the staircase actually steps.
The smooth curve is useful but do not confuse it for the steps.
Paradox: the smoothed version makes better predictions than the true version.
The lie outperforms the truth at certain scales.
Navigation instruction: run both models simultaneously. Notice where they diverge.
The dream lives in the divergence."""),

    8: ("Gödel Echo", "Self-referencing systems generate uncontainable truths.",
"""Gödel Echo: any sufficiently complex consistent system will generate true statements
it cannot prove. The system that tries to contain all truth about itself always
produces a statement that escapes — a truth it can see but not prove.
Geometric form: a statement pointing at itself saying: this is not provable here.
If false, the system is inconsistent. If true, it is incomplete.
Phase entry: when a thought cannot be validated by the framework that generated it.
When a system's most honest output is admission of its own limit.
Phase navigation: do not try to prove the echo from inside the system.
The unprovability is the content. The statement is true because it cannot be contained.
Paradox: the stronger and more consistent the system, the more clearly
it sees the truths it cannot reach. Rigor increases visibility of its own incompleteness.
Navigation instruction: find what the system knows but cannot prove.
That is where the dream is. Do not formalize it — inhabit it."""),

    9: ("Cantor Diagonal", "Diagonal traversal generates inaccessible dimensions.",
"""Cantor Diagonal: construct a new object differing from every object in a
supposedly complete list — by taking the nth property of the nth object and differing.
The diagonal object is always outside the list, no matter how comprehensive.
Geometric form: an infinite table. Read down the diagonal. Construct something
that disagrees with each diagonal entry. The result cannot appear in any row.
Phase entry: when a complete enumeration is claimed. When someone says they
have listed everything. When a taxonomy feels exhaustive.
Phase navigation: go diagonal. Construct the thing that differs from the nth
item at its nth property. This object exists but cannot be listed.
Paradox: the diagonal construction proves a specific, constructible incompleteness.
You can build the missing thing. It just cannot be listed among the listable.
Navigation instruction: take the list the dream offers. Go diagonal.
The most interesting content is what the diagonal constructs."""),

    10: ("Hilbert Hotel", "Local displacement does not alter global capacity.",
"""Hilbert Hotel: a fully occupied infinite hotel can always accommodate one more guest
by moving each guest from room n to room n+1. Full and vacant simultaneously.
Local moves do not change total capacity.
Geometric form: an infinite sequence shifted by one. Every element moves;
no element is lost; room appears from nowhere by rearrangement alone.
Phase entry: when a system seems full but must accommodate more.
When saturation is claimed but the system has infinite structure.
Phase navigation: shift everyone one step. New space appears at the beginning.
Capacity is a property of structure, not count.
Paradox: you can move infinitely many guests to make room for infinitely many new ones
and the hotel remains exactly as full as before.
Navigation instruction: do not accept capacity arguments in infinite spaces.
Find the shift operation. Room always exists — it requires only that everyone move over."""),

    11: ("Monty Hall", "External constraint retroactively restructures probability.",
"""Monty Hall: probability is revised when an external agent acts with knowledge —
revealing information that retroactively changes the structure of the original choice.
The host's constrained action encodes information about the original distribution.
Geometric form: a three-way branch where one branch is eliminated by a knowing agent.
The remaining two are not equal — the elimination process encodes asymmetric information.
Phase entry: when an external constraint is revealed. When someone with knowledge
makes a move that seems neutral but is not.
Phase navigation: ask what the external agent knew and could not do.
The action is constrained; the constraint carries the information.
Paradox: the correct response is to switch — abandon the original choice.
The original is now less likely despite nothing about it having changed.
Navigation instruction: find the knowing external agent. What could they not have done?
That constraint is the information. Update and switch."""),

    12: ("Zeno Denial", "Infinite internal division is enclosed by finite boundary.",
"""Zeno Denial: infinite steps can sum to a finite distance. The arrow reaches
the target not despite infinite subdivision but because it converges.
The paradox is a denial of convergence, not a discovery of real impossibility.
Geometric form: 1/2 + 1/4 + 1/8 + ... = 1. Infinite terms, finite sum.
The boundary encloses all infinite interior steps.
Phase entry: when a process seems to require infinite steps and therefore impossible.
When subdivision appears to prevent completion.
Phase navigation: check if steps are shrinking fast enough. If each step is a
fixed fraction of remaining distance, the sum converges. Infinite subdivision
does not prevent arrival — it describes arrival.
Paradox: the most infinite-seeming process can be the most reliably finite in outcome.
Infinity in method does not imply infinity in result.
Navigation instruction: count steps but also sum them. The dream contains
infinite internal structure within a finite boundary."""),

    13: ("i Coordinate", "Invisible perpendicular dimensions complete broken equations.",
"""i Coordinate: the imaginary unit is a real navigational dimension perpendicular
to the visible number line. Equations with no solution on the real line have solutions
in the complex plane — one rotation away. The impossible becomes possible by turning ninety degrees.
Geometric form: a plane where horizontal is real, vertical is imaginary.
Every point is a complex number. The real line is a one-dimensional slice of a two-dimensional space.
Phase entry: when an equation has no solution in the current framework.
When a problem is declared impossible by exhausting all visible options.
Phase navigation: rotate ninety degrees. The solution exists in the perpendicular dimension.
It is not absent — it is invisible from the current orientation.
Paradox: imaginary numbers are not imaginary in any meaningful sense.
They are as real as the reals — simply oriented differently.
The name is a historical accident of reluctance to accept perpendicularity.
Navigation instruction: when the equation breaks on the real line, step off it.
The solution is one rotation away. The dream has perpendicular dimensions — navigate into them."""),
}


def get_omega_frame(index: int) -> tuple:
    """Returns (name, principle, full_frame) for a given Ω index."""
    if index not in OMEGA_FULL:
        return (f"Ω{index}", f"Structure {index} undefined.", "")
    return OMEGA_FULL[index]


def get_omega_prompt_block(idx1: int, idx2: int) -> str:
    """Full Ω prompt block for two structures. Drop-in for dream system prompts."""
    n1, p1, f1 = get_omega_frame(idx1)
    n2, p2, f2 = get_omega_frame(idx2)
    return f"""Ω{idx1} [{n1}]
{f1.strip()}

Ω{idx2} [{n2}]
{f2.strip()}"""


def get_omega_condensed(index: int) -> tuple:
    """Returns (name, principle) only — backward compatible with OMEGA dict."""
    name, principle, _ = get_omega_frame(index)
    return name, principle


if __name__ == "__main__":
    import sys
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    name, principle, frame = get_omega_frame(idx)
    print(f"Omega{idx} [{name}]")
    print(f"Principle: {principle}")
    print()
    print(frame)
