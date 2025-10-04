// src/pages/dashboard/organizations.tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Edit,
  Trash2,
  ChevronDown,
  ChevronRight,
  Server,
  Sparkles,
  Plus,
} from "lucide-react";

/* ---------- Types ---------- */
type OrgItem = {
  organization_id: string;
  name: string;
  status: string;
  last_seen?: string | null;
  features?: Record<string, any>;
};

type OrgsResp = {
  success: boolean;
  data?: {
    items: OrgItem[];
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
};

type OrchRow = {
  orchestrator_id: string;
  organization_id: string;
  name: string;
  status: string;
  health_status: string;
  last_seen?: string | null;
  metadata?: Record<string, any>;
};

type OrchestratorsResp = {
  success: boolean;
  data?: {
    items: OrchRow[];
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

type LiveResp = {
  success: boolean;
  data?: {
    orchestrators: Record<
      string,
      {
        organization_id: string;
        name: string;
        status: string;
        last_seen?: string;
        metadata?: Record<string, any>;
      }
    >;
    total_count: number;
  };
};

const StatusBadge = ({ status }: { status?: string }) => {
  const s = (status ?? "").toLowerCase();
  let variant: "default" | "secondary" | "destructive" = "secondary";
  
  if (s === "active" || s === "connected") {
    variant = "default";
  } else if (s === "independent") {
    variant = "destructive";
  }
  
  return <Badge variant={variant}>{s || "unknown"}</Badge>;
};

/* ---------- Main ---------- */
export const Organizations = () => {
  const [loading, setLoading] = useState(true);

  // rows to render
  const [items, setItems] = useState<OrgItem[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // support data
  const [registeredMap, setRegisteredMap] =
    useState<Record<string, Array<{ id: string; status: string; name?: string }>>>({});
  const [liveOrgIds, setLiveOrgIds] = useState<Set<string>>(new Set());
  const [liveFeaturesByOrg, setLiveFeaturesByOrg] =
    useState<
      Record<string, { cache?: { enabled?: boolean }; firewall?: { enabled?: boolean } }>
    >({});
  const [independenceStatus, setIndependenceStatus] = useState<Record<string, boolean>>({});

  // Create Organization dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [newOrgId, setNewOrgId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgLocation, setNewOrgLocation] = useState("unknown");
  const [creating, setCreating] = useState(false);

  // --- loader (DB-only for orgs) ---
  const loadAll = async () => {
    setLoading(true);
    try {
      // 1) Orgs from DB (authoritative)
      const orgsRes = await api.get<OrgsResp>("/api/v1/controller/organizations", {
        params: { page_size: 100 },
      });
      setItems(orgsRes.data.data?.items ?? []);

      // 2) Orchestrators for "registered" counts (not for status)
      const orchsRes = await api.get<OrchestratorsResp>(
        "/api/v1/controller/orchestrators",
        { params: { page_size: 100 } }
      );
      const orchRows = orchsRes.data.data?.items ?? [];
      const reg: Record<string, Array<{ id: string; status: string; name?: string }>> =
        {};
      for (const r of orchRows) {
        const arr = reg[r.organization_id] ?? [];
        arr.push({ id: r.orchestrator_id, status: r.status, name: r.name });
        reg[r.organization_id] = arr;
      }
      setRegisteredMap(reg);

      // 3) Load independence status for each orchestrator
      const independenceMap: Record<string, boolean> = {};
      for (const r of orchRows) {
        try {
          const indRes = await api.get(`/api/v1/internal/orchestrators/${r.orchestrator_id}/independence`);
          independenceMap[r.organization_id] = indRes.data?.is_independent ?? false;
        } catch {
          independenceMap[r.organization_id] = false;
        }
      }
      setIndependenceStatus(independenceMap);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Helper: refresh the live map immediately (also used by the poller)
  const refreshLiveNow = async () => {
    try {
      const liveRes = await api.get<LiveResp>("/api/v1/controller/orchestrators/live");
      const liveMap = liveRes.data?.data?.orchestrators ?? {};
      const s = new Set<string>();
      const featuresByOrg: Record<
        string,
        { cache?: { enabled?: boolean }; firewall?: { enabled?: boolean } }
      > = {};

      Object.values(liveMap).forEach((payload: any) => {
        const oid = payload?.organization_id;
        if (!oid) return;
        s.add(oid);
        const f = payload?.metadata?.features ?? {};
        featuresByOrg[oid] = {
          cache: { enabled: f?.cache?.enabled },
          firewall: { enabled: f?.firewall?.enabled },
        };
      });

      setLiveOrgIds(s);
      setLiveFeaturesByOrg(featuresByOrg);
    } catch {
      /* ignore */
    }
  };

  // Pull live initially & every 10s
  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      if (!mounted) return;
      await refreshLiveNow();
    };
    tick();
    const t = setInterval(tick, 10_000);
    return () => {
      mounted = false;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Only "live" flips active badge (DB authoritative for list)
  const merged = useMemo(() => {
    return items.map((org) => {
      const reg = registeredMap[org.organization_id] ?? [];
      const live = liveOrgIds.has(org.organization_id);
      const isIndependent = independenceStatus[org.organization_id] ?? false;
      const overall = isIndependent ? "independent" : (live ? "active" : "inactive");
      const liveFeat = liveFeaturesByOrg[org.organization_id] || {};
      return { org, reg, live, overall, liveFeat, isIndependent };
    });
  }, [items, registeredMap, liveOrgIds, liveFeaturesByOrg, independenceStatus]);

  const toggleExpand = (orgId: string) =>
    setExpanded((e) => ({ ...e, [orgId]: !e[orgId] }));

  // Delete organization
  const deleteOrg = async (orgId: string, orgName: string) => {
    if (!confirm(`Are you sure you want to delete "${orgName}"?`)) {
      return;
    }
    
    try {
      await api.delete(`/api/v1/internal/orchestrators/${orgId}/deregister`);
      await loadAll();
      await refreshLiveNow();
    } catch (err) {
      console.error("Delete org failed", err);
      alert("Delete organization failed. See console.");
    }
  };

  // Toggle independence mode
  const toggleIndependence = async (orgId: string, orchestratorId: string, currentStatus: boolean) => {
    try {
      await api.put(`/api/v1/internal/orchestrators/${orchestratorId}/independence`, {
        is_independent: !currentStatus,
        privacy_mode: false
      });
      
      // Update local state immediately
      setIndependenceStatus(prev => ({
        ...prev,
        [orgId]: !currentStatus
      }));
      
      // Refresh data to get updated status
      await loadAll();
      await refreshLiveNow();
    } catch (err) {
      console.error("Toggle independence failed", err);
      alert("Failed to toggle independence mode. See console.");
    }
  };

  // Create org (DB-first; fallback only if controller route is locked)
  const createOrg = async () => {
    if (!newOrgId.trim() || !newOrgName.trim()) {
      alert("Please enter Org ID and Name.");
      return;
    }
    setCreating(true);
    const org_id = newOrgId.trim();
    const name = newOrgName.trim();
    const location = (newOrgLocation || "unknown").trim();

    try {
      // Register the orchestrator
      await api.post("/api/v1/internal/orchestrators/register", {
        orchestrator_id: org_id,
        organization_id: org_id,
        name,
        location,
      });

      setCreateOpen(false);
      setNewOrgId("");
      setNewOrgName("");
      setNewOrgLocation("unknown");
      await loadAll();
      await refreshLiveNow();
    } catch (err) {
      console.error("Create org failed", err);
      alert("Create organization failed. See console.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">
            Organizations
          </h1>
          <p className="text-muted-foreground mt-1">
            Create, configure, and manage orchestrator instances for
            organizations
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add New Organization
        </Button>
      </div>

      <Card className="bg-card border-border">
        <div className="p-6">
          {loading && (
            <div className="text-sm text-muted-foreground">Loading…</div>
          )}
          {!loading && merged.length === 0 && (
            <div className="text-sm text-muted-foreground">
              No organizations yet.
            </div>
          )}

          <div className="space-y-4">
            {merged.map(({ org, reg, live, overall, liveFeat, isIndependent }) => {
              const isOpen = !!expanded[org.organization_id];

              return (
                <div
                  key={org.organization_id}
                  className="rounded-lg border border-border hover:bg-card/50 transition-colors"
                >
                  <div className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => toggleExpand(org.organization_id)}
                        className="text-muted-foreground"
                      >
                        {isOpen ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                      <div className="w-6 h-6 rounded-sm bg-muted flex items-center justify-center">
                        <div
                          className={`w-3 h-3 ${
                            overall === "active"
                              ? "bg-primary"
                              : "bg-muted-foreground/30"
                          } rounded-sm`}
                        />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium text-foreground">
                            {org.name}
                          </h3>
                          <StatusBadge status={overall} />
                        </div>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mt-1">
                          <span>ID: {org.organization_id}</span>
                          {!!reg.length && (
                            <span className="inline-flex items-center gap-1">
                              <Server className="h-3 w-3" /> {reg.length}{" "}
                              registered
                            </span>
                          )}
                          {live && (
                            <span className="inline-flex items-center gap-1">
                              <Sparkles className="h-3 w-3" /> live
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0">
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        className="h-8 w-8 p-0"
                        onClick={() => deleteOrg(org.organization_id, org.name)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {isOpen && (
                    <>
                      <Separator />
                      <div className="p-4">
                        <div className="text-sm">
                          <div className="font-medium mb-1">
                            Organization Details
                          </div>
                          <div className="text-xs bg-muted/10 p-3 rounded-md space-y-1">
                            <div><span className="font-medium">ID:</span> {org.organization_id}</div>
                            <div><span className="font-medium">Name:</span> {org.name}</div>
                            <div><span className="font-medium">Status:</span> <StatusBadge status={overall} /></div>
                          </div>
                        </div>
                      </div>
                      <Separator />
                      <div className="p-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium mb-1">Independence Mode</div>
                            <div className="text-xs text-muted-foreground">
                              When enabled, orchestrator operates independently without controller supervision
                            </div>
                          </div>
                          <Switch
                            checked={independenceStatus[org.organization_id] ?? false}
                            onCheckedChange={(checked) => {
                              const orchestratorId = reg[0]?.id || org.organization_id;
                              toggleIndependence(org.organization_id, orchestratorId, independenceStatus[org.organization_id] ?? false);
                            }}
                            disabled={!reg.length}
                          />
                        </div>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      {/* Create Organization Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New Organization</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="org-id">Organization ID</Label>
              <Input
                id="org-id"
                placeholder="e.g., org-acme-001"
                value={newOrgId}
                onChange={(e) => setNewOrgId(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="org-name">Name</Label>
              <Input
                id="org-name"
                placeholder="e.g., Acme Corp"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="org-loc">Location</Label>
              <Input
                id="org-loc"
                placeholder="e.g., us-east-1 / on-prem"
                value={newOrgLocation}
                onChange={(e) => setNewOrgLocation(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateOpen(false)}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button onClick={createOrg} disabled={creating}>
              {creating ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Organizations;
