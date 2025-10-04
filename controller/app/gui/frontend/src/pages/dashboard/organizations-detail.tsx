"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { 
  Building2, 
  Server, 
  Shield, 
  Database, 
  MessageSquare, 
  Activity,
  AlertCircle,
  CheckCircle
} from "lucide-react";

type Organization = {
  organization_id: string;
  name: string;
  location: string;
  is_active: boolean;
  is_independent: boolean;
  settings: Record<string, any>;
  created_at: string;
  updated_at: string;
};

type OrchestratorInstance = {
  orchestrator_id: string;
  organization_id: string;
  organization_name: string;
  status: "active" | "inactive" | "independent";
  health_status: string;
  last_seen: string | null;
  features: Record<string, any>;
  is_independent: boolean;
};

type RecommendationMessage = {
  id: string;
  orchestrator_id: string;
  message_type: "recommendation" | "monitoring";
  content: string;
  message_metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
  status: "pending" | "accepted" | "dismissed";
};

type OrganizationsResp = {
  success: boolean;
  data?: {
    items: Organization[];
    total_items: number;
  };
};

type OrchestratorsResp = {
  success: boolean;
  data?: {
    items: OrchestratorInstance[];
    total_items: number;
  };
};

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

const OrganizationsDetail = () => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [orchestrators, setOrchestrators] = useState<OrchestratorInstance[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [independenceStatus, setIndependenceStatus] = useState<Record<string, boolean>>({});

  const loadData = async () => {
    setLoading(true);
    try {
      // Load organizations
      const orgRes = await api.get<OrganizationsResp>("/api/v1/controller/organizations?page_size=100");
      const orgs = orgRes.data?.data?.items || [];
      setOrganizations(orgs);

      // Load orchestrators
      const orchRes = await api.get<OrchestratorsResp>("/api/v1/controller/orchestrators?page_size=100");
      const orchs = orchRes.data?.data?.items || [];
      setOrchestrators(orchs);

      // Load independence status for each orchestrator
      const independenceMap: Record<string, boolean> = {};
      for (const orch of orchs) {
        try {
          const indRes = await api.get(`/api/v1/internal/orchestrators/${orch.orchestrator_id}/independence`);
          independenceMap[orch.organization_id] = indRes.data?.is_independent ?? false;
        } catch {
          independenceMap[orch.organization_id] = false;
        }
      }
      setIndependenceStatus(independenceMap);

      // Load recommendation messages from API
      try {
        const messagesRes = await api.get("/api/v1/internal/messages");
        const messages = messagesRes.data?.messages || [];
        setRecommendations(messages);
      } catch (error) {
        console.error("Failed to load messages:", error);
        setRecommendations([]);
      }

    } catch (error) {
      console.error("Failed to load data:", error);
    } finally {
      setLoading(false);
    }
  };

  const toggleIndependence = async (orgId: string, orchestratorId: string, currentStatus: boolean) => {
    try {
      await api.put(`/api/v1/internal/orchestrators/${orchestratorId}/independence`, {
        is_independent: !currentStatus,
        privacy_mode: false
      });
      
      setIndependenceStatus(prev => ({
        ...prev,
        [orgId]: !currentStatus
      }));
      
      await loadData();
    } catch (err) {
      console.error("Toggle independence failed", err);
    }
  };

  const handleRecommendation = async (recId: string, action: "accept" | "dismiss") => {
    try {
      await api.put(`/api/v1/internal/messages/${recId}/status`, {
        status: action === "accept" ? "accepted" : "dismissed"
      });
      
      setRecommendations(prev => 
        prev.map(rec => 
          rec.id === recId ? { ...rec, status: action === "accept" ? "accepted" : "dismissed" } : rec
        )
      );
    } catch (error) {
      console.error("Failed to update message status:", error);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const getOrchestratorForOrg = (orgId: string) => {
    return orchestrators.find(orch => orch.organization_id === orgId);
  };

  const getRecommendationsForOrg = (orgId: string) => {
    const orch = getOrchestratorForOrg(orgId);
    return orch ? recommendations.filter(rec => rec.orchestrator_id === orch.orchestrator_id) : [];
  };

  const getFeatureStatus = (features: Record<string, any>, featureName: string) => {
    return features?.[featureName]?.enabled ?? false;
  };

  if (loading) {
    return (
      <div className="p-8">
        <div className="text-center">Loading organizations...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">Organization Characteristics</h1>
        <p className="text-muted-foreground mt-2">
          Detailed view of organization settings, features, and orchestrator communications
        </p>
      </div>

      <div className="space-y-6">
        {organizations.map((org) => {
          const orch = getOrchestratorForOrg(org.organization_id);
          const orgRecommendations = getRecommendationsForOrg(org.organization_id);
          const isIndependent = independenceStatus[org.organization_id] ?? false;

          return (
            <Card key={org.organization_id} className="p-6">
              <div className="space-y-6">
                {/* Organization Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-lg bg-muted/20 flex items-center justify-center">
                      <Building2 className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-foreground">{org.name}</h3>
                      <p className="text-sm text-muted-foreground">ID: {org.organization_id}</p>
                    </div>
                  </div>
                  <Badge variant={
                    isIndependent ? "destructive" : 
                    orch?.status === "active" ? "default" : 
                    "secondary"
                  }>
                    {isIndependent ? "Independent" : 
                     orch?.status === "active" ? "Active" : 
                     "Inactive"}
                  </Badge>
                </div>

                <Separator />

                {/* Organization Details */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Left Column - Basic Info */}
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-3">Organization Details</h4>
                      <div className="space-y-2">
                        <div className="flex items-center space-x-2">
                          <Activity className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm">Status: {org.is_active ? "Active" : "Inactive"}</span>
                        </div>
                      </div>
                    </div>

                    {/* Independence Toggle */}
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-3">Independence Mode</h4>
                      <div className="flex items-center justify-between p-3 bg-muted/10 rounded-lg">
                        <div>
                          <div className="text-sm font-medium">Independent Operation</div>
                          <div className="text-xs text-muted-foreground">
                            When enabled, orchestrator operates without controller supervision
                          </div>
                        </div>
                        <Switch
                          checked={isIndependent}
                          onCheckedChange={() => {
                            if (orch) {
                              toggleIndependence(org.organization_id, orch.orchestrator_id, isIndependent);
                            }
                          }}
                          disabled={!orch}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Right Column - Features & Status */}
                  <div className="space-y-4">
                    {isIndependent ? (
                      <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="h-5 w-5 text-destructive" />
                          <div>
                            <div className="text-sm font-medium text-destructive">Independent Mode</div>
                            <div className="text-xs text-muted-foreground">
                              This orchestrator operates independently and does not share monitoring data
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : orch ? (
                      <>
                        {/* Feature Status */}
                        <div>
                          <h4 className="text-sm font-medium text-muted-foreground mb-3">Feature Status</h4>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between p-2 bg-muted/10 rounded">
                              <div className="flex items-center space-x-2">
                                <Database className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm">Cache</span>
                              </div>
                              <Badge variant={getFeatureStatus(orch.features, "cache") ? "default" : "secondary"}>
                                {getFeatureStatus(orch.features, "cache") ? "ON" : "OFF"}
                              </Badge>
                            </div>
                            <div className="flex items-center justify-between p-2 bg-muted/10 rounded">
                              <div className="flex items-center space-x-2">
                                <Shield className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm">Firewall</span>
                              </div>
                              <Badge variant={getFeatureStatus(orch.features, "firewall") ? "default" : "secondary"}>
                                {getFeatureStatus(orch.features, "firewall") ? "ON" : "OFF"}
                              </Badge>
                            </div>
                          </div>
                        </div>

                        {/* Orchestrator Status */}
                        <div>
                          <h4 className="text-sm font-medium text-muted-foreground mb-3">Orchestrator Status</h4>
                          <div className="space-y-2">
                            <div className="flex items-center space-x-2">
                              <Server className="h-4 w-4 text-muted-foreground" />
                              <span className="text-sm">Last Seen: {timeAgo(orch.last_seen)}</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <Activity className="h-4 w-4 text-muted-foreground" />
                              <span className="text-sm">Health: {orch.health_status}</span>
                            </div>
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="p-4 bg-muted/10 rounded-lg">
                        <div className="text-sm text-muted-foreground">No orchestrator connected</div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Recommendations & Monitoring Messages */}
                {!isIndependent && orgRecommendations.length > 0 && (
                  <>
                    <Separator />
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-3">Messages from Orchestrator</h4>
                      <div className="space-y-3">
                        {orgRecommendations.map((rec) => (
                          <div key={rec.id} className="p-4 bg-muted/10 rounded-lg">
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 mb-2">
                                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                                  <Badge variant={rec.message_type === "recommendation" ? "default" : "secondary"}>
                                    {rec.message_type}
                                  </Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {timeAgo(rec.created_at)}
                                  </span>
                                </div>
                                <p className="text-sm">{rec.content}</p>
                              </div>
                              {rec.status === "pending" && (
                                <div className="flex space-x-2 ml-4">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => handleRecommendation(rec.id, "accept")}
                                  >
                                    <CheckCircle className="h-4 w-4 mr-1" />
                                    Accept
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => handleRecommendation(rec.id, "dismiss")}
                                  >
                                    Dismiss
                                  </Button>
                                </div>
                              )}
                              {rec.status === "accepted" && (
                                <Badge variant="default" className="ml-4">
                                  <CheckCircle className="h-3 w-3 mr-1" />
                                  Accepted
                                </Badge>
                              )}
                              {rec.status === "dismissed" && (
                                <Badge variant="secondary" className="ml-4">
                                  Dismissed
                                </Badge>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export default OrganizationsDetail;
