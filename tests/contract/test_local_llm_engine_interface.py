from __future__ import annotations

import inspect

from local_llm import LocalLLMEngine, PromptEnvelope, create_local_llm_engine
from local_llm.protocol import LLMEngine


def test_public_api_exposes_local_engine_types():
    assert LocalLLMEngine.__name__ == "LocalLLMEngine"
    assert PromptEnvelope.__name__ == "PromptEnvelope"
    assert callable(create_local_llm_engine)


def test_engine_construction_validates_local_endpoint():
    engine = create_local_llm_engine("llama3", "http://localhost:11434")

    assert engine.modelName == "llama3"
    assert engine.endpointUrl == "http://localhost:11434"
    assert engine.isAvailableLocally() in {True, False}


def test_the_engine_exposes_is_available():
    local_engine = create_local_llm_engine("llama3", "http://localhost:11434")

    assert callable(local_engine.isAvailable)
    assert local_engine.isAvailable() == local_engine.isAvailableLocally()
    # The model behind an answer is recorded, so a summary written by one
    # model is never mistaken for one written by another.
    assert local_engine.providerId == "local:llama3"


def test_local_engine_satisfies_the_llm_engine_protocol():
    engine = create_local_llm_engine("llama3", "http://localhost:11434")

    assert isinstance(engine, LLMEngine)
    assert callable(engine.generate)
    assert callable(engine.generateStream)
    assert inspect.isasyncgenfunction(engine.generateStream)
