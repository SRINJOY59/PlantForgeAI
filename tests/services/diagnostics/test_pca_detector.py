"""Unit tests for the PCA-based Multivariate Statistical Process Control (MSPC) detector."""

import json
from datetime import datetime, timezone
import numpy as np
import pytest

from diagnostics.detector import (
    AnomalyScore,
    DetectorStore,
    OnlinePCADetector,
    PCAModel,
    train_pca_model,
)


@pytest.fixture
def nominal_multivariate_data():
    """Generate 200 samples of 6 correlated plant variables (nominal baseline)."""
    np.random.seed(42)
    n_samples = 200
    # True underlying latent drivers (e.g. throughput, ambient temp)
    latent1 = np.random.normal(0, 1, n_samples)
    latent2 = np.random.normal(0, 1, n_samples)

    # 6 correlated plant tags
    x1 = 100.0 + 2.0 * latent1 + np.random.normal(0, 0.2, n_samples) # REACTOR.T
    x2 = 2500.0 + 15.0 * latent1 + np.random.normal(0, 1.0, n_samples) # REACTOR.P
    x3 = 50.0 + 3.0 * latent2 + np.random.normal(0, 0.3, n_samples) # SEPARATOR.Level
    x4 = 65.0 + 2.5 * latent1 + 1.2 * latent2 + np.random.normal(0, 0.2, n_samples) # CONDENSER.T
    x5 = 120.0 + 4.0 * latent2 + np.random.normal(0, 0.4, n_samples) # STRIPPER.Level
    x6 = 80.0 + 1.8 * latent1 + np.random.normal(0, 0.2, n_samples) # PRODUCT.Flow

    return {
        "REACTOR.T": x1.tolist(),
        "REACTOR.P": x2.tolist(),
        "SEPARATOR.Level": x3.tolist(),
        "CONDENSER.T": x4.tolist(),
        "STRIPPER.Level": x5.tolist(),
        "PRODUCT.Flow": x6.tolist(),
    }


def test_pca_training_and_serialization(nominal_multivariate_data, tmp_path):
    model = train_pca_model(nominal_multivariate_data, variance_target=0.85, alpha=0.01)

    assert len(model.tags) == 6
    assert model.k_components < 6
    assert model.variance_explained >= 0.85
    assert model.t2_limit > 0
    assert model.spe_limit > 0

    # Test JSON serialization roundtrip
    model_json = model.to_json()
    reloaded = PCAModel.from_json(model_json)
    assert reloaded.tags == model.tags
    assert reloaded.k_components == model.k_components
    assert pytest.approx(reloaded.t2_limit, 1e-4) == model.t2_limit
    assert pytest.approx(reloaded.spe_limit, 1e-4) == model.spe_limit

    # Test DetectorStore persistence
    store_file = tmp_path / "model.json"
    store = DetectorStore(local_fallback=store_file)
    store.save(model)
    loaded = store.load()
    assert loaded is not None
    assert loaded.tags == model.tags


def test_pca_nominal_scoring(nominal_multivariate_data):
    model = train_pca_model(nominal_multivariate_data, variance_target=0.85, alpha=0.01)

    # Score a nominal sample close to means
    nominal_sample = {
        "REACTOR.T": 100.2,
        "REACTOR.P": 2501.0,
        "SEPARATOR.Level": 50.1,
        "CONDENSER.T": 65.2,
        "STRIPPER.Level": 120.3,
        "PRODUCT.Flow": 80.1,
    }
    score = model.score_sample(nominal_sample, ts=1000.0)

    assert isinstance(score, AnomalyScore)
    assert not score.is_anomaly
    assert score.t2_ratio < 1.0
    assert score.spe_ratio < 1.0


def test_pca_correlation_break_detection(nominal_multivariate_data):
    """Test that a correlation break is caught by SPE/T2 even when individual
    variables stay within individual +/- 3 sigma bounds."""
    model = train_pca_model(nominal_multivariate_data, variance_target=0.85, alpha=0.01)

    # In nominal data: REACTOR.T and CONDENSER.T are positively correlated (~+0.9).
    # Fault scenario: High REACTOR.T (104.0, +2 sigma) but LOW CONDENSER.T (60.0, -2 sigma).
    # Both are within univariate limits [94..106] and [58..72], but their JOINT physical relationship broke!
    correlation_break_sample = {
        "REACTOR.T": 104.0,
        "REACTOR.P": 2530.0,
        "SEPARATOR.Level": 50.0,
        "CONDENSER.T": 59.0, # Breaks correlation
        "STRIPPER.Level": 120.0,
        "PRODUCT.Flow": 83.0,
    }

    score = model.score_sample(correlation_break_sample, ts=1000.0)
    assert score.is_anomaly
    assert score.spe_ratio > 1.0 # SPE explodes when correlation subspace is violated
    assert score.top_contributing_tag in ["CONDENSER.T", "REACTOR.T"]
    assert score.contributions["CONDENSER.T"] > 0.15


def test_online_detector_persistence(nominal_multivariate_data):
    model = train_pca_model(nominal_multivariate_data, variance_target=0.85, alpha=0.01)
    detector = OnlinePCADetector(model, persistence_count=3, window_size=5, cooldown_s=60.0)

    nominal_sample = {t: float(np.mean(nominal_multivariate_data[t])) for t in model.tags}
    anom_sample = dict(nominal_sample)
    anom_sample["REACTOR.T"] = nominal_sample["REACTOR.T"] + 15.0 # Large deviation

    # Sample 1: anom (1/3) -> No event
    ev1 = detector.process_sample(anom_sample, ts=100.0)
    assert ev1 is None

    # Sample 2: normal (1/3) -> Glitch didn't persist
    ev2 = detector.process_sample(nominal_sample, ts=101.0)
    assert ev2 is None

    # Sample 3, 4, 5: sustained anomaly (3 consecutive)
    detector.process_sample(anom_sample, ts=102.0)
    detector.process_sample(anom_sample, ts=103.0)
    ev5 = detector.process_sample(anom_sample, ts=104.0)

    assert ev5 is not None
    assert ev5.trigger_tag == "REACTOR.T"
    assert ev5.level == "ML_ANOMALY"
    assert ev5.t2_ratio > 1.0 or ev5.spe_ratio > 1.0
    assert isinstance(ev5.onset, datetime)

    # Sample 6: during cooldown -> Suppressed
    ev6 = detector.process_sample(anom_sample, ts=120.0)
    assert ev6 is None
