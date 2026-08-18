"""Diagnostics: fault detection, isolation and matching.

The statistical half of RCA - it turns telemetry into fault signatures and
matches live anomalies against the learned library. It holds no LLM dependency
on purpose: the signal never meets the model. The two worlds meet only through
the FaultSignature / DiagnosisMatch contracts in plantmind_core.schemas, and an
LLM enters only later, in the agents service, to narrate a finished Diagnosis.
"""
