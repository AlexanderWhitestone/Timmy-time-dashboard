/**
 * local_llm.js — In-browser LLM inference via WebLLM.
 *
 * Loads a small language model directly into the browser using WebGPU
 * (or WASM fallback) so Timmy can run on an iPhone with zero server
 * dependency.  Falls back to server-side Ollama when the local model
 * is unavailable.
 *
 * Usage:
 *   const llm = new LocalLLM({ modelId, onProgress, onReady, onError });
 *   await llm.init();
 *   const reply = await llm.chat("Hello Timmy");
 */

/* global webllm */

// ── Model catalogue ────────────────────────────────────────────────────────
// Models tested on iPhone 15 Pro / Safari 26+.  Sorted smallest → largest.
const MODEL_CATALOGUE = [
  {
    id: "SmolLM2-360M-Instruct-q4f16_1-MLC",
    label: "SmolLM2 360M (fast)",
    sizeHint: "~200 MB",
    description: "Fastest option. Good for simple Q&A.",
  },
  {
    id: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC",
    label: "Qwen 2.5 0.5B (balanced)",
    sizeHint: "~350 MB",
    description: "Best quality under 500 MB.",
  },
  {
    id: "SmolLM2-1.7B-Instruct-q4f16_1-MLC",
    label: "SmolLM2 1.7B (smart)",
    sizeHint: "~1 GB",
    description: "Highest quality. Needs more memory.",
  },
  {
    id: "Llama-3.2-1B-Instruct-q4f16_1-MLC",
    label: "Llama 3.2 1B",
    sizeHint: "~700 MB",
    description: "Meta's compact model. Good all-rounder.",
  },
];

