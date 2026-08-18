"""PCA model calibration and threshold calculation for Multivariate SPC.

Computes:
1. Mean and standard deviation per process variable.
2. Correlation matrix eigendecomposition / SVD.
3. Dimension reduction selecting k components for cumulative variance target (default 85%).
4. Hotelling's T² control limit via F-distribution.
5. Squared Prediction Error (SPE / Q) control limit via Jackson-Mudholkar approximation.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from diagnostics.detector.model import PCAModel
from plantmind_core.telemetry import get_logger

log = get_logger("diagnostics.detector.trainer")


def train_pca_model(
    data: dict[str, list[float]],
    *,
    variance_target: float = 0.85,
    alpha: float = 0.01,
    min_samples: int = 30,
) -> PCAModel:
    """Train a PCA baseline model from nominal telemetry samples.

    Args:
        data: Mapping of tag_id -> list of float values (equal length).
        variance_target: Minimum fraction of cumulative variance explained (0.80 - 0.95).
        alpha: False alarm significance level (e.g. 0.01 = 99% confidence threshold).
        min_samples: Minimum required observations to fit PCA reliably.

    Returns:
        Calibrated PCAModel ready for online scoring.
    """
    tags = [t for t, vals in data.items() if vals and len(vals) >= min_samples]
    if not tags:
        raise ValueError(f"Insufficient samples: need at least {min_samples} points per tag")

    n_samples = min(len(data[t]) for t in tags)
    if n_samples < min_samples:
        raise ValueError(f"Sample length ({n_samples}) less than min_samples ({min_samples})")

    # Build matrix X: N x P
    cols = []
    for tag in tags:
        cols.append(np.array(data[tag][:n_samples], dtype=np.float64))
    X = np.column_stack(cols) # N x P
    N, P = X.shape

    # 1. Compute means and standard deviations
    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0, ddof=1)

    # Protect against zero variance (constant tags)
    std[std < 1e-6] = 1.0

    # 2. Standardize X: Z = (X - mu) / sigma
    Z = (X - mean) / std

    # 3. Covariance / Correlation matrix: R = (1 / (N - 1)) * Z^T * Z
    R = np.cov(Z, rowvar=False)
    if P == 1:
        R = np.array([[1.0]])

    # 4. Eigendecomposition of R
    eigenvalues, eigenvectors = np.linalg.eigh(R)

    # Sort descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[idx], 1e-8)  # prevent division by zero
    eigenvectors = eigenvectors[:, idx]

    # 5. Determine retained components k based on variance target
    total_var = np.sum(eigenvalues)
    var_exp = eigenvalues / total_var
    cum_var_exp = np.cumsum(var_exp)

    k = int(np.searchsorted(cum_var_exp, variance_target) + 1)
    k = max(1, min(k, P - 1 if P > 1 else 1))

    P_k = eigenvectors[:, :k]         # Loading matrix (P x k)
    lam_k = eigenvalues[:k]           # Retained eigenvalues (k)
    retained_var = float(cum_var_exp[k - 1])

    # 6. Calculate Hotelling's T^2 threshold
    # T2_limit = [k(N-1) / (N-k)] * F_alpha(k, N-k)
    if N > k:
        f_crit = stats.f.ppf(1.0 - alpha, k, N - k)
        t2_limit = float((k * (N - 1) / (N - k)) * f_crit)
    else:
        t2_limit = float(stats.chi2.ppf(1.0 - alpha, df=k))

    # 7. Calculate SPE (Q) threshold using Jackson-Mudholkar approximation
    if k < P:
        res_eigs = eigenvalues[k:]
        theta1 = float(np.sum(res_eigs))
        theta2 = float(np.sum(res_eigs ** 2))
        theta3 = float(np.sum(res_eigs ** 3))

        if theta1 > 1e-8 and theta2 > 1e-8:
            h0 = 1.0 - (2.0 * theta1 * theta3) / (3.0 * (theta2 ** 2))
            if abs(h0) < 1e-4:
                h0 = 1e-4
            c_alpha = stats.norm.ppf(1.0 - alpha)
            term = 1.0 + (c_alpha * np.sqrt(2.0 * theta2 * (h0 ** 2))) / theta1 + (theta2 * h0 * (h0 - 1.0)) / (theta1 ** 2)
            spe_limit = float(theta1 * np.maximum(term, 0.0) ** (1.0 / h0))
        else:
            spe_limit = float(stats.chi2.ppf(1.0 - alpha, df=max(1, P - k)))
    else:
        spe_limit = 1.0

    # Ensure finite positive limits
    if not np.isfinite(t2_limit) or t2_limit <= 0:
        t2_limit = float(stats.chi2.ppf(1.0 - alpha, df=k))
    if not np.isfinite(spe_limit) or spe_limit <= 0:
        spe_limit = 1.0

    log.info("pca model trained",
             tags=P, samples=N, k_components=k,
             variance_explained=round(retained_var, 3),
             t2_limit=round(t2_limit, 2), spe_limit=round(spe_limit, 2))

    return PCAModel(
        tags=tags,
        mean=[float(m) for m in mean],
        std=[float(s) for s in std],
        components=[[float(cell) for cell in row] for row in P_k],
        eigenvalues=[float(lam) for lam in lam_k],
        t2_limit=t2_limit,
        spe_limit=spe_limit,
        variance_explained=retained_var,
        k_components=k,
        n_samples=N,
    )
