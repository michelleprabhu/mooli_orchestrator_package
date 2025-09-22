import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { CacheToggle } from "@/components/ui/cache-toggle"
import {
  CacheCard,
  CacheCardContent,
  CacheCardDescription,
  CacheCardHeader,
  CacheCardTitle
} from "@/components/ui/cache-card"
import { toast } from "@/hooks/use-toast"
import { Trash2, Download, Activity, RefreshCw } from "lucide-react"

interface CacheConfig {
  enabled: boolean
  threshold: number // UI: percentage (0–100)
  defaultTtl: number
}

interface HealthStatus {
  status: string
  redis: string
  uptime_seconds: number
  key_count: number
  cache_enabled: boolean
}

export const ConfigurationCache = () => {
  const [config, setConfig] = useState<CacheConfig>({
    enabled: true,
    threshold: 75,
    defaultTtl: 3600
  })
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Fetch health + config
  const fetchHealth = async () => {
    try {
      const res = await fetch("/api/v1/cache/health")
      if (res.ok) {
        const data = await res.json()
        setHealth({
          status: data.status || 'unknown',
          redis: data.redis_connected ? 'connected' : 'disconnected',
          uptime_seconds: data.uptime_seconds || 0,
          key_count: data.total_keys || 0,
          cache_enabled: data.cache_enabled || false
        })
      }
    } catch (error) {
      console.error("Failed to fetch health:", error)
    }
  }

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch("/api/v1/cache/config")
        if (res.ok) {
          const data = await res.json()
          setConfig({
            enabled: data.enabled,
            threshold: Math.round((data.similarity_threshold ?? 0) * 100),
            defaultTtl: data.default_ttl_seconds ?? 3600
          })
        }
      } catch (error) {
        console.error("Failed to fetch configuration:", error)
      }
    }

    fetchConfig()
    fetchHealth()
    const interval = setInterval(fetchHealth, 30000) // auto refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const handleToggleCache = async (enabled: boolean) => {
    setConfig(prev => ({ ...prev, enabled }))
    try {
      await fetch("/api/v1/cache/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
      })
      toast({
        title: enabled ? "Cache Enabled" : "Cache Disabled",
        description: `LLM Cache system is now ${enabled ? "active" : "inactive"}`
      })
    } catch {
      toast({
        title: "Error",
        description: "Failed to update cache configuration",
        variant: "destructive"
      })
    }
  }

  const handleUpdateConfig = async () => {
    setIsLoading(true)
    try {
      const payload = {
        default_ttl_seconds: config.defaultTtl,
        similarity_threshold: config.threshold / 100
      }
      await fetch("/api/v1/cache/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
      toast({
        title: "Configuration Updated",
        description: "Cache settings have been successfully updated"
      })
    } catch {
      toast({
        title: "Error",
        description: "Failed to update configuration",
        variant: "destructive"
      })
    }
    setIsLoading(false)
  }

  const handleClearCache = async () => {
    setIsLoading(true)
    try {
      await fetch("/api/v1/cache/keys", { method: "DELETE" })
      toast({
        title: "Cache Cleared",
        description: "All cached entries have been removed"
      })
    } catch {
      toast({
        title: "Error",
        description: "Failed to clear cache",
        variant: "destructive"
      })
    }
    setIsLoading(false)
  }

  const handleExportCache = async () => {
    try {
      const response = await fetch("/api/v1/cache/export/json")
      if (!response.ok) throw new Error()
      const data = await response.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json"
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "cache-export.json"
      a.click()
      URL.revokeObjectURL(url)
      toast({
        title: "Cache Exported",
        description: "Cache data has been downloaded"
      })
    } catch {
      toast({
        title: "Error",
        description: "Failed to export cache",
        variant: "destructive"
      })
    }
  }

  return (
    <div className="space-y-6">
      {/* Health Status */}
      <CacheCard>
        <CacheCardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CacheCardTitle>System Health</CacheCardTitle>
              <CacheCardDescription>
                Redis connection and cache service status
              </CacheCardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Activity
                className={`h-6 w-6 ${
                  health?.redis === "connected"
                    ? "text-green-500"
                    : "text-red-500"
                }`}
              />
              <Button size="sm" variant="ghost" onClick={fetchHealth}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CacheCardHeader>
        {health && (
          <CacheCardContent>
            <div className="space-y-2">
              <p className="text-foreground"><span className="text-muted-foreground">Status:</span> {health.status}</p>
              <p className="text-foreground"><span className="text-muted-foreground">Redis:</span> {health.redis}</p>
              <p className="text-foreground"><span className="text-muted-foreground">Downtime:</span> {health.uptime_seconds}s</p>
              <p className="text-foreground"><span className="text-muted-foreground">Keys in cache:</span> {health.key_count}</p>
              <p className="text-foreground"><span className="text-muted-foreground">Cache Enabled:</span> {health.cache_enabled ? "Yes" : "No"}</p>
            </div>
          </CacheCardContent>
        )}
      </CacheCard>

      {/* Cache System Status */}
      <CacheCard>
        <CacheCardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CacheCardTitle>Enable Cache System</CacheCardTitle>
              <CacheCardDescription>
                Turn on/off main cache functionality
              </CacheCardDescription>
            </div>
            <CacheToggle
              checked={config.enabled}
              onCheckedChange={handleToggleCache}
            />
          </div>
        </CacheCardHeader>
      </CacheCard>

      {/* Cache Configuration */}
      <CacheCard>
        <CacheCardHeader>
          <CacheCardTitle>Cache Configuration</CacheCardTitle>
          <CacheCardDescription>
            Configure cache thresholds and TTL settings
          </CacheCardDescription>
        </CacheCardHeader>
        <CacheCardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="threshold" className="text-foreground">
                Cache Threshold (%)
              </Label>
              <p className="text-xs text-muted-foreground">
                Similarity score (0-100%) required for a cached response to be used. Higher values mean stricter matching - only very similar prompts will get cached responses.
              </p>
              <Input
                id="threshold"
                type="number"
                min="0"
                max="100"
                value={config.threshold}
                onChange={e =>
                  setConfig(prev => ({
                    ...prev,
                    threshold: parseInt(e.target.value) || 0
                  }))
                }
                className="bg-input border-border text-foreground placeholder-muted-foreground"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ttl" className="text-foreground">
                Default TTL (seconds)
              </Label>
              <p className="text-xs text-muted-foreground">
                Time-To-Live: How long cached responses remain valid before expiring. Set to 3600 for 1 hour, 86400 for 24 hours.
              </p>
              <Input
                id="ttl"
                type="number"
                min="0"
                value={config.defaultTtl}
                onChange={e =>
                  setConfig(prev => ({
                    ...prev,
                    defaultTtl: parseInt(e.target.value) || 0
                  }))
                }
                className="bg-input border-border text-foreground placeholder-muted-foreground"
              />
            </div>
          </div>
          <div className="flex justify-end mt-6">
            <Button
              onClick={handleUpdateConfig}
              disabled={isLoading}
              className="bg-primary hover:bg-primary/80 text-primary-foreground"
            >
              Update Configuration
            </Button>
          </div>
        </CacheCardContent>
      </CacheCard>

      {/* Cache Operations */}
      <CacheCard>
        <CacheCardHeader>
          <CacheCardTitle>Cache Operations</CacheCardTitle>
          <CacheCardDescription>
            Manage cache data and perform maintenance operations
          </CacheCardDescription>
        </CacheCardHeader>
        <CacheCardContent>
          <div className="flex gap-4">
            <Button
              onClick={handleClearCache}
              disabled={isLoading}
              variant="destructive"
              className="flex items-center gap-2"
            >
              <Trash2 className="h-4 w-4" />
              Clear Cache
            </Button>
            <Button
              onClick={handleExportCache}
              disabled={isLoading}
              variant="secondary"
              className="flex items-center gap-2"
            >
              <Download className="h-4 w-4" />
              Export Cache
            </Button>
          </div>
        </CacheCardContent>
      </CacheCard>
    </div>
  )
}