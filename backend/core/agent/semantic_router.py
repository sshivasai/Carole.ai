"""
# backend/core/agent/semantic_router.py

Native ultra-fast semantic intent router for Carole.ai.
Uses pre-trained embeddings (via model2vec or multi_model_router) and cosine similarity
to route user prompts to intents in milliseconds without LLM inference overhead or package downgrades.
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
import numpy as np

logger = logging.getLogger("carole.semantic_router")


@dataclass
class Route:
    name: str
    utterances: List[str]
    threshold: float = 0.65
    _vectors: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class RouteMatch:
    name: str
    score: float
    threshold: float


class SemanticRouter:
    """
    In-memory vector router that classifies natural language queries into defined intent routes.
    """

    def __init__(self):
        self._model = None
        self._initialized = False
        self.routes: Dict[str, Route] = {}
        self._setup_default_routes()

    def _setup_default_routes(self):
        self.routes = {
            "capability_inquiry": Route(
                name="capability_inquiry",
                threshold=0.62,
                utterances=[
                    "do you have access to write something into memory tool ?",
                    "can you write to memory?",
                    "what tools do you have access to?",
                    "do you have access to the browser tool?",
                    "can you run shell commands?",
                    "are you allowed to edit files in this project?",
                    "what permissions do you have?",
                    "can you tell me what you are able to do?",
                    "is it possible for you to create files?",
                    "do we have access to git tools?",
                    "do you have capability to search the web?",
                    "what are your available tools?",
                ],
            ),
            "chitchat_greeting": Route(
                name="chitchat_greeting",
                threshold=0.65,
                utterances=[
                    "hello",
                    "hey there",
                    "hi archer",
                    "good morning",
                    "how are you doing today?",
                    "thanks for the help",
                    "thank you very much",
                    "nice job, looks good",
                    "hey team, who is online?",
                    "great work!",
                ],
            ),
            "informational_question": Route(
                name="informational_question",
                threshold=0.62,
                utterances=[
                    "how does authentication work in this app?",
                    "what is the difference between facts and memory?",
                    "why is this function returning null?",
                    "explain how carole_dir is constructed",
                    "what does this error message mean?",
                    "tell me about the architecture of the backend",
                    "can you explain the project structure?",
                    "where are temporary files stored?",
                    "what is the purpose of the judge ai?",
                ],
            ),
            "imperative_action": Route(
                name="imperative_action",
                threshold=0.62,
                utterances=[
                    "write a python script to test the database",
                    "create the frontend landing page in index.html",
                    "run pytest on the test suite",
                    "edit backend/main.py to add the new endpoint",
                    "search google for the latest react release",
                    "build the frontend application",
                    "fix the bug in auth login handler",
                    "delete the temporary test files",
                    "create a new component for user profile",
                    "install the requirements and start the server",
                    "refactor the database queries to be async",
                ],
            ),
        }

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            from core.knowledge.hybrid_search import StaticCodeEmbedder
            self._model = StaticCodeEmbedder.get_model()
        except Exception as e:
            logger.warning("Semantic intent routing unavailable; grammar rules remain active: %s", type(e).__name__)
            self._model = None

        # Precompute normalized embeddings for all routes
        for route in self.routes.values():
            self._index_route(route)

        self._initialized = self._model is not None

    def _index_route(self, route: Route):
        if not route.utterances:
            return
        if self._model is not None:
            try:
                embeddings = self._model.encode(route.utterances)
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1e-10
                route._vectors = embeddings / norms
            except Exception as e:
                logger.error("Failed to index route %s: %s", route.name, e)
                route._vectors = None

    def route(self, query: str) -> Optional[RouteMatch]:
        """
        Routes the given query to the best matching intent route.
        Returns RouteMatch if similarity >= route.threshold, else None.
        """
        if not query or not query.strip():
            return None

        self._ensure_initialized()

        if self._model is None:
            return None

        clean_query = query.strip()
        try:
            q_vec = self._model.encode([clean_query])[0]
            norm = np.linalg.norm(q_vec)
            if norm == 0:
                return None
            q_vec = q_vec / norm

            best_match: Optional[RouteMatch] = None
            highest_score = -1.0

            for route in self.routes.values():
                if route._vectors is None or len(route._vectors) == 0:
                    continue

                # Cosine similarities across all utterances in this route
                sims = np.dot(route._vectors, q_vec)
                max_sim = float(np.max(sims))

                if max_sim > highest_score:
                    highest_score = max_sim
                    if max_sim >= route.threshold:
                        best_match = RouteMatch(name=route.name, score=max_sim, threshold=route.threshold)

            return best_match
        except Exception as e:
            logger.debug("Semantic router error during query: %s", e)
            return None


# Global singleton instance
semantic_router = SemanticRouter()
