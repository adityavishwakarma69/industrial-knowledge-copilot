"""
Industrial Knowledge Intelligence (IKI)
=======================================

An AI-powered platform that ingests heterogeneous industrial documents
(engineering drawings, maintenance records, safety procedures, inspection
reports, operating instructions, project files) and makes their collective
intelligence queryable through an Expert Knowledge Copilot.

Core design goals
-----------------
* Works fully offline out-of-the-box (deterministic embeddings + extractive
  answer synthesis) so it can be demoed without any API key.
* Pluggable AI backend: drop in OpenAI / Anthropic for higher-quality
  embeddings and generation via a single environment variable.
* Every answer is grounded: source citations, confidence scores and direct
  links back to the originating documents.
"""

__version__ = "1.0.0"
