# Tool selection and discovery

Roles provide loading preferences, not access boundaries. All worker and coordinator agents use the same selection and execution pipeline.

Shipped role prompts express specialization preferences and defer tool availability to the runtime catalog and permissions. Saved custom prompts are not rewritten.

## Request flow

1. Filter the registry by current tool permissions, explicit denies, team/agent scope, and host ownership.
2. Rank visible tool descriptions against the task using the shared local Model2Vec model, combined with whole-word relevance. Exact tool names take precedence. Compound requests are compared as a whole and by clauses; category diversification prevents a large tool family from filling every slot.
3. Load up to 12 schemas. Discovery, file reading, and clarification are prioritized, followed by explicitly discovered tools, semantic matches, general defaults, and role defaults.
4. Apply the schema token budget in relevance order, preserving discovery and explicitly requested schemas. Provider serialization can sort the resulting selection for stable caching without changing which tools survive budgeting. The full context capacity check remains authoritative.
5. Send the system context, message history, and active schemas to the model. Ordinary conversational requests use the existing no-tool chat profile.
6. Execute returned calls through the existing safe/judge/human/block policy gates. Relevance ranking never grants execution permission.

## Discovery

Agents can use any of these forms:

```json
{"query": "Take a picture of the page"}
{"family": "browser"}
{"tool_names": ["browser_navigate", "browser_extract_text"]}
```

All matching and activation use the same retrieval function. New requests take precedence over older discoveries; older tools remain while space permits. Failed searches do not discard useful tools. Results distinguish loaded schemas from deferred tools and put the activation summary first so result truncation does not hide it.

The system catalog lists permitted families and concise examples, plus instructions for query discovery. A large family cannot truncate all later families out of the catalog. New plugin registrations and permission changes invalidate the agent's cached catalog. Metadata changes invalidate retrieval caches automatically.

## Failure handling

- If local embeddings are unavailable or malformed, whole-word description search remains available. Exact-name and family discovery do not require the semantic model.
- Model/schema budgeting preserves relevance order for OpenAI, Anthropic, and Gemini formats. Primary and fallback models use the same preparation path.
- Capability-refusal recovery can point agents toward unloaded but discoverable tools. It does not override actual permission denials, approval decisions, or reported execution failures.
- Existing live execution checks remain authoritative if permissions change between selection and execution.

Semantic retrieval is a relevance estimate, not a guarantee of understanding every request. Clear tool descriptions and model-driven discovery remain necessary. Initial ranking uses the task request; agents use query discovery as their needs change during a task.

## Regression coverage

`backend/tests/test_tool_retrieval.py` exercises real-model paraphrases, newly registered plugins, metadata/cache changes, embedding outages, permission filtering before selection limits, relevance-preserving budgets across providers, fallback consistency, query discovery, and scoped schemas. `test_tool_discovery_policy.py`, `test_intent_engine.py`, and the existing access-control/execution tests cover authorization and recovery boundaries.
