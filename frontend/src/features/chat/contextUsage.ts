export interface ContextSnapshot {
  call_id?: string;
  run_id?: string;
  model?: string;
  estimated_tokens?: number;
  context_window?: number;
  output_reserve?: number;
  components?: Record<string, number>;
  timestamp?: number;
  profile?: string;
  capacity_source?: string;
}

export interface TokenUsageEvent {
  call_id?: string;
  agent_id?: string;
  agent_name?: string;
  model?: string;
  resolved_model?: string | null;
  context_window?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  reasoning_tokens?: number | null;
  usage_source?: string;
  input_source?: string;
  output_source?: string;
}

export function agentContext(snapshot?: ContextSnapshot, usage?: TokenUsageEvent) {
  const matches = !snapshot || (!!snapshot.call_id && snapshot.call_id === usage?.call_id);
  const measured = matches && usage?.input_source === "provider";
  const tokens = measured ? usage?.prompt_tokens : snapshot?.estimated_tokens ?? (matches ? usage?.prompt_tokens : undefined);
  const limit = snapshot?.context_window ?? (matches ? usage?.context_window : undefined);
  return { tokens, limit, source: measured ? "reported" : "estimated",
    percent: tokens !== undefined && limit ? Math.min(100, tokens / limit * 100) : undefined };
}
