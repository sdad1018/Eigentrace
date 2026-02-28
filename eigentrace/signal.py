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
    torch = _require_torch()
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    signal = [ord(c) / 127.0 for c in text[:length]]
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
    mean_l = float(pred_np.mean())
    surprisal = [abs(float(x) - mean_l) / (mean_l + 1e-9) for x in pred_np]
    zp = _z_pinch(surprisal)

    arr = np.array(surprisal)
    pv = float(np.var(arr))

    if spectral < 0.1 or pv < 0.001:
        status = "FLAT"
    elif spectral > 3.5 or pv > 1.2:
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
