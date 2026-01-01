# Architecture: AI-Augmented Diagnostics (Optional)

## 1. Core Philosophy: Offline-First & User Controlled

`kubectl-smart` is designed as a deterministic, offline-first tool for SREs. The introduction of Large Language Model (LLM) capabilities follows strict governance principles:

1.  **Offline by Default:** The tool assumes no internet access and no AI providers are configured. All core heuristics (scoring, graph analysis, forecasting) run locally on the user's machine.
2.  **Explicit Opt-In:** AI features are strictly disabled until the user explicitly creates a configuration file and sets `enabled = true`.
3.  **Vendor Agnostic:** Users choose their provider. Support includes cloud providers (OpenAI, Gemini) and **local, offline models** (Ollama, LocalAI) to maintain total data sovereignty.
4.  **Read-Only & Advisory:** The AI component, like the rest of the tool, has no write access to the cluster. Its output is labeled as "Advisory Insight" and clearly distinguished from deterministic system signals.

## 2. Configuration Strategy (`config.toml`)

Control is managed via a dedicated TOML configuration file (e.g., `~/.kubectl-smart/config.toml` or `./kubectl-smart.toml`). This ensures sensitive settings are not passed via command-line flags.

### Configuration Schema

```toml
[ai]
# MASTER SWITCH: Must be set to true to enable any AI features.
# Default: false
enabled = false

# Provider selection: "openai", "gemini", "anthropic", or "local"
provider = "local"

# Analysis strictness
temperature = 0.1       # Low temperature for factual, technical responses
max_tokens = 1000       # Cap response length
timeout_seconds = 20    # Fail fast if AI is unresponsive

[ai.privacy]
# Data Redaction: Patterns to mask before sending context to LLM
# Default includes common secret keys.
redact_patterns = ["password", "token", "secret", "key", "auth"]
# If true, the tool prints the exact prompt to stdout for audit before sending.
audit_mode = false

# Provider-specific configurations
[ai.providers.local]
# Perfect for air-gapped environments or privacy-sensitive orgs
base_url = "http://localhost:11434/v1"  # e.g., Ollama
model = "llama3:instruct"

[ai.providers.openai]
api_key_env = "OPENAI_API_KEY"  # Read key from this env var
model = "gpt-4-turbo"

[ai.providers.gemini]
api_key_env = "GEMINI_API_KEY"
model = "gemini-pro"
```

## 3. Integration Architecture

The `LLMAnalyzer` is implemented as a **final, optional stage** in the diagnosis pipeline. It does not replace the deterministic `ScoringEngine`; it augments it.

```mermaid
graph LR
    A[Collectors] --> B[Scoring Engine]
    B --> C[DiagnosisResult (Deterministic)]
    C --> D{Config: ai.enabled?}
    D -- No (Default) --> E[Renderer]
    D -- Yes --> F[Sanitizer]
    F --> G[LLM Client]
    G --> H[AI Insight]
    H --> E
```

### The Sanitization Layer
Before any data leaves the internal memory structure:
1.  **Redaction:** Recursively walks the `DiagnosisResult` object. Keys matching `ai.privacy.redact_patterns` have their values replaced with `[REDACTED]`.
2.  **Minimization:** Only relevant fields (Status, Events, Logs, Root Cause) are selected. Raw, noisy metadata (managedFields, annotations) is stripped to reduce token usage and data leakage.

## 4. Feature Specification

When enabled, the AI Analyzer provides specific enhancements:

### A. Contextual Log Synthesis
*   **Problem:** 50 lines of logs with mixed "Errors" and "Warnings".
*   **Deterministic View:** Lists unique lines with "Error" keyword.
*   **AI Augmented View:** "The logs indicate a cascading failure. The initial `Connection Refused` to Redis caused the worker thread to panic, which is why you see the subsequent stack traces."

### B. Root Cause Explanation
*   **Problem:** Complex interaction between Taints, Affinity, and Resource Quotas.
*   **Deterministic View:** "FailedScheduling (Score: 90)".
*   **AI Augmented View:** "The Pod is pending because it requests a GPU node (via affinity), but the only available GPU node has a taint `special-hardware=true:NoSchedule` which this Pod does not tolerate."

## 5. Implementation Roadmap

1.  **Configuration Loader:** Implement `ConfigManager` to read/validate `config.toml`.
2.  **Privacy/Sanitization Engine:** Build the robust redaction logic *before* integrating any API.
3.  **Local LLM Support:** Prioritize "Local/Ollama" provider implementation first to validate the "Offline-Capable" promise.
4.  **Cloud Providers:** Add adapters for OpenAI/Gemini as secondary options.