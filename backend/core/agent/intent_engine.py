"""
# backend/core/agent/intent_engine.py

Grammar-based intent parsing and anti-refusal engine.
Ensures deterministic action enforcement on Turn 1 and eliminates false safety/capability refusals.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class IntentKind(str, Enum):
    ACTION = "action"
    INFORMATIONAL = "informational"


class IssueKind(str, Enum):
    UNEXECUTED_PROMISE = "unexecuted_promise"


@dataclass(frozen=True)
class CapabilityContext:
    browser_available: bool = False
    shell_available: bool = False
    filesystem_available: bool = False


@dataclass(frozen=True)
class IntentResult:
    kind: IntentKind
    requires_action: bool
    confidence: float


@dataclass(frozen=True)
class ResponseIssue:
    kind: IssueKind
    message: str


class IntentEngine:
    """
    Analyzes natural language prompts and agent responses to enforce action-gated
    execution and intercept unexecuted promises or false refusals.
    """

    # Pure informational query prefixes that should NOT be forced to call a tool
    _PURE_QUESTION_PREFIXES = (
        "what is", "what are", "what does", "what do", "what can", "what will",
        "why is", "why are", "why did", "why does", "why do",
        "how to", "tell me how", "how does", "how do", "how come", "how can", "how would",
        "who is", "who are", "who was",
        "explain how", "explain what", "explain why", "can you explain",
        "tell me about", "tell me what", "describe what", "describe how",
        "is it possible to", "difference between",
        "do you have", "do you", "do we have", "can you tell me",
        "are you able to", "is there", "are there", "have you", "has anyone",
        "which tools", "what tools", "what capabilities", "what permissions",
    )

    # Imperative action verbs
    _ACTION_VERBS = (
        "open", "browse", "navigate", "visit", "search", "google", "look up",
        "create", "make", "generate", "write", "draft", "code", "scaffold",
        "edit", "modify", "update", "patch", "refactor", "change", "replace",
        "delete", "remove", "clean", "drop",
        "run", "execute", "start", "launch", "trigger",
        "test", "check", "verify", "inspect", "debug", "fix", "solve", "resolve",
        "build", "compile", "bundle", "install", "download", "clone", "git",
        "hire", "spawn", "delegate", "assign", "dispatch",
        "find", "locate", "grep", "scan",
    )

    # Subject + Modal + Verb pattern (e.g. "I want you to open", "Can you please search", "Let's fix")
    _MODAL_PREFIX_RE = re.compile(
        r"^(?:(?:i\s+need\s+you\s+to|i\s+want\s+you\s+to|please|can\s+you(?:\s+please)?|could\s+you(?:\s+please)?|would\s+you(?:\s+please)?|let's|help\s+me(?:\s+to)?|go\s+ahead\s+and|kindly)\s+)+(?:to\s+)?",
        re.IGNORECASE,
    )

    # Patterns indicating unexecuted promises ("I will open the file", "Let me search for that", "On it — opening...")
    _UNEXECUTED_PROMISE_PATTERNS = [
        re.compile(r"\b(?:i'll|i\s+will|let\s+me(?!\s+know)|let's|i\s+am\s+going\s+to|working\s+on\s+it|just\s+a\s+moment|one\s+moment)\b", re.IGNORECASE),
        re.compile(r"\b(?:i'll\s+hire|i\s+will\s+hire|i'll\s+spawn|i\s+will\s+spawn|i'll\s+delegate|hiring\s+a|spawning\s+a)\b", re.IGNORECASE),
        re.compile(r"\b(?:on\s+it|i['’]?m\s+on\s+it)\b", re.IGNORECASE),
        re.compile(r"\b(?:opening\s+(?:a\s+)?(?:browser|file|window|tab|terminal)|searching\s+(?:for|the\s+web)|checking\s+(?:the\s+)?(?:browser|database|files?)|navigating\s+to)\b", re.IGNORECASE),
        re.compile(r"\b(?:starting\s+(?:to|on)|about\s+to|getting\s+started\s+on)\b", re.IGNORECASE),
    ]

    # False refusal patterns
    _FALSE_BROWSER_REFUSAL_RE = re.compile(
        r"(?:cannot|can't|unable\s+to|(?:do\s+not|don't)\s+have\s+(?:access\s+to|the\s+ability\s+to))\s+(?:a\s+)?(?:browser|browse|open\s+(?:a\s+)?browser|access\s+(?:the\s+)?(?:web|internet|external\s+sites)|visit\s+websites?|navigate\s+to\s+urls?)",
        re.IGNORECASE,
    )

    _FALSE_CAPABILITY_REFUSAL_RE = re.compile(
        r"(?:as\s+an\s+ai|i\s+am\s+an\s+ai|i\s+don't\s+have\s+(?:a\s+)?shell|cannot\s+execute\s+commands?|cannot\s+create\s+files?|do\s+not\s+have\s+file\s+access)",
        re.IGNORECASE,
    )

    @classmethod
    def classify_intent(cls, prompt: str) -> Tuple[str, float]:
        """
        Classifies user prompt using semantic router (vector cosine similarity).
        Returns (route_name, score). Falls back to ('unknown', 0.0).
        """
        try:
            from core.agent.semantic_router import semantic_router
            match = semantic_router.route(prompt)
            if match:
                return match.name, match.score
        except Exception:
            pass
        return "unknown", 0.0

    @classmethod
    def is_action_request(cls, prompt: str) -> bool:
        """
        Determines if a user prompt is an actionable request that mandates
        a tool execution on Turn 1.
        Uses SemanticRouter and grammar/regex rules with @mention normalization.
        """
        if not prompt or not prompt.strip():
            return False

        # Strip @mentions like @Archer, @Nova to isolate intent
        clean_prompt = re.sub(r'@[A-Za-z0-9_-]+', '', prompt).strip()
        p = clean_prompt.lower()

        # Check for capability / access inquiries (e.g. "do you have access to write something into memory tool?")
        if re.search(r"^(?:do\s+you\s+have|are\s+you\s+able\s+to|can\s+you\s+access|what\s+tools?\s+do\s+you\s+have|which\s+tools?\s+do\s+you\s+have)\b", p):
            if any(term in p for term in ["access", "tool", "tools", "permission", "permissions", "capability", "capabilities", "memory"]):
                return False

        # Bare capability questions lack a concrete object to act on.
        if re.fullmatch(r"can you (?:write to|read from|access) (?:the )?memory\??", p):
            return False

        # Direct imperative check: If the prompt starts with an action verb (or modal prefix + action verb)
        # and not a question prefix, it is an action request regardless of router similarity.
        first_clean = cls._MODAL_PREFIX_RE.sub("", p).strip()
        first_words = first_clean.split()
        if first_words and first_words[0] in cls._ACTION_VERBS:
            if not any(p.startswith(q) for q in cls._PURE_QUESTION_PREFIXES):
                return True

        # Phase 2: Grammar & Rule-based Fallback
        # If it starts with an informational question prefix, it's not an action mandate
        # UNLESS it also contains an explicit compound action directive (e.g. "How does auth work? Find the auth file")
        for q_pre in cls._PURE_QUESTION_PREFIXES:
            if p.startswith(q_pre):
                # Check for subsequent action commands separated by punctuation
                sentences = re.split(r"[.?!;\n]+", p)
                if len(sentences) > 1:
                    # If any subsequent sentence is an action command, consider it actionable
                    return any(cls._is_imperative_sentence(s.strip()) for s in sentences[1:] if s.strip())
                return False

        # Phase 1: Semantic Intent Routing (Vector Similarity)
        route_name, score = cls.classify_intent(clean_prompt)
        if route_name in ("capability_inquiry", "chitchat_greeting", "informational_question") and score >= 0.75:
            return False
        if route_name == "imperative_action":
            return True

        return cls._is_imperative_sentence(p)

    @classmethod
    def _is_imperative_sentence(cls, sentence: str) -> bool:
        """Checks if a single sentence represents an imperative action request."""
        if not sentence:
            return False

        clean = cls._MODAL_PREFIX_RE.sub("", sentence).strip()

        # Check if first word of the cleaned sentence is an action verb
        words = clean.split()
        if words and words[0] in cls._ACTION_VERBS:
            return True

        # Check for direct action verb patterns anywhere in clean
        for verb in cls._ACTION_VERBS:
            if re.search(rf"\b{re.escape(verb)}\b", clean):
                # Ensure it's not preceded by "how to" or "way to"
                if not re.search(rf"\b(?:how\s+to|way\s+to|steps?\s+to)\s+{re.escape(verb)}\b", sentence):
                    return True

        return False

    @classmethod
    def detect_false_refusal(cls, response_text: str, capabilities: Optional[CapabilityContext] = None) -> Optional[str]:
        """
        Detects if the model generated a false safety/capability refusal when it
        actually has full tool capabilities.
        """
        if not response_text:
            return None

        # Unknown capabilities never justify overriding a refusal or boundary.
        if capabilities is None:
            return None
        if cls._FALSE_BROWSER_REFUSAL_RE.search(response_text) and capabilities.browser_available:
            return "Browser tools are available. If the action is authorized, use a native tool call; otherwise explain the missing permission."
        shell_denial = re.search(r"shell|execute\s+commands?", response_text, re.I)
        file_denial = re.search(r"create\s+files?|file\s+access", response_text, re.I)
        if (shell_denial and capabilities.shell_available) or (file_denial and capabilities.filesystem_available):
            return "The relevant tools are available. Use native tool calls only within the user's authorization and current permissions."

        return None

    @classmethod
    def detect_unexecuted_promise(cls, response_text: str, has_tool_call: bool) -> Optional[str]:
        """
        Detects when an agent says it will do something or is about to take an action
        but fails to output an [ACTION] tag.
        """
        if has_tool_call or not response_text:
            return None

        text_lower = response_text.lower()

        # Ignore conversational phrases like "let me know" or "let me see if"
        if "let me know" in text_lower or "let me see if" in text_lower:
            cleaned_check = re.sub(r"\blet\s+me\s+(?:know|see\s+if)\b", "", text_lower)
            if not any(pat.search(cleaned_check) for pat in cls._UNEXECUTED_PROMISE_PATTERNS):
                return None

        if any(pattern.search(text_lower) for pattern in cls._UNEXECUTED_PROMISE_PATTERNS):
            return (
                "You described a future action without executing a tool. If the user authorized that action, "
                "use the available native tool schema with concrete arguments. If permission or information "
                "is missing, ask for it; if no action is needed, answer directly. Never manufacture a tool "
                "call in text or claim an unverified action succeeded."
            )

        return None

    @classmethod
    def analyze(cls, prompt: str) -> IntentResult:
        requires_action = cls.is_action_request(prompt)
        return IntentResult(IntentKind.ACTION if requires_action else IntentKind.INFORMATIONAL,
                            requires_action, 0.95 if requires_action else 0.75)

    @classmethod
    def detect_response_issue(cls, response_text: str, has_tool_call: bool = False) -> Optional[ResponseIssue]:
        message = cls.detect_unexecuted_promise(response_text, has_tool_call)
        return ResponseIssue(IssueKind.UNEXECUTED_PROMISE, message) if message else None
