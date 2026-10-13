"""AutoCV AI Facade.

Re-exports multi-agent clients, schemas, context builders, and prompts.
"""
from src.ai import (
    ANALYSIS_PROMPT,
    ANALYSIS_SCHEMA,
    EDIT_PROMPT,
    EDIT_SCHEMA,
    FACTS_POLICY,
    REPAIR_PROMPT,
    REPAIR_SCHEMA,
    AIClient,
    EditResult,
    ProviderError,
    object_schema,
    repair_context,
    text_sources,
    validate_json,
)

__all__ = [
    "AIClient",
    "ProviderError",
    "EditResult",
    "object_schema",
    "validate_json",
    "text_sources",
    "repair_context",
    "ANALYSIS_SCHEMA",
    "EDIT_SCHEMA",
    "REPAIR_SCHEMA",
    "ANALYSIS_PROMPT",
    "EDIT_PROMPT",
    "REPAIR_PROMPT",
    "FACTS_POLICY",
]
