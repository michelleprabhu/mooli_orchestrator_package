// src/pages/dashboard/logs.tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, Activity, ShieldAlert, AlertTriangle, Clock } from "lucide-react";

/* -------- Recharts (static imports; Vite-friendly) -------- */
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

/* ----------------------------- Types ----------------------------- */
type LogItem = {
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL" | string;
  message: string;
  source?: string;
};
type LogsResp = { success?: boolean; data?: { items: LogItem[] } | LogItem[] };

/* ----------------------------- Utils ----------------------------- */
const safeDate = (v?: string) => {
  if (!v) return null;
  const t = new Date(v).getTime();
  return Number.isFinite(t) ? new Date(t) : null;
};
const fmtTime = (iso?: string) => {
  const d = safeDate(iso);
  return d ? d.toLocaleString() : "—";
};
const minuteKey = (iso: string) => {
  const d = safeDate(iso);
  if (!d) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${dd} ${hh}:${mm}`;
};

/* --------------------- AutoSizer (stops clipping) --------------------- */
function AutoSizer({
  className,
  children,
  minHeight = 200,
}: {
  className?: string;
  children: (size: { width: number; height: number }) => React.ReactNode;
  minHeight?: number;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [{ width, height }, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (!cr) return;
      const w = Math.max(0, Math.floor(cr.width));
      const h = Math.max(minHeight, Math.floor(cr.height));
      setSize((s) => (s.width !== w || s.height !== h ? { width: w, height: h } : s));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [minHeight]);

  return (
    <div ref={ref} className={className} style={{ minWidth: 0, minHeight }}>
      {width > 0 && height > 0 ? children({ width, height }) : null}
    </div>
  );
}

/* --------------------------------- Page ---------------------------------- */
export default function LogsOverview() {
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<LogItem[]>([]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const resCtrl = await api
        .get<LogsResp>("/api/v1/controller/logs", { params: { page_size: 400 } })
        .catch(() => null);
      const resInt = !resCtrl
        ? await api.get<LogsResp>("/api/v1/internal/logs", { params: { page_size: 400 } }).catch(() => null)
        : null;

      const raw = resCtrl?.data?.data ?? resInt?.data?.data ?? [];
      const arrRaw: unknown = Array.isArray(raw) ? raw : (raw as any)?.items ?? [];
      const arr = (Array.isArray(arrRaw) ? arrRaw : []) as LogItem[];

      const clean = arr
        .filter((r) => r && r.timestamp && safeDate(r.timestamp))
        .sort((a, b) => (a.timestamp > b.timestamp ? -1 : 1));
      setLogs(clean);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLogs(); }, []);

  const { total, errors, warnings, lastEventAt } = useMemo(() => {
    let err = 0, warn = 0;
    for (const r of logs) {
      const L = (r.level || "").toUpperCase();
      if (L === "ERROR" || L === "CRITICAL") err++;
      else if (L === "WARNING" || L === "WARN") warn++;
    }
    return {
      total: logs.length,
      errors: err,
      warnings: warn,
      lastEventAt: logs[0]?.timestamp ? fmtTime(logs[0].timestamp) : "—",
    };
  }, [logs]);

  const chartData = useMemo(() => {
    if (!logs.length) return [{ minute: "", count: 0 }, { minute: " ", count: 0 }];
    const latest = safeDate(logs[0].timestamp)!;
    const start = new Date(latest.getTime() - 29 * 60 * 1000);

    const bucket: Record<string, number> = {};
    for (const r of logs) {
      const mk = minuteKey(r.timestamp);
      if (!mk) continue;
      bucket[mk] = (bucket[mk] || 0) + 1;
    }

    const series: { minute: string; count: number }[] = [];
    for (let t = start.getTime(); t <= latest.getTime(); t += 60_000) {
      const d = new Date(t);
      const mk = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
      series.push({ minute: mk.slice(11), count: bucket[mk] || 0 });
    }
    if (series.length === 1) return [{ minute: "", count: 0 }, ...series];
    return series;
  }, [logs]);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Logs Overview</h1>
          <p className="text-muted-foreground mt-1">Recent activity.</p>
        </div>
        <Button onClick={fetchLogs} variant="outline" disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Total + Chart */}
      <Card className="p-6 border border-border bg-card min-w-0">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-muted/40">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Total (last fetch)</div>
              <div className="text-3xl font-semibold text-foreground">{total}</div>
            </div>
          </div>
          <Badge variant="secondary">per-minute</Badge>
        </div>

        {/* Clipping-proof chart area */}
        <AutoSizer className="h-56 w-full min-w-0 block">
          {({ width, height }) => (
            <ResponsiveContainer width={width} height={height}>
              <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.35} />
                <XAxis dataKey="minute" tick={{ fontSize: 12, fill: "#9ca3af" }} axisLine={{ stroke: "#4b5563" }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#9ca3af" }} axisLine={{ stroke: "#4b5563" }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: 8,
                    color: "#f9fafb",
                  }}
                  labelStyle={{ color: "#e5e7eb" }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  name="Logs/min"
                  stroke="#fb923c"
                  fill="#f97316"
                  fillOpacity={0.25}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </AutoSizer>
      </Card>

      {/* Errors / Warnings / Last Event */}
      <div className="grid gap-6 md:grid-cols-3 min-w-0">
        <Card className="p-6 border border-border bg-card">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-500/15">
              <ShieldAlert className="h-5 w-5 text-red-400" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Errors</div>
              <div className="text-2xl font-semibold text-foreground">{errors}</div>
            </div>
          </div>
        </Card>

        <Card className="p-6 border border-border bg-card">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/15">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Warnings</div>
              <div className="text-2xl font-semibold text-foreground">{warnings}</div>
            </div>
          </div>
        </Card>

        <Card className="p-6 border border-border bg-card">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-muted/40">
              <Clock className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Last Event</div>
              <div className="text-sm font-medium text-foreground">{lastEventAt}</div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
