"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, Users, Activity, DollarSign, BarChart3, Server, Cloud } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

/** -------- Types (match BE) -------- */
type OverviewResp = {
  success: boolean;
  data?: {
    period: { start: string; end: string };
    active_organizations: number;
    total_cost: number;
    total_requests: number;
    system_health: number;
  };
};

type CostsResp = {
  success: boolean;
  data?: {
    granularity: "hour" | "day" | "week" | "month";
    forecast?: { end_of_month_cost: number } | null;
    history?: Array<{ date: string; cost: number }>;
  };
};

type DbOrchestrator = {
  orchestrator_id: string;
  organization_id: string;
  name: string;
  status: "active" | "inactive" | "independent" | string;
  health_status?: string;
  last_seen?: string | null;
  metadata?: Record<string, unknown>;
  is_independent?: boolean;
};

type OrchestratorsResp = {
  success: boolean;
  data?: {
    items: DbOrchestrator[];
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

type OrgsResp = {
  success: boolean;
  data?: {
    items: Array<{ organization_id: string; name: string; status: string; last_seen?: string | null }>;
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
};

type HealthResp = {
  status: string;
  service: string;
  dependencies: { database: string; config: string };
  timestamp: string;
};

/** -------- Helpers -------- */
const fmt = (n?: number) => (n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 });

const timeAgo = (iso?: string | null) => {
  if (!iso) return "not connected";
  const d = new Date(iso);
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
};

/** -------- Component -------- */
export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<OverviewResp["data"]>();
  const [costs, setCosts] = useState<CostsResp["data"]>();
  const [costHistory, setCostHistory] = useState<Array<{ date: string; cost: number }>>([]);

  const [orchRows, setOrchRows] = useState<DbOrchestrator[]>([]);
  const [orgs, setOrgs] = useState<OrgsResp["data"]>();
  const [health, setHealth] = useState<HealthResp | null>(null);

  // derive "live" from DB rows (status computed server-side from last_heartbeat/last_seen)
  const live = useMemo(() => {
    const items = orchRows.map((o) => ({
      orgId: o.organization_id,
      id: o.orchestrator_id,
      name: o.name || o.orchestrator_id,
      status: (o.status as string) || "inactive",
      lastSeen: o.last_seen ?? null,
    }));
    const count = items.filter((i) => i.status === "active").length;
    return { items, count };
  }, [orchRows]);

  useEffect(() => {
    let mounted = true;
    let timer: any;

    const load = async () => {
      try {
        // Load APIs individually to prevent one failure from blocking others
        const [ov, cs, orchs, og, hl] = await Promise.all([
          api.get<OverviewResp>("/api/v1/controller/overview").catch(e => ({ data: { success: false, data: undefined } })),
          api.get<CostsResp>("/api/v1/controller/costs", { params: { include_forecast: true, granularity: "day" } }).catch(e => ({ data: { success: false, data: undefined } })),
          api.get<OrchestratorsResp>("/api/v1/controller/orchestrators", { params: { page_size: 100 } }).catch(e => ({ data: { success: false, data: { items: [] } } })),
          api.get<OrgsResp>("/api/v1/controller/organizations", { params: { page_size: 5 } }).catch(e => ({ data: { success: false, data: { items: [] } } })),
          api.get<HealthResp>("/api/v1/controller/health").catch(e => ({ data: {} })),
        ]);

        if (!mounted) return;

        console.log("Dashboard data loaded:", { 
          overview: ov.data.data, 
          total_cost: ov.data.data?.total_cost 
        });

        setOverview(ov.data.data);
        setCosts(cs.data.data);
        setCostHistory(cs.data.data?.history ?? []);
        setOrchRows(orchs.data.data?.items ?? []);
        setOrgs(og.data.data);
        setHealth(hl.data);
      } catch (err) {
        console.error("dashboard load failed", err);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    // light auto-refresh so the card updates as DB heartbeats land
    timer = setInterval(load, 15000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">Dashboard</h1>
        <p className="text-muted-foreground">Welcome back! Here’s what’s happening with your business today.</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Total Revenue</p>
              <p className="text-2xl font-bold text-foreground">{loading ? "…" : `$${fmt(overview?.total_cost)}`}</p>
            </div>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </div>
        </Card>
        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Subscriptions</p>
              <p className="text-2xl font-bold text-foreground">{loading ? "…" : `+${fmt(overview?.active_organizations)}`}</p>
            </div>
            <Users className="h-4 w-4 text-muted-foreground" />
          </div>
        </Card>
        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Sales</p>
              <p className="text-2xl font-bold text-foreground">{loading ? "…" : `+${fmt(overview?.total_requests)}`}</p>
            </div>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </div>
        </Card>
        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Active Now</p>
              <p className="text-2xl font-bold text-foreground">{loading ? "…" : `+${fmt(overview?.system_health)}`}</p>
            </div>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </div>
        </Card>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">
        {/* Overview block with chart */}
        <Card className="col-span-4 bg-card border-border p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-semibold text-foreground">Cost Trend</h3>
              {!loading && overview?.period && (
                <p className="text-xs text-muted-foreground mt-1">
                  {new Date(overview.period.start).toLocaleString()} — {new Date(overview.period.end).toLocaleString()}
                </p>
              )}
            </div>
            <div className="flex space-x-2">
              <Button variant="outline" size="sm">Week</Button>
              <Button variant="outline" size="sm">Month</Button>
              <Button variant="default" size="sm">Year</Button>
            </div>
          </div>

          <div className="h-[300px]">
            {loading ? (
              <div className="h-full w-full bg-muted/10 rounded-lg flex items-center justify-center">
                <BarChart3 className="h-12 w-12 text-muted-foreground" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={costHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="cost" stroke="#8884d8" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Live list (DB-derived) */}
        <Card className="col-span-3 bg-card border-border p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-foreground">Live Orchestrators</h3>
            <Badge variant="secondary">{loading ? "…" : `${live.count} live`}</Badge>
          </div>
          <div className="space-y-4">
            {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
            {!loading && live.items.length === 0 && (
              <div className="text-sm text-muted-foreground">No orchestrators</div>
            )}
            {live.items.map((o) => (
              <div key={o.id} className="flex items-center space-x-4">
                <div className="w-9 h-9 rounded-full bg-muted/20 flex items-center justify-center">
                  <Server className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">{o.name}</p>
                  <p className="text-xs text-muted-foreground">ID: {o.id} · Org: {o.orgId}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant={
                    o.status === "active" ? "default" : 
                    o.status === "independent" ? "destructive" : 
                    "secondary"
                  }>
                    {o.status === "active" ? "active (heartbeat)" : 
                     o.status === "independent" ? "independent" : 
                     "inactive"}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground">{timeAgo(o.lastSeen)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Bottom grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">Cost Forecast</h3>
            <Badge variant="secondary">{loading ? "…" : (costs?.granularity ?? "day")}</Badge>
          </div>
          <div className="flex items-center justify-between py-2">
            <div className="text-sm text-muted-foreground">End-of-month cost</div>
            <div className="text-sm font-medium text-foreground">
              {loading ? "…" : costs?.forecast?.end_of_month_cost != null ? `$${fmt(costs?.forecast?.end_of_month_cost)}` : "N/A"}
            </div>
          </div>
        </Card>

        <Card className="bg-card border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">Controller Health</h3>
            <Badge variant={health?.status === "healthy" ? "default" : "secondary"}>{health?.status ?? "…"}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <Cloud className="h-4 w-4 text-muted-foreground" />
              <div>
                <div className="text-sm text-muted-foreground">Database</div>
                <div className="text-sm font-medium text-foreground">{health ? health.dependencies.database : "…"}</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Cloud className="h-4 w-4 text-muted-foreground" />
              <div>
                <div className="text-sm text-muted-foreground">Config</div>
                <div className="text-sm font-medium text-foreground">{health ? health.dependencies.config : "…"}</div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {!!orgs?.items?.length && (
        <div className="mt-8">
          <Card className="bg-card border-border p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">Organizations - Config</h3>
            <div className="grid md:grid-cols-2 gap-3">
              {orgs.items.slice(0, 5).map((o) => (
                <div key={o.organization_id} className="flex items-center justify-between p-3 rounded-md border border-border">
                  <div>
                    <div className="text-sm font-medium text-foreground">{o.name}</div>
                    <div className="text-xs text-muted-foreground">ID: {o.organization_id}</div>
                  </div>
                  <Badge variant={o.status === "active" ? "default" : "secondary"}>{o.status}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