// ── Capability detection ──────────────────────────────────────────────────
function detectWebGPU() {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

function detectWASM() {
  try {
    return typeof WebAssembly === "object" && typeof WebAssembly.instantiate === "function";
  } catch {
    return false;
  }
}

// ── LocalLLM class ────────────────────────────────────────────────────────
class LocalLLM {
  /**
   * @param {object}   opts
   * @param {string}   opts.modelId     — WebLLM model ID
   * @param {function} opts.onProgress  — (report) progress during download
   * @param {function} opts.onReady     — () called when model is loaded
   * @param {function} opts.onError     — (error) called on fatal error
   * @param {string}   opts.systemPrompt — system message for the model
   */
  constructor(opts = {}) {
    this.modelId = opts.modelId || "SmolLM2-360M-Instruct-q4f16_1-MLC";
    this.onProgress = opts.onProgress || (() => {});
    this.onReady = opts.onReady || (() => {});
    this.onError = opts.onError || (() => {});
    this.systemPrompt =
      opts.systemPrompt ||
      "You are Timmy, a sovereign AI assistant. You are helpful, concise, and loyal. " +
      "Address the user as 'Sir' when appropriate. Keep responses brief on mobile.";

    this.engine = null;
    this.ready = false;
    this.loading = false;
    this._hasWebGPU = detectWebGPU();
    this._hasWASM = detectWASM();
  }

  /** Check if local inference is possible on this device. */
  static isSupported() {
    return detectWebGPU() || detectWASM();
  }

  /** Return the model catalogue for UI rendering. */
  static getCatalogue() {
    return MODEL_CATALOGUE;
  }

  /** Return runtime capability info. */
  getCapabilities() {
    return {
      webgpu: this._hasWebGPU,
      wasm: this._hasWASM,
      supported: this._hasWebGPU || this._hasWASM,
      backend: this._hasWebGPU ? "WebGPU" : this._hasWASM ? "WASM" : "none",
    };
  }

  /**
   * Initialize the engine and download/cache the model.
   * Model weights are cached in the browser's Cache API so subsequent
   * loads are nearly instant.
   */
  async init() {
    if (this.ready) return;
    if (this.loading) return;

    if (!this._hasWebGPU && !this._hasWASM) {
      const err = new Error(
        "Neither WebGPU nor WebAssembly is available. " +
        "Update to iOS 26+ / Safari 26+ for WebGPU support."
      );
      this.onError(err);
      throw err;
    }

    this.loading = true;

    try {
      // Dynamic import of WebLLM from CDN (avoids bundling)
      if (typeof webllm === "undefined") {
        await this._loadWebLLMScript();
      }

      const initProgressCallback = (report) => {
        this.onProgress(report);
      };

      this.engine = await webllm.CreateMLCEngine(this.modelId, {
        initProgressCallback,
      });

      this.ready = true;
      this.loading = false;
      this.onReady();
    } catch (err) {
      this.loading = false;
      this.ready = false;
      this.onError(err);
      throw err;
    }
  }

  /**
   * Send a chat message and get a response.
   * @param {string} userMessage
   * @param {object} opts
   * @param {function} opts.onToken — streaming callback (delta)
   * @returns {Promise<string>} full response text
   */
  async chat(userMessage, opts = {}) {
    if (!this.ready) {
      throw new Error("Model not loaded. Call init() first.");
    }

    const messages = [
      { role: "system", content: this.systemPrompt },
      { role: "user", content: userMessage },
    ];

    if (opts.onToken) {
      // Streaming mode
      let fullText = "";
      const chunks = await this.engine.chat.completions.create({
        messages,
        stream: true,
        temperature: 0.7,
        max_tokens: 512,
      });

      for await (const chunk of chunks) {
        const delta = chunk.choices[0]?.delta?.content || "";
        fullText += delta;
        opts.onToken(delta, fullText);
      }
      return fullText;
    }

    // Non-streaming mode
    const response = await this.engine.chat.completions.create({
      messages,
      temperature: 0.7,
      max_tokens: 512,
    });

    return response.choices[0]?.message?.content || "";
  }

  /** Reset conversation context. */
  async resetChat() {
    if (this.engine) {
      await this.engine.resetChat();
    }
  }

  /** Unload the model and free memory. */
  async unload() {
    if (this.engine) {
      await this.engine.unload();
      this.engine = null;
      this.ready = false;
    }
  }

  /** Get current engine stats (tokens/sec, memory, etc). */
  async getStats() {
    if (!this.engine) return null;
    try {
      const stats = await this.engine.runtimeStatsText();
      return stats;
    } catch {
      return null;
    }
  }

  // ── Private ─────────────────────────────────────────────────────────────

  /** Load the WebLLM script from CDN. */
  _loadWebLLMScript() {
    return new Promise((resolve, reject) => {
      // Check if already loaded
      if (typeof webllm !== "undefined") {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src =
        "https://esm.run/@anthropic-ai/sdk" !== script.src
          ? "https://esm.run/@anthropic-ai/sdk"
          : "";
      // Use the WebLLM CDN bundle
      script.type = "module";
      script.textContent = `
        import * as webllmModule from "https://esm.run/@mlc-ai/web-llm";
        window.webllm = webllmModule;
        window.dispatchEvent(new Event("webllm-loaded"));
      `;
      document.head.appendChild(script);

      const onLoaded = () => {
        window.removeEventListener("webllm-loaded", onLoaded);
        resolve();
      };
      window.addEventListener("webllm-loaded", onLoaded);

      // Fallback: also try the UMD bundle approach
      const fallbackScript = document.createElement("script");
      fallbackScript.src = "https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.80/lib/index.min.js";
      fallbackScript.onload = () => {
        if (typeof webllm !== "undefined") {
          resolve();
        }
      };
      fallbackScript.onerror = () => {
        reject(new Error("Failed to load WebLLM library from CDN."));
      };
      document.head.appendChild(fallbackScript);
    });
  }
}

// Export for use in templates
window.LocalLLM = LocalLLM;
window.LOCAL_MODEL_CATALOGUE = MODEL_CATALOGUE;
