import pytest
from plantmind_core.schemas.field_copilot import WorkerIntent
from agents.usecases.field_copilot.prompts import is_safety_step, make_spoken

def test_is_safety_step():
    assert is_safety_step("WARNING: High voltage area.") is True
    assert is_safety_step("Ensure lockout tagout is performed.") is True
    assert is_safety_step("Check the pressure gauge.") is False
    assert is_safety_step("Be careful, surface may be hot surface.") is True

def test_make_spoken():
    # Should strip markdown and citations
    clean = make_spoken("Check the valve **XV-101** [doc:abc p.1]")
    assert clean == "Check the valve XV-101"
    
    # Should prefix warning if hazard words are present
    warn = make_spoken("Toxic gas may be present [doc:123]")
    assert warn == "WARNING: Toxic gas may be present"
    
    # Should not double prefix warning
    double_warn = make_spoken("WARNING: Toxic gas may be present [doc:123]")
    assert double_warn == "WARNING: Toxic gas may be present"
