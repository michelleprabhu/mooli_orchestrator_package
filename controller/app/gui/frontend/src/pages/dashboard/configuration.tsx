"use client"

import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"

import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { RefreshCw, Server, PlugZap, Activity, Database, TrendingUp } from "lucide-react"

import { ResponsiveContainer, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from "recharts"

/* ----------------------------- Types ----------------------------- */
type HealthResp = { status?: string; service?: string; timestamp?: string }
type InternalHealthResp = { success?: boolean; ws?: { status?: string; error?: string }; message?: string }

type OverviewResp = {
  success: boolean
  data?: {
    period: { start: string; end: string }
    active_organizations: number
    total_cost: number
    total_requests: number
    system_health: number
  }
}

type OrgItem = {
  organization_id: string
  name: string
  status: string
  last_seen?: string | null
  features?: Record<string, any>
}

type OrgsResp = {
  success: boolean
  data?: {
    items: OrgItem[]
    page: number
    page_size: number
    total_items: number
    total_pages: number
  }
}

type OrchRow = {
  orchestrator_id: string
  organization_id: string
  name: string
  status: string
  health_status: string
  last_seen?: string | null
  metadata?: Record<string, any>
}

type OrchestratorsResp = {
  success: boolean
  data?: {
    items: OrchRow[]
  }
}

type LiveResp = {
  success: boolean
  data?: {
    orchestrators: Record<
      string,
      { organization_id: string; name: string; status: string; last_seen?: string; metadata?: Record<string, any> }
    >
    total_count: number
  }
}

/* ---------- Helpers ---------- */
const MetricCard = ({
  icon: Icon,
  title,
  value,
  subtitle,
  status,
  trend,
}: {
  icon: any
  title: string
  value: string | number
  subtitle: string
  status?: "good" | "warning" | "error"
  trend?: "up" | "down" | "stable"
}) => (
  <Card className="p-6 hover:shadow-lg transition-all duration-200 border border-border bg-card">
    <div className="flex items-start justify-between">
      <div className="flex items-center gap-3">
        <div
          className={`p-2 rounded-lg ${
            status === "good"
              ? "bg-green-500/20 text-green-400"
              : status === "warning"
                ? "bg-amber-500/20 text-amber-400"
                : status === "error"
                  ? "bg-red-500/20 text-red-400"
                  : "bg-gray-500/20 text-gray-400"
          }`}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <div className="font-semibold text-foreground">{title}</div>
          <div className="text-2xl font-bold text-foreground mt-1">{value}</div>
        </div>
      </div>
      {trend && (
        <div
          className={`flex items-center gap-1 text-sm ${
            trend === "up" ? "text-green-400" : trend === "down" ? "text-red-400" : "text-gray-400"
          }`}
        >
          <TrendingUp className="h-4 w-4" />
        </div>
      )}
    </div>
    <div className="mt-4 text-sm text-muted-foreground">{subtitle}</div>
  </Card>
)

/* --------------------------------- Page ---------------------------------- */
export default function Configurations() {
  const [loading, setLoading] = useState(true)

  const [controllerHealth, setControllerHealth] = useState<HealthResp | null>(null)
  const [internalHealth, setInternalHealth] = useState<InternalHealthResp | null>(null)
  const [overview, setOverview] = useState<OverviewResp["data"] | null>(null)

  const [orgs, setOrgs] = useState<OrgItem[]>([])
  const [orchestrators, setOrchestrators] = useState<OrchRow[]>([])
  const [liveOrgIds, setLiveOrgIds] = useState<Set<string>>(new Set())

  const loadAll = async () => {
    setLoading(true)
    try {
      const [ctrl, intr, ovw, orgsRes, orchsRes, liveRes] = await Promise.all([
        api.get<HealthResp>("/api/v1/controller/health").catch(() => ({ data: {} as any })),
        api.get<InternalHealthResp>("/api/v1/internal/health").catch(() => ({ data: {} as any })),
        api.get<OverviewResp>("/api/v1/controller/overview").catch(() => ({ data: { success: false } as any })),
        api.get<OrgsResp>("/api/v1/controller/organizations", { params: { page_size: 100 } }),
        api.get<OrchestratorsResp>("/api/v1/controller/orchestrators", { params: { page_size: 100 } }),
        api.get<LiveResp>("/api/v1/controller/orchestrators/live").catch(() => ({ data: { success: false } as any })),
      ])

      setControllerHealth(ctrl.data || null)
      setInternalHealth(intr.data || null)
      setOverview(ovw.data?.data ?? null)

      setOrgs(orgsRes.data.data?.items ?? [])
      setOrchestrators(orchsRes.data.data?.items ?? [])

      const liveMap = (liveRes.data?.data?.orchestrators ?? {}) as Record<string, any>
      const s = new Set<string>()
      Object.values(liveMap).forEach((p: any) => {
        const oid = p?.organization_id
        if (oid) s.add(oid)
      })
      setLiveOrgIds(s)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const chartData = useMemo(() => {
    const regCountByOrg: Record<string, number> = {}
    for (const r of orchestrators) {
      const key = r.organization_id
      regCountByOrg[key] = (regCountByOrg[key] || 0) + 1
    }
    return (orgs || []).map((o) => ({
      org: o.name || o.organization_id,
      organization_id: o.organization_id,
      Registered: regCountByOrg[o.organization_id] || 0,
      Live: liveOrgIds.has(o.organization_id) ? 1 : 0,
    }))
  }, [orgs, orchestrators, liveOrgIds])

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header (same as Dashboard/Organizations) */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Configurations</h1>
          <p className="text-muted-foreground mt-1">System status and an overview of organizations.</p>
        </div>
        <Button onClick={loadAll} variant="outline" disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Metric Cards */}
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Server}
          title="Controller Status"
          value={controllerHealth?.status || "unknown"}
          subtitle={
            controllerHealth?.timestamp
              ? `Updated ${new Date(controllerHealth.timestamp).toLocaleString()}`
              : "No recent data"
          }
          status={(controllerHealth?.status || "healthy") === "healthy" ? "good" : "error"}
        />

        <MetricCard
          icon={PlugZap}
          title="WebSocket Bridge"
          value={internalHealth?.ws?.status || "down"}
          subtitle={internalHealth?.message || "Internal API connection"}
          status={(internalHealth?.ws?.status || "down") === "ok" ? "good" : "error"}
        />

        <MetricCard
          icon={Activity}
          title="Active Organizations"
          value={overview?.active_organizations ?? "—"}
          subtitle="Organizations active in the last 30 days"
          status="good"
          trend="up"
        />

        <MetricCard
          icon={Database}
          title="System Health"
          value={overview?.system_health ? `${overview.system_health}%` : "—"}
          subtitle="Overall system performance metric"
          status={
            overview?.system_health
              ? overview.system_health >= 90
                ? "good"
                : overview.system_health >= 70
                  ? "warning"
                  : "error"
              : undefined
          }
        />
      </div>

      {/* Chart */}
      <Card className="p-8 border border-border bg-card">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Organizations Overview</h2>
            <p className="text-muted-foreground mt-1">Registered vs Live orchestrators by organization</p>
          </div>
        </div>

        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="org" tick={{ fontSize: 12, fill: "#9ca3af" }} axisLine={{ stroke: "#4b5563" }} />
              <YAxis tick={{ fontSize: 12, fill: "#9ca3af" }} axisLine={{ stroke: "#4b5563" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  color: "#f9fafb",
                }}
              />
              <Legend />
              <Bar dataKey="Registered" fill="#f97316" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Live" fill="#fb923c" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-400">Loading system data…</span>
        </div>
      )}
    </div>
  )
}
