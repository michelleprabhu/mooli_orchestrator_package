import React, { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Trash2 } from 'lucide-react';
import { apiClient } from '../services/api-client';
import { toast } from 'sonner';

export const ConfigurationFirewall: React.FC = () => {
  const [firewallEnabled, setFirewallEnabled] = useState(true);
  const [autoBlockSuspicious, setAutoBlockSuspicious] = useState(true);
  const [secretsScanning, setSecretsScanning] = useState(true);
  const [toxicityDetection, setToxicityDetection] = useState(true);
  const [quarantineSystem, setQuarantineSystem] = useState(true);
  const [securityScanning, setSecurityScanning] = useState(true);
  const [enableMasking, setEnableMasking] = useState(true);
  const [enablePIIDetection, setEnablePIIDetection] = useState(true);
  const [hipaaCompliance, setHipaaCompliance] = useState(true);

  // New state for allow/block rules with database integration
  const [firewallRules, setFirewallRules] = useState<Array<{
    id: string;
    rule_type: string;
    pattern?: string;
    description?: string;
    domain_scope?: string;
    applies_to_domains?: string[];
    priority?: number;
    rule_category?: string;
  }>>([]);
  const [loading, setLoading] = useState(false);
  const [showDomainRules, setShowDomainRules] = useState(false);
  const [domainRuleType, setDomainRuleType] = useState<"blanket" | "keyword">("blanket");

  // Temp inputs for adding rules
  const [newRuleType, setNewRuleType] = useState<"allow" | "block">("allow");
  const [newRuleValue, setNewRuleValue] = useState("");
  const [newRuleDesc, setNewRuleDesc] = useState("");
  const [newRuleDomain, setNewRuleDomain] = useState("");
  const [newRulePriority, setNewRulePriority] = useState("50");

  // --- Database rule management functions ---
  const loadRules = async () => {
    setLoading(true);
    try {
      const data = await apiClient.get('/firewall/rules');
      setFirewallRules(data.rules || []);
    } catch (err) {
      console.error('Error loading firewall rules:', err);
      toast.error('Failed to load firewall rules');
    } finally {
      setLoading(false);
    }
  };

  const createRule = async () => {
    // For blanket domain rules, pattern is not required
    if (domainRuleType === "keyword" && !newRuleValue.trim()) {
      toast.error('Pattern is required for keyword rules');
      return;
    }
    if (domainRuleType === "blanket" && !newRuleDomain.trim()) {
      toast.error('Domain is required for blanket domain rules');
      return;
    }

    setLoading(true);
    try {
      const endpoint = newRuleDomain ? '/firewall/domain-rules' : '/firewall/rules';
      const payload: any = {
        rule_type: newRuleType,
        description: newRuleDesc || undefined
      };

      // Add domain-specific fields if domain is specified
      if (newRuleDomain) {
        payload.domain_scope = newRuleDomain;
        payload.priority = parseInt(newRulePriority) || 50;
        payload.rule_category = domainRuleType === "blanket" ? "blanket_domain" : "keyword";

        // Only add pattern for keyword rules
        if (domainRuleType === "keyword") {
          payload.pattern = newRuleValue;
        }
      } else {
        // General rules always need patterns
        payload.pattern = newRuleValue;
        payload.rule_category = "keyword";
      }

      const newRule = await apiClient.post(endpoint, payload);
      setFirewallRules(prev => [...prev, newRule]);
      setNewRuleValue("");
      setNewRuleDesc("");
      setNewRuleDomain("");
      setNewRulePriority("50");
      toast.success(`${newRuleDomain ? `${domainRuleType === "blanket" ? 'Blanket domain' : 'Domain keyword'}` : 'General'} ${newRuleType} rule created successfully`);
    } catch (err) {
      console.error('Error creating firewall rule:', err);
      toast.error('Failed to create firewall rule');
    } finally {
      setLoading(false);
    }
  };

  const deleteRule = async (ruleId: string) => {
    setLoading(true);
    try {
      await apiClient.delete(`/firewall/rules/${ruleId}`);
      setFirewallRules(prev => prev.filter(rule => rule.id !== ruleId));
      toast.success('Rule deleted successfully');
    } catch (err) {
      console.error('Error deleting firewall rule:', err);
      toast.error('Failed to delete firewall rule');
    } finally {
      setLoading(false);
    }
  };

  // Load rules on component mount
  useEffect(() => {
    loadRules();
  }, []);

  // --- Helper to call backend ---
  const callEndpoint = async (endpoint: string, payload: object) => {
    try {
      const data = await apiClient.post(endpoint, payload);
      console.log(`Response from ${endpoint}:`, data);
      toast.success(`${endpoint.split('/').pop()} scan completed`);
    } catch (err) {
      console.error(`Error calling ${endpoint}:`, err);
      toast.error(`Failed to test ${endpoint.split('/').pop()} scan`);
    }
  };

  // --- Handlers for switches ---
  const handlePIIToggle = async (enabled: boolean) => {
    setEnablePIIDetection(enabled);
    if (enabled) {
      await callEndpoint("/firewall/scan/pii", { content: "test pii input" });
    }
  };

  const handleSecretsToggle = async (enabled: boolean) => {
    setSecretsScanning(enabled);
    if (enabled) {
      await callEndpoint("/firewall/scan/secrets", { content: "AWS_KEY=AKIA1234567890" });
    }
  };

  const handleToxicityToggle = async (enabled: boolean) => {
    setToxicityDetection(enabled);
    if (enabled) {
      await callEndpoint("/firewall/scan/toxicity", { content: "test harmful content" });
    }
  };

  const handleAllowlistToggle = async (enabled: boolean) => {
    setFirewallEnabled(enabled);
    if (enabled) {
      const allowTopics = firewallRules.filter(r => r.rule_type === "allow").map(r => r.pattern);
      const blockedTopics = firewallRules.filter(r => r.rule_type === "block").map(r => r.pattern);
      await callEndpoint("/firewall/scan/allow", {
        text: "example test text",
        topics: allowTopics,
        blocked: blockedTopics
      });
    }
  };


  return (
    <div className="flex-1 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">LLM Firewall</h1>
        <Button variant="outline" className="border-border text-foreground">
          Update
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">
        Control the basic firewall settings
      </p>

      {/* Basic Firewall Settings */}
      <Card className="p-6 bg-card border-border">
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h3 className="text-lg font-medium text-foreground">Enable Firewall (Allow/Block)</h3>
              <p className="text-sm text-muted-foreground">Turn on/off firewall enforcement</p>
            </div>
            <Switch
              checked={firewallEnabled}
              onCheckedChange={handleAllowlistToggle}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h3 className="text-lg font-medium text-foreground">Auto-block Suspicious Activity</h3>
              <p className="text-sm text-muted-foreground">Automatically block IPs with suspicious behavior</p>
            </div>
            <Switch
              checked={autoBlockSuspicious}
              onCheckedChange={setAutoBlockSuspicious}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h3 className="text-lg font-medium text-foreground">Enable Secrets Scanning</h3>
              <p className="text-sm text-muted-foreground">Scan content for exposed credentials and tokens</p>
            </div>
            <Switch
              checked={secretsScanning}
              onCheckedChange={handleSecretsToggle}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h3 className="text-lg font-medium text-foreground">Enable Toxicity Detection</h3>
              <p className="text-sm text-muted-foreground">Automatically scan content for offensive material</p>
            </div>
            <Switch
              checked={toxicityDetection}
              onCheckedChange={handleToxicityToggle}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>
        </div>
      </Card>

      {/* Rule Management */}
      <Card className="p-6 bg-card border-border">
        <div className="space-y-6">
          <h3 className="text-lg font-medium text-foreground">Rule Management</h3>
          <p className="text-sm text-muted-foreground">Configure allow/block rules</p>

          {/* Toggle for domain rules */}
          <div className="flex items-center space-x-2 mb-4">
            <Switch
              checked={showDomainRules}
              onCheckedChange={setShowDomainRules}
            />
            <label className="text-sm font-medium text-foreground">
              Enable Domain-Specific Rules
            </label>
          </div>

          {/* Domain rule type selector */}
          {showDomainRules && (
            <div className="mb-4 p-4 border border-border rounded-lg bg-muted/30">
              <h4 className="text-sm font-medium text-foreground mb-2">Domain Rule Type</h4>
              <div className="flex space-x-4">
                <label className="flex items-center space-x-2">
                  <input
                    type="radio"
                    value="blanket"
                    checked={domainRuleType === "blanket"}
                    onChange={(e) => setDomainRuleType("blanket" as "blanket")}
                    className="text-orange-primary"
                  />
                  <span className="text-sm">Blanket Domain Block</span>
                  <span className="text-xs text-muted-foreground">(Block all content in this domain)</span>
                </label>
                <label className="flex items-center space-x-2">
                  <input
                    type="radio"
                    value="keyword"
                    checked={domainRuleType === "keyword"}
                    onChange={(e) => setDomainRuleType("keyword" as "keyword")}
                    className="text-orange-primary"
                  />
                  <span className="text-sm">Keyword in Domain</span>
                  <span className="text-xs text-muted-foreground">(Block specific keywords within domain)</span>
                </label>
              </div>
            </div>
          )}

          {/* Add New Rule */}
          <div className="space-y-4">
            <h4 className="text-base font-medium text-foreground">
              Add New {showDomainRules ? (domainRuleType === "blanket" ? 'Blanket Domain' : 'Domain Keyword') : 'General'} Rule
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Rule Type</label>
                <Select value={newRuleType} onValueChange={(val: any) => setNewRuleType(val)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Allow" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow">Allow</SelectItem>
                    <SelectItem value="block">Block</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {/* Only show pattern field for keyword rules or general rules */}
              {(!showDomainRules || domainRuleType === "keyword") && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Pattern Value</label>
                  <Input
                    placeholder="E.g. patient / acme-corp"
                    value={newRuleValue}
                    onChange={(e) => setNewRuleValue(e.target.value)}
                  />
                </div>
              )}
              {showDomainRules ? (
                <>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">Domain</label>
                    <Input
                      placeholder="E.g. healthcare, finance, programming"
                      value={newRuleDomain}
                      onChange={(e) => setNewRuleDomain(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">Priority (0-100)</label>
                    <Input
                      type="number"
                      placeholder="50"
                      value={newRulePriority}
                      onChange={(e) => setNewRulePriority(e.target.value)}
                      min="0"
                      max="100"
                    />
                  </div>
                </>
              ) : (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Description (Optional)</label>
                  <Input
                    placeholder="Rule Description"
                    value={newRuleDesc}
                    onChange={(e) => setNewRuleDesc(e.target.value)}
                  />
                </div>
              )}
            </div>
            {showDomainRules && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Description (Optional)</label>
                <Input
                  placeholder="Rule Description"
                  value={newRuleDesc}
                  onChange={(e) => setNewRuleDesc(e.target.value)}
                />
              </div>
            )}
            <Button
              className="bg-orange-primary hover:bg-orange-dark text-white"
              onClick={createRule}
              disabled={
                loading ||
                (showDomainRules && !newRuleDomain.trim()) ||
                ((!showDomainRules || domainRuleType === "keyword") && !newRuleValue.trim())
              }
            >
              {loading ? "Adding..." : `Add New ${showDomainRules ? (domainRuleType === "blanket" ? 'Blanket Domain' : 'Domain Keyword') : 'General'} Rule`}
            </Button>
          </div>

          {/* Existing Rules */}
          <div className="space-y-4">
            {loading && <p className="text-sm text-muted-foreground">Loading rules...</p>}

            <h4 className="text-base font-medium text-foreground">Allow Rules</h4>
            {firewallRules.filter(rule => rule.rule_type === "allow").map(rule => (
              <div key={rule.id} className="p-4 border border-border rounded-lg flex items-center justify-between">
                <div className="space-y-1">
                  <div className="text-sm font-medium text-foreground">
                    {rule.rule_category === "blanket_domain" ? `[ALL ${rule.domain_scope?.toUpperCase()} CONTENT]` : rule.pattern}
                    {rule.domain_scope && (
                      <span className="ml-2 px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">
                        Domain: {rule.domain_scope}
                      </span>
                    )}
                    {rule.rule_category && (
                      <span className="ml-2 px-2 py-1 text-xs bg-green-100 text-green-700 rounded">
                        {rule.rule_category === "blanket_domain" ? "Blanket" : "Keyword"}
                      </span>
                    )}
                    {rule.priority !== undefined && rule.priority > 0 && (
                      <span className="ml-2 px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded">
                        Priority: {rule.priority}
                      </span>
                    )}
                  </div>
                  {rule.description && (
                    <div className="text-xs text-muted-foreground">{rule.description}</div>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteRule(rule.id)}
                  className="text-destructive hover:text-destructive"
                  disabled={loading}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}

            {firewallRules.filter(rule => rule.rule_type === "allow").length === 0 && !loading && (
              <p className="text-sm text-muted-foreground">No allow rules configured</p>
            )}

            <h4 className="text-base font-medium text-foreground">Block Rules</h4>
            {firewallRules.filter(rule => rule.rule_type === "block").map(rule => (
              <div key={rule.id} className="p-4 border border-border rounded-lg flex items-center justify-between">
                <div className="space-y-1">
                  <div className="text-sm font-medium text-foreground">
                    {rule.rule_category === "blanket_domain" ? `[ALL ${rule.domain_scope?.toUpperCase()} CONTENT]` : rule.pattern}
                    {rule.domain_scope && (
                      <span className="ml-2 px-2 py-1 text-xs bg-red-100 text-red-700 rounded">
                        Domain: {rule.domain_scope}
                      </span>
                    )}
                    {rule.rule_category && (
                      <span className="ml-2 px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded">
                        {rule.rule_category === "blanket_domain" ? "Blanket" : "Keyword"}
                      </span>
                    )}
                    {rule.priority !== undefined && rule.priority > 0 && (
                      <span className="ml-2 px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded">
                        Priority: {rule.priority}
                      </span>
                    )}
                  </div>
                  {rule.description && (
                    <div className="text-xs text-muted-foreground">{rule.description}</div>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteRule(rule.id)}
                  className="text-destructive hover:text-destructive"
                  disabled={loading}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}

            {firewallRules.filter(rule => rule.rule_type === "block").length === 0 && !loading && (
              <p className="text-sm text-muted-foreground">No block rules configured</p>
            )}
          </div>
        </div>
      </Card>

      {/* PII Detection & HIPAA Compliance */}
      <Card className="p-6 bg-card border-border">
        <div className="space-y-6">
          <h3 className="text-lg font-medium text-foreground">PII Detection & HIPAA Compliance</h3>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h4 className="text-base font-medium text-foreground">Enable PII Detection</h4>
              <p className="text-sm text-muted-foreground">Scan content for personally identifiable information</p>
            </div>
            <Switch
              checked={enablePIIDetection}
              onCheckedChange={handlePIIToggle}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h4 className="text-base font-medium text-foreground">Enable Security Scanning</h4>
              <p className="text-sm text-muted-foreground">General security scanning toggle</p>
            </div>
            <Switch
              checked={securityScanning}
              onCheckedChange={setSecurityScanning}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h4 className="text-base font-medium text-foreground">Enable Masking</h4>
              <p className="text-sm text-muted-foreground">Mask detected PII</p>
            </div>
            <Switch
              checked={enableMasking}
              onCheckedChange={setEnableMasking}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h4 className="text-base font-medium text-foreground">HIPAA Compliance Mode</h4>
              <p className="text-sm text-muted-foreground">Enhanced protection for healthcare information</p>
            </div>
            <Switch
              checked={hipaaCompliance}
              onCheckedChange={setHipaaCompliance}
              className="data-[state=checked]:bg-orange-primary"
            />
          </div>
        </div>
      </Card>
    </div>
  );
};
