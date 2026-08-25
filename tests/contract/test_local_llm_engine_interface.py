from __future__ import annotations

import inspect

from local_llm import GroqLLMEngine, LocalLLMEngine, PromptEnvelope, create_groq_llm_engine, create_local_llm_engine
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


def test_local_and_groq_engines_both_expose_is_available():
    local_engine = create_local_llm_engine("llama3", "http://localhost:11434")
    groq_engine = create_groq_llm_engine("llama-3.3-70b-versatile")

    assert callable(local_engine.isAvailable)
    assert local_engine.isAvailable() == local_engine.isAvailableLocally()
    assert callable(groq_engine.isAvailable)
    assert groq_engine.isAvailable() == groq_engine.isAvailableLocally()


def test_local_engine_satisfies_the_llm_engine_protocol():
    engine = create_local_llm_engine("llama3", "http://localhost:11434")

    assert isinstance(engine, LLMEngine)
    assert callable(engine.generate)
    assert callable(engine.generateStream)
    assert inspect.isasyncgenfunction(engine.generateStream)


def test_groq_engine_satisfies_the_same_llm_engine_protocol():
    engine = create_groq_llm_engine("llama-3.3-70b-versatile")

    assert isinstance(engine, GroqLLMEngine)
    assert isinstance(engine, LLMEngine)
    assert callable(engine.isAvailableLocally)
    assert callable(engine.checkAvailability)
    assert callable(engine.generate)
    assert callable(engine.generateStream)
    assert inspect.isasyncgenfunction(engine.generateStream)
