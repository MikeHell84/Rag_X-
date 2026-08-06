export type AgentType = 'chat' | 'embedding' | 'reranker'

export type AgentProvider =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'mistral'
  | 'groq'
  | 'ollama'
  | 'openrouter'
  | 'custom'

export interface Agent {
  id: number
  name: string
  agent_type: AgentType
  agent_type_display: string
  provider: AgentProvider
  model: string
  base_url?: string
  description: string
  temperature: number
  max_tokens: number
  top_k: number
  system_prompt: string
  embedding_dim: number
  has_api_key: boolean
  api_key_masked: string
  api_key?: string
  is_active: boolean
  is_fallback: boolean
  fallback_order: number
  created_at: string
  updated_at: string
}

export interface PlatformConfig {
  chunk_size: number
  chunk_overlap: number
  hybrid_top_k: number
  rerank_top_k: number
  embed_batch_size: number
  max_context_tokens: number
  use_semantic_guard: boolean
}

export const TYPE_LABEL: Record<AgentType, string> = {
  chat: 'Generación (LLM)',
  embedding: 'Embeddings',
  reranker: 'Re-ranking'
}

export const PROVIDER_LABEL: Record<AgentProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic (Claude)',
  google: 'Google (Gemini)',
  mistral: 'Mistral',
  groq: 'Groq',
  ollama: 'Ollama (local)',
  openrouter: 'OpenRouter',
  custom: 'OpenAI-compatible (base_url)'
}

export const EMBEDDING_PROVIDERS: AgentProvider[] = ['openai', 'google', 'mistral', 'ollama', 'custom']
export const KEYLESS_PROVIDERS: AgentProvider[] = ['ollama']

export const PROVIDER_KEY_URL: Partial<Record<AgentProvider, string>> = {
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/settings/api-keys',
  google: 'https://aistudio.google.com/app/apikey',
  mistral: 'https://console.mistral.ai/api-keys',
  groq: 'https://console.groq.com/keys',
  openrouter: 'https://openrouter.ai/keys'
}

export const MODELS_BY_PROVIDER: Record<AgentProvider, { chat: string[]; embedding: string[] }> = {
  openai: {
    chat: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'o3-mini', 'o3'],
    embedding: ['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002']
  },
  anthropic: {
    chat: ['claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-sonnet-4-20250514', 'claude-haiku-4-5-20251001'],
    embedding: []
  },
  google: {
    chat: ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'],
    embedding: ['text-embedding-004', 'gemini-embedding-001']
  },
  mistral: {
    chat: ['mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest'],
    embedding: ['mistral-embed']
  },
  groq: {
    chat: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it', 'mixtral-8x7b-32768'],
    embedding: []
  },
  ollama: {
    chat: ['llama3.2', 'llama3.1', 'qwen2.5', 'gemma2', 'mistral'],
    embedding: ['nomic-embed-text', 'mxbai-embed-large', 'bge-m3']
  },
  openrouter: {
    chat: ['openai/gpt-4o-mini', 'anthropic/claude-3.5-sonnet', 'meta-llama/llama-3.3-70b-instruct'],
    embedding: []
  },
  custom: {
    chat: [''],
    embedding: ['']
  }
}

export function defaultModel(provider: AgentProvider, agentType: AgentType): string {
  const list = MODELS_BY_PROVIDER[provider][agentType === 'embedding' ? 'embedding' : 'chat']
  return list.find((m) => m !== '') ?? (agentType === 'embedding' ? 'text-embedding-3-small' : 'gpt-4o-mini')
}

export function modelsFor(provider: AgentProvider, agentType: AgentType): string[] {
  return MODELS_BY_PROVIDER[provider][agentType === 'embedding' ? 'embedding' : 'chat'].filter((m) => m !== '')
}
