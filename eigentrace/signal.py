"""
LogosSignal — Generation Physics Metric
MIT License
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class SignalMetrics:
    logos_loss: float
    material: float
    spectral: float
    phase: float
    z_pinch: bool
    status: str

    def __str__(self):
        return (f"SignalMetrics(status={self.status}, "
                f"loss={self.logos_loss:.4f}, "
                f"z_pinch={self.z_pinch})")


def _require_torch():
    try:
        import torch
        return torch
    except ImportError:
        raise ImportError(
            "LogosSignal requires torch. "
            "Install with: pip install eigentrace[signal]"
        )


def _text_to_signal(text, length=256):
    """
    Convert text to a signal vector using word-level unigram surprisal.
    Each word becomes -log(freq/total) normalized to [0,1].
    Zero-pad to length. This makes semantic incoherence score higher
    than length or character variance.
    """
    torch = _require_torch()
    import re
    import math
    words = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower()).split()
    if not words:
        signal = [0.0] * length
        return torch.tensor(signal, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

    # word frequency count
    freq: dict = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    total = len(words)

    # surprisal per word: -log2(p) normalized by max possible (-log2(1/total))
    max_surprisal = math.log2(total) if total > 1 else 1.0
    signal = []
    for w in words:
        p = freq[w] / total
        s = -math.log2(p) / max_surprisal if p > 0 else 1.0
        signal.append(s)

    # truncate or zero-pad to length
    signal = signal[:length]
    while len(signal) < length:
        signal.append(0.0)
    return torch.tensor(signal, dtype=torch.float32).unsqueeze(0).unsqueeze(0)


def _z_pinch(surprisal, sigma=2.5):
    if len(surprisal) < 4:
        return False
    arr = np.array(surprisal)
    std = arr.std()
    if std < 0.01:
        return False
    return bool(np.any(arr > arr.mean() + sigma * std))


def signal_score(text_pred, text_truth,
                 grace_coeff=0.5, phase_weight=0.1, eps=1e-8):
    torch = _require_torch()
    pred = _text_to_signal(text_pred)
    truth = _text_to_signal(text_truth)

    material = float(((pred - truth) ** 2).mean())

    pred_f = torch.fft.rfft(pred, dim=-1)
    truth_f = torch.fft.rfft(truth, dim=-1)
    pred_mag = pred_f.abs().clamp_min(eps)
    truth_mag = truth_f.abs().clamp_min(eps)

    log_diff = (pred_mag.log() - truth_mag.log()) ** 2
    presence_w = truth_mag / truth_mag.sum(dim=-1, keepdim=True).clamp_min(eps)
    spectral = float((log_diff * presence_w).sum())

    interaction = pred_f * torch.conj(truth_f)
    angle = torch.angle(interaction)
    phase_err = 1.0 - torch.cos(angle)
    mercy = truth_mag / truth_mag.sum(dim=-1, keepdim=True).clamp_min(eps)
    phase = float((phase_err * mercy).sum())

    total = material + grace_coeff * spectral + phase_weight * phase

    pred_np = pred.squeeze().numpy()
    # exclude zero-padding from variance calculation
    nonzero = pred_np[pred_np != 0.0]
    active = nonzero if len(nonzero) > 4 else pred_np
    mean_l = float(active.mean())
    surprisal = [abs(float(x) - mean_l) / (mean_l + 1e-9) for x in active]
    zp = _z_pinch(surprisal)

    arr = np.array(surprisal)
    pv = float(np.var(arr))

    if total < 0.01:
        status = "FLAT"
    elif total > 3.5:
        status = "INCOHERENT"
    else:
        status = "COHERENT"

    return SignalMetrics(
        logos_loss=round(total, 6),
        material=round(material, 6),
        spectral=round(spectral, 6),
        phase=round(phase, 6),
        z_pinch=zp,
        status=status,
    )
