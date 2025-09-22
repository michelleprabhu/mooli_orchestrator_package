import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner"; // optional; remove if not installed

/*
 FastAPI integration guide (suggested endpoints)
 ------------------------------------------------------------
 - GET    /api/gateway/config
      Returns the current RouterConfig (omit secrets). Use on mount to bootstrap UI.
 - POST   /api/gateway/config
      Saves RouterConfig. Server should handle secret storage and validation.
 - POST   /api/gateway/test
      Body: { provider, apiKey?, model? } -> returns { ok, latencyMs, message }.
 - POST   /api/gateway/route/preview
      Body: { input, metadata? } -> returns { provider, model, reason }.
 - POST   /api/gateway/secret (optional)
      Body: { provider, apiKey } -> store secrets; returns { ok }.
*/
// ------------------------------------------------------------
// Types
// ------------------------------------------------------------
export type Provider = "openai" | "anthropic" | "gemini";

export interface ProviderConfig {
  enabled: boolean;
  apiKey: string; // NOTE: collect only; store securely on the server.
  defaultModel: string;
}

export type DynamicStrategy = "value" | "smart" | "turbo";

export interface RouterConfig {
  enabled: boolean;
  mode: "static" | "dynamic";
  providers: Record<Provider, ProviderConfig>;
  dynamic: {
    strategy: DynamicStrategy;
  };
}

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------
const ORANGE = "#FF7A1A";

const DEFAULT_CONFIG: RouterConfig = {
  enabled: true,
  mode: "static",
  providers: {
    openai: { enabled: true, apiKey: "", defaultModel: "gpt-4o-mini" },
    anthropic: { enabled: false, apiKey: "", defaultModel: "claude-3-5-sonnet" },
    gemini: { enabled: false, apiKey: "", defaultModel: "gemini-1.5-flash" },
  },
  dynamic: { strategy: "smart" },
};

const MODEL_OPTIONS: Record<Provider, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4o", "o4-mini", "gpt-3.5-turbo"],
  anthropic: ["claude-3-5-haiku", "claude-3-5-sonnet", "claude-3-opus"],
  gemini: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"],
};

// Mask API key when rendering JSON preview
const mask = (s: string) => (s ? `${s.slice(0, 3)}••••${s.slice(-2)}` : "");

// Back-compat migration for previously saved values
const migrateStrategy = (s: any): DynamicStrategy => {
  switch (s) {
    case "low_cost":
      return "value";
    case "optimum":
      return "smart";
    case "best_performance":
      return "turbo";
    case "value":
    case "smart":
    case "turbo":
      return s;
    default:
      return "smart";
  }
};

// Gating helpers for tests and clarity
export const canUseProviders = (mode: RouterConfig["mode"]) => mode === "static";
export const canUseDynamic = (mode: RouterConfig["mode"]) => mode === "dynamic";

// ------------------------------------------------------------
// Component
// ------------------------------------------------------------
export interface LLMRouterSettingsPageProps {
  initialConfig?: Partial<RouterConfig>;
  onSave?: (config: RouterConfig) => void; // Use this to POST to your backend (e.g., FastAPI)
}

