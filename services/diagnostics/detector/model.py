"""PCA-based Multivariate Statistical Process Control (MSPC) for TEP.

Defines the mathematical model representation and score containers for Hotelling's T²
and Squared Prediction Error (SPE / Q-statistic) anomaly detection.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass
class AnomalyScore:
    """Detection scores and tag-level attribution for a single telemetry sample."""
    ts: float
    t2: float
    spe: float
    t2_limit: float
    spe_limit: float
    t2_ratio: float           # t2 / t2_limit (> 1.0 indicates breach)
    spe_ratio: float          # spe / spe_limit (> 1.0 indicates breach)
    is_anomaly: bool          # True if t2_ratio > 1.0 or spe_ratio > 1.0
    top_contributing_tag: str # Tag with the highest residual / t2 contribution
    contributions: dict[str, float] # Normalized [0..1] attribution per tag


@dataclass
class PCAModel:
    """Fitted PCA baseline model for nominal plant state.

    Attributes:
        tags: Ordered list of tag IDs included in the model.
        mean: Tag-wise nominal means (shape P).
        std: Tag-wise nominal standard deviations (shape P).
        components: Principal component loading matrix P (shape P x k).
        eigenvalues: Latent roots corresponding to top k components (shape k).
        t2_limit: Hotelling's T^2 threshold at significance alpha (e.g. 0.01).
        spe_limit: SPE (Q-statistic) threshold at significance alpha.
        variance_explained: Ratio of total variance captured by top k components.
        k_components: Number of retained principal components.
        n_samples: Number of calibration samples used during fitting.
    """
    tags: list[str]
    mean: list[float]
    std: list[float]
    components: list[list[float]]   # P x k
    eigenvalues: list[float]        # k
    t2_limit: float
    spe_limit: float
    variance_explained: float
    k_components: int
    n_samples: int

    def score_sample(self, sample_dict: dict[str, float], ts: float = 0.0) -> AnomalyScore:
        """Score a single multivariate sample against the PCA baseline."""
        # Convert dictionary to ordered vector aligned with self.tags
        vec = []
        for i, tag in enumerate(self.tags):
            val = sample_dict.get(tag)
            if val is None or not np.isfinite(val):
                val = self.mean[i]
            vec.append(float(val))

        x = np.array(vec, dtype=np.float64)
        mu = np.array(self.mean, dtype=np.float64)
        sigma = np.array(self.std, dtype=np.float64)
        P = np.array(self.components, dtype=np.float64) # P x k
        lam = np.array(self.eigenvalues, dtype=np.float64) # k

        # Standardize: z = (x - mu) / sigma
        z = (x - mu) / sigma

        # Projection onto PC subspace: t = P^T * z (k x 1)
        t = np.dot(P.T, z)

        # Reconstruction: z_hat = P * t (P x 1)
        z_hat = np.dot(P, t)

        # Residual vector: e = z - z_hat
        e = z - z_hat

        # 1. Hotelling's T^2 statistic: sum(t_i^2 / lambda_i)
        t2 = float(np.sum((t ** 2) / lam))

        # 2. Squared Prediction Error (SPE / Q): ||e||^2 = sum(e_j^2)
        spe = float(np.sum(e ** 2))

        t2_ratio = float(t2 / self.t2_limit) if self.t2_limit > 0 else 0.0
        spe_ratio = float(spe / self.spe_limit) if self.spe_limit > 0 else 0.0
        is_anomaly = bool(t2_ratio > 1.0 or spe_ratio > 1.0)

        # Tag-level contribution calculation (SPE residual contributions)
        # cont_j = e_j^2
        raw_contrib = e ** 2
        total_contrib = float(np.sum(raw_contrib))
        if total_contrib > 1e-9:
            norm_contrib = raw_contrib / total_contrib
        else:
            norm_contrib = np.zeros_like(raw_contrib)

        contributions = {tag: round(float(norm_contrib[j]), 4) for j, tag in enumerate(self.tags)}

        top_idx = int(np.argmax(raw_contrib)) if len(raw_contrib) > 0 else 0
        top_tag = self.tags[top_idx] if self.tags else ""

        return AnomalyScore(
            ts=ts,
            t2=t2,
            spe=spe,
            t2_limit=self.t2_limit,
            spe_limit=self.spe_limit,
            t2_ratio=t2_ratio,
            spe_ratio=spe_ratio,
            is_anomaly=is_anomaly,
            top_contributing_tag=top_tag,
            contributions=contributions,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PCAModel":
        return cls(
            tags=list(data["tags"]),
            mean=list(data["mean"]),
            std=list(data["std"]),
            components=[list(row) for row in data["components"]],
            eigenvalues=list(data["eigenvalues"]),
            t2_limit=float(data["t2_limit"]),
            spe_limit=float(data["spe_limit"]),
            variance_explained=float(data["variance_explained"]),
            k_components=int(data["k_components"]),
            n_samples=int(data["n_samples"]),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "PCAModel":
        return cls.from_dict(json.loads(json_str))
