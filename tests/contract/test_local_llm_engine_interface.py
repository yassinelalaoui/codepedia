from __future__ import annotations

from local_llm import LocalLLMEngine, PromptEnvelope, create_local_llm_engine


def test_public_api_exposes_local_engine_types():
    assert LocalLLMEngine.__name__ == "LocalLLMEngine"
    assert PromptEnvelope.__name__ == "PromptEnvelope"
    assert callable(create_local_llm_engine)


def test_engine_construction_validates_local_endpoint():
    engine = create_local_llm_engine("llama3", "http://localhost:11434")

    assert engine.modelName == "llama3"
    assert engine.endpointUrl == "http://localhost:11434"
    assert engine.isAvailableLocally() in {True, False}