export default function LLMRouterSettingsPage({
  initialConfig = DEFAULT_CONFIG,
  onSave
}: LLMRouterSettingsPageProps = {}) {
  const [config, setConfig] = useState<RouterConfig>(() => ({
    ...DEFAULT_CONFIG,
    ...initialConfig,
    providers: {
      ...DEFAULT_CONFIG.providers,
      ...(initialConfig?.providers || {}),
    },
    dynamic: { ...DEFAULT_CONFIG.dynamic, ...(initialConfig?.dynamic || {}) },
  }));

  // Load configuration from backend on mount
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch('/api/gateway/config');
        if (response.ok) {
          const backendConfig = await response.json();
          setConfig(prevConfig => ({
            ...prevConfig,
            ...backendConfig,
            providers: {
              ...prevConfig.providers,
              ...backendConfig.providers,
            },
          }));
        }
      } catch (error) {
        console.error('Failed to load config from backend:', error);
        toast("Failed to load configuration from backend");
      }
    };

    loadConfig();
  }, []);

  // Persist locally (optional)
  useEffect(() => {
    try {
      localStorage.setItem("llm-router-config", JSON.stringify(config));
    } catch {}
  }, [config]);

  // Load from localStorage if present (optional)
  // TODO[FastAPI]: Prefer bootstrapping from your server. Example:
  // fetch('/api/gateway/config')
  //   .then(r => (r.ok ? r.json() : Promise.reject(r)))
  //   .then(server => setConfig(c => ({ ...c, ...server })))
  //   .catch(() => {});
  useEffect(() => {
    try {
      const raw = localStorage.getItem("llm-router-config");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.dynamic?.strategy) parsed.dynamic.strategy = migrateStrategy(parsed.dynamic.strategy);
        setConfig((c) => ({ ...c, ...parsed }));
      }
    } catch {}
  }, []);


  const saveConfig = async () => {
    if (onSave) onSave(config);

    // Save to backend
    try {
      const response = await fetch('/api/gateway/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });

      if (response.ok) {
        toast("Configuration saved successfully");
      } else {
        const error = await response.text();
        toast("Save failed: " + error);
      }
    } catch (error) {
      console.error('Network error:', error);
      toast("Network error occurred while saving");
    }
    console.log("Gateway Config", config);
  };

  const resetConfig = () => setConfig(DEFAULT_CONFIG);

  // Utilities to update nested state with gating
  const updateProvider = (p: Provider, patch: Partial<ProviderConfig>) =>
    setConfig((prev) => {
      if (!canUseProviders(prev.mode)) return prev; // prevent updates when Dynamic is selected
      return {
        ...prev,
        providers: { ...prev.providers, [p]: { ...prev.providers[p], ...patch } },
      };
    });

  const setDynamicStrategy = (s: DynamicStrategy) =>
    setConfig((prev) => (canUseDynamic(prev.mode) ? { ...prev, dynamic: { strategy: s } } : prev));

  const ProviderCard = ({ p, title, description }: { p: Provider; title: string; description: string }) => {
    const pc = config.providers[p];
    const models = MODEL_OPTIONS[p];
    const disabled = !canUseProviders(config.mode);

    return (
      <Card className={`bg-[#1A1F25] border border-white/5 rounded-2xl ${disabled ? "opacity-50" : ""}`} aria-disabled={disabled}>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-[#E6E8EB] text-lg">{title}</CardTitle>
              <CardDescription className="text-[#A0A6AD]">{description}</CardDescription>
            </div>
            <div className="flex items-center gap-3">
              {/* TODO[FastAPI]: Optional "Test Connection" button ->
                  fetch('/api/gateway/test', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: p, apiKey: pc.apiKey, model: pc.defaultModel }) })
                    .then(r => r.json()).then(res => res.ok ? toast.success('Test passed') : toast.error(res.message || 'Test failed')); */}
              <Label className="text-[#A0A6AD]">Enable</Label>
              <Switch
                disabled={disabled}
                checked={pc.enabled}
                onCheckedChange={(v) => updateProvider(p, { enabled: v })}
                className="data-[state=checked]:bg-[var(--accent)]"
                style={{ '--accent': ORANGE }}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label className="text-[#E6E8EB]">Default Model</Label>
            <div className="flex gap-2">
              <Select
                disabled={disabled}
                value={models.includes(pc.defaultModel) ? pc.defaultModel : "__custom__"}
                onValueChange={(v) =>
                  v === "__custom__"
                    ? updateProvider(p, { defaultModel: pc.defaultModel || models[0] })
                    : updateProvider(p, { defaultModel: v })
                }
              >
                <SelectTrigger className="bg-[#14181E] border-white/10 text-[#E6E8EB] data-[placeholder]:text-[#79818A]">
                  <SelectValue placeholder="Choose model" />
                </SelectTrigger>
                <SelectContent className="bg-[#14181E] text-[#E6E8EB] border-white/10">
                  {models.map((m) => (
                    <SelectItem key={m} value={m} className="focus:bg-white/5">
                      {m}
                    </SelectItem>
                  ))}
                  <SelectItem value="__custom__" className="text-[#A0A6AD]">Custom…</SelectItem>
                </SelectContent>
              </Select>
              {(!models.includes(pc.defaultModel) || pc.defaultModel === "__custom__") && (
                <Input
                  disabled={disabled}
                  placeholder="custom model id"
                  className="bg-[#14181E] border-white/10 text-[#E6E8EB] placeholder:text-[#79818A]"
                  value={pc.defaultModel === "__custom__" ? "" : pc.defaultModel}
                  onChange={(e) => updateProvider(p, { defaultModel: e.target.value })}
                />
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-[#E6E8EB]">API Key</Label>
            {/* TODO[FastAPI]: Never store API keys in localStorage. Send to a server-side secrets endpoint.
                Example: POST /api/gateway/secret { provider, apiKey } */}
            <Input
              disabled={disabled}
              type="password"
              placeholder={`Enter ${title} API key`}
              className="bg-[#14181E] border-white/10 text-[#E6E8EB] tracking-widest placeholder:text-[#79818A]"
              value={pc.apiKey}
              onChange={(e) => updateProvider(p, { apiKey: e.target.value })}
            />
            <p className="text-xs text-[#79818A]">Store securely on server/secret manager. This page only collects input.</p>
          </div>
        </CardContent>
      </Card>
    );
  };

  const DynamicCard = ({ title, value, description }: { title: string; value: DynamicStrategy; description: string }) => {
    const disabled = !canUseDynamic(config.mode);
    const selected = config.dynamic.strategy === value;

    return (
      <div
        className={`p-4 rounded-xl border ${selected ? "bg-white/5" : "border-white/10 bg-[#14181E]"} ${disabled ? "opacity-50 pointer-events-none" : ""}`}
        style={{ borderColor: selected ? ORANGE : undefined }}
        aria-disabled={disabled}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-[#E6E8EB]">{title}</h3>
          <input
            type="radio"
            className="accent-[#FF7A1A]"
            disabled={disabled}
            checked={selected}
            onChange={() => setDynamicStrategy(value)}
          />
        </div>
        <p className={`text-sm mt-2 ${disabled ? "text-[#6b7280]" : "text-[#A0A6AD]"}`}>
          <span className="font-medium">Selection:</span> {description}
        </p>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#0F1117] text-[#E6E8EB]">
      {/* Top Bar */}
      <div className="sticky top-0 z-10 backdrop-blur bg-[#0F1117]/85 border-b border-white/5">
        <div className="mx-auto max-w-6xl px-5 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Optimiser Gateway</h1>
            <p className="text-sm text-[#A0A6AD]">Configure provider keys, default models, and dynamic optimizing strategy.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Label className="text-[#A0A6AD]">Enable Optimizer Gateway</Label>
              <Switch
                checked={config.enabled}
                onCheckedChange={(v) => setConfig((c) => ({ ...c, enabled: v }))}
                className="data-[state=checked]:bg-[var(--accent)]"
                style={{ '--accent': ORANGE }}
              />
            </div>
            <Button
              onClick={resetConfig}
              variant="outline"
              className="bg-[#14181E] border-white/10 text-[#E6E8EB] hover:bg:white/5 focus-visible:ring-0"
            >
              Reset
            </Button>
            <Button
              onClick={saveConfig}
              className="bg-[#FF7A1A] hover:bg-[#ff8a3a] text:black"
            >
              Update
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-6xl px-5 py-6 space-y-6">
        <Card className="bg-[#1A1F25] border border-white/5 rounded-2xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-[#E6E8EB] text-lg">Optimizer Mode</CardTitle>
            <CardDescription className="text-[#A0A6AD]">Choose between direct provider usage (Static) or automatic model selection (Dynamic).</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={config.mode} onValueChange={(v: "static" | "dynamic") => setConfig((c) => ({ ...c, mode: v }))} className="w-full">
              <TabsList className="bg-[#14181E] border border:white/10 text-[#A0A6AD] rounded-xl p-1">
                <TabsTrigger value="static" className="px-3 py-1.5 rounded-lg bg-transparent text-[#A0A6AD] data-[state=active]:bg-[#1A1F25] data-[state=active]:text-[#E6E8EB] data-[state=active]:border data-[state=active]:border-white/10 hover:text-[#E6E8EB] focus-visible:ring-0">Static</TabsTrigger>
                <TabsTrigger value="dynamic" className="px-3 py-1.5 rounded-lg bg-transparent text-[#A0A6AD] data-[state=active]:bg-[#1A1F25] data-[state=active]:text-[#E6E8EB] data-[state=active]:border data-[state=active]:border-white/10 hover:text-[#E6E8EB] focus-visible:ring-0">Dynamic</TabsTrigger>
              </TabsList>

              {/* STATIC MODE */}
              <TabsContent value="static" className="pt-4 space-y-4">
                <div className="grid grid-cols-1 gap-4">
                  <ProviderCard p="openai" title="OpenAI" description="Select default model and provide API key." />
                  <ProviderCard p="anthropic" title="Anthropic Claude" description="Select default model and provide API key." />
                  <ProviderCard p="gemini" title="Google Gemini" description="Select default model and provide API key." />
                </div>
              </TabsContent>

              {/* DYNAMIC MODE */}
              <TabsContent value="dynamic" className="pt-4 space-y-4">
                <Card className="bg-[#1A1F25] border border-white/5 rounded-2xl">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-[#E6E8EB] text-lg">Dynamic Strategy</CardTitle>
                    <CardDescription className="text-[#A0A6AD]">Gateway will select a model based on the chosen strategy.</CardDescription>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* TODO[FastAPI]: You may expose a "Route Preview" action that calls
                        POST /api/gateway/route/preview with a sample input to show which provider/model would be chosen. */}
                    <DynamicCard title="Value" value="value" description="cost-first with caching/compression." />
                    <DynamicCard title="Smart" value="smart" description="balanced on context size and task complexity." />
                    <DynamicCard title="Turbo" value="turbo" description="quality-first with tool-use/parallelism." />
                  </CardContent>
                </Card>

              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}

// Simple sanity tests (run in console): window.runRouterConfigTests?.()
export function runRouterConfigTests() {
  const cfg: RouterConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
  const errors: string[] = [];

  // Test 1: mask() should hide API keys
  const masked = mask("sk-abcdef");
  if (!masked.startsWith("sk-") || !masked.endsWith("ef") || masked.includes("abcd")) {
    errors.push("mask() did not mask as expected");
  }

  // Additional mask test
  if (mask("") !== "") {
    errors.push("mask('') should return empty string");
  }

  // Test 2: provider defaults exist
  (Object.keys(cfg.providers) as Provider[]).forEach((p) => {
    if (typeof cfg.providers[p].defaultModel !== "string") errors.push(`missing defaultModel for ${p}`);
  });

  // Test 3: dynamic strategies enum
  const allowed: DynamicStrategy[] = ["value", "smart", "turbo"];
  if (!allowed.includes(cfg.dynamic.strategy)) errors.push("invalid dynamic.strategy default");

  // Test 4: migrateStrategy back-compat
  const legacy = ["low_cost", "optimum", "best_performance", "value", "smart", "turbo"];
  const migrated = legacy.map((s) => migrateStrategy(s as any));
  if (JSON.stringify(migrated) !== JSON.stringify(["value", "smart", "turbo", "value", "smart", "turbo"])) {
    errors.push("migrateStrategy mapping is incorrect");
  }

  // Test 5: gating helpers
  if (!(canUseProviders("static") && !canUseProviders("dynamic") && canUseDynamic("dynamic") && !canUseDynamic("static"))) {
    errors.push("gating helpers returned incorrect booleans");
  }

  const result = { passed: errors.length === 0, errors };
  console.log("LLM Router tests:", result);
  return result;
}
