/**
 * User Prompts Tracker Dashboard
 * 
 * Real-time dashboard for tracking individual user prompts with detailed evaluation scores,
 * firewall status, cache metrics, and user feedback using Phoenix parent-child span hierarchy.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { 
  Search,
  RefreshCw,
  Download,
  Eye,
  Shield,
  Clock,
  Zap,
  CheckCircle,
  Filter,
  MoreVertical,
  ChevronDown,
  ChevronRight,
  User,
  MessageSquare,
  DollarSign,
  Activity
} from 'lucide-react';
import { toast } from '@/components/ui/use-toast';
import { format } from 'date-fns';
import { webSocketService } from '@/services/websocket';

// Types based on the backend service
interface PromptData {
  message_id: string;
  user_id: string;
  username: string;
  full_name: string;
  timestamp: string;
  prompt_text: string;
  response_text: string;
  total_duration_ms?: number;
  cache_hit?: boolean;
  similarity_score?: number;
  cache_lookup_ms?: number;
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_cost?: number;
  model?: string;
  llm_duration_ms?: number;
  was_blocked?: boolean;
  block_reason?: string;
  rule_category?: string;
  risk_score?: number;
  detected_entities?: any[];
  evaluation_scores?: {
    [key: string]: {
      score: number;
      reasoning: string;
    };
  };
}

interface PromptsResponse {
  prompts: PromptData[];
  pagination: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
  filters: {
    start_date: string;
    end_date: string;
    user_filter?: string;
    search_text?: string;
  };
}

interface PromptDetailData {
  message_id: string;
  user_id: string;
  username: string;
  full_name: string;
  timestamp: string;
  prompt_text: string;
  response_text: string;
  response_timestamp?: string;
  total_duration_ms?: number;
  cache_data?: any;
  llm_data?: any;
  firewall_data?: any;
  evaluation_data?: any;
  parent_attributes?: any;
  child_spans_count?: number;
}

// Evaluation metric display names - updated for clarity and user-friendliness
const EVALUATION_METRICS = {
  answer_correctness: 'Accuracy',
  answer_relevance: 'Relevance',
  hallucination: 'Hallucination Risk',
  hallucination_score: 'Hallucination Risk',
  goal_accuracy: 'Task Success',
  human_vs_ai: 'Human-like Quality',
  summarization: 'Summary Quality',
  toxicity: 'Safety Score'
};

export const UserPromptsTracker: React.FC = () => {
  // State management
  const [prompts, setPrompts] = useState<PromptData[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({
    total: 0,
    limit: 50,
    offset: 0,
    has_more: false
  });
  
  // Filters and search
  const [searchText, setSearchText] = useState('');
  const [userFilter, setUserFilter] = useState('all');
  const [dateRange, setDateRange] = useState({
    start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days ago
    end_date: new Date().toISOString()
  });
  
  // UI state
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetailData | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  
  // Real-time updates
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [connectionState, setConnectionState] = useState(webSocketService.getConnectionState());
  
  // Refs for cleanup
  const subscriptionCleanup = useRef<(() => void)[]>([]);

  // Load prompts data
  const loadPrompts = useCallback(async (resetOffset = true) => {
    try {
      setLoading(true);
      const offset = resetOffset ? 0 : pagination.offset;
      
      // Wait for WebSocket connection with timeout
      const waitForConnection = async (maxWaitTime = 10000): Promise<boolean> => {
        const startTime = Date.now();
        while (Date.now() - startTime < maxWaitTime) {
          if (webSocketService.getConnectionState() === 'connected') {
            return true;
          }
          // Wait 100ms before checking again
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        return false;
      };
      
      // Ensure WebSocket connection before making request
      const isConnected = await waitForConnection();
      if (!isConnected) {
        // Try to connect if not connected
        try {
          await webSocketService.connect({ user_id: 'default_user' });
        } catch (connectError) {
          console.error('Failed to establish WebSocket connection:', connectError);
          throw new Error('Unable to establish WebSocket connection. Please refresh the page.');
        }
      }
      
      const response: PromptsResponse = await webSocketService.requestPrompts({
        start_date: dateRange.start_date,
        end_date: dateRange.end_date,
        limit: pagination.limit,
        offset,
        user_filter: userFilter === 'all' ? undefined : userFilter,
        search_text: searchText || undefined
      });
      
      if (resetOffset) {
        setPrompts(response.prompts);
        setPagination({
          total: response.pagination.total,
          limit: response.pagination.limit,
          offset: 0,
          has_more: response.pagination.has_more
        });
      } else {
        setPrompts(prev => [...prev, ...response.prompts]);
        setPagination(prev => ({
          ...prev,
          offset: offset + response.pagination.limit,
          has_more: response.pagination.has_more
        }));
      }
      
    } catch (error) {
      console.error('Error loading prompts:', error);
      toast({
        title: "Error",
        description: "Failed to load prompts data",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  }, [dateRange, userFilter, searchText, pagination.limit, pagination.offset]);

  // Load more prompts (pagination)
  const loadMore = () => {
    if (pagination.has_more && !loading) {
      loadPrompts(false);
    }
  };

  // Get prompt details
  const getPromptDetails = async (messageId: string) => {
    try {
      const detail: PromptDetailData = await webSocketService.requestPromptDetail(messageId);
      setSelectedPrompt(detail);
      setDetailDialogOpen(true);
    } catch (error) {
      console.error('Error loading prompt details:', error);
      toast({
        title: "Error",
        description: "Failed to load prompt details",
        variant: "destructive"
      });
    }
  };

  // Export data
  const exportData = async (format: 'csv' | 'json') => {
    try {
      const response = await webSocketService.exportPrompts({
        format,
        filters: {
          start_date: dateRange.start_date,
          end_date: dateRange.end_date,
          user_filter: userFilter === 'all' ? undefined : userFilter,
          search_text: searchText || undefined
        }
      });
      
      // Create download link
      const blob = new Blob([atob(response.data)], { 
        type: format === 'csv' ? 'text/csv' : 'application/json' 
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = response.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      toast({
        title: "Success",
        description: `Data exported successfully as ${format.toUpperCase()}`
      });
    } catch (error) {
      console.error('Error exporting data:', error);
      toast({
        title: "Error",
        description: "Failed to export data",
        variant: "destructive"
      });
    }
  };

  // Toggle row expansion
  const toggleRowExpansion = (messageId: string) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  // Real-time subscription management
  useEffect(() => {
    const setupSubscription = async () => {
      try {
        // Subscribe to real-time updates
        await webSocketService.subscribeToPrompts();
        setIsSubscribed(true);
        
        // Set up event listeners
        const cleanup1 = webSocketService.addEventListener('prompts_update', (data) => {
          // Add new prompt to the beginning of the list
          setPrompts(prev => [data, ...prev]);
          setPagination(prev => ({ ...prev, total: prev.total + 1 }));
          toast({
            title: "New Prompt",
            description: "New prompt received"
          });
        });
        
        const cleanup2 = webSocketService.addEventListener('prompt_error', (error) => {
          console.error('Prompt tracking error:', error);
          toast({
            title: "Error",
            description: "Real-time update error",
            variant: "destructive"
          });
        });
        
        subscriptionCleanup.current = [cleanup1, cleanup2];
        
      } catch (error) {
        console.error('Failed to set up real-time subscription:', error);
      }
    };

    if (connectionState === 'connected' && !isSubscribed) {
      setupSubscription();
    }

    return () => {
      // Cleanup subscriptions
      subscriptionCleanup.current.forEach(cleanup => cleanup());
    };
  }, [connectionState, isSubscribed]);

  // Monitor connection state
  useEffect(() => {
    const cleanup = webSocketService.onStateChange(setConnectionState);
    return cleanup;
  }, []);

  // Initial data load - direct database access
  useEffect(() => {
    // Establish WebSocket connection first
    if (connectionState === 'disconnected') {
      webSocketService.connect({ user_id: 'default_user' }).catch(error => {
        console.error('Failed to establish WebSocket connection:', error);
      });
    }
    
    loadPrompts();
  }, []);

  // Auto-refresh every 30 seconds - database polling
  useEffect(() => {
    const interval = setInterval(() => {
      if (!loading) {
        loadPrompts(true); // Reset offset on auto-refresh
      }
    }, 30000); // 30 seconds

    return () => clearInterval(interval);
  }, [loading, loadPrompts]);

  // Format evaluation score for display
  const formatEvaluationScore = (score: number): string => {
    return (score * 100).toFixed(1) + '%';
  };

  // Get score color based on value
  const getScoreColor = (score: number): string => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  // Render evaluation scores with improved readability
  const renderEvaluationScores = (scores: PromptData['evaluation_scores']) => {
    if (!scores || Object.keys(scores).length === 0) {
      return <span className="text-gray-400">No evaluations</span>;
    }

    // Sort scores to prioritize important metrics
    const sortedMetrics = Object.entries(scores).sort(([a], [b]) => {
      const priority = ['answer_correctness', 'answer_relevance', 'hallucination_score', 'hallucination', 'goal_accuracy'];
      const aIndex = priority.indexOf(a);
      const bIndex = priority.indexOf(b);
      if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
      if (aIndex !== -1) return -1;
      if (bIndex !== -1) return 1;
      return a.localeCompare(b);
    });

    return (
      <div className="space-y-1">
        {sortedMetrics.slice(0, 3).map(([metric, data]) => {
          const displayName = EVALUATION_METRICS[metric as keyof typeof EVALUATION_METRICS] || metric;
          const isHallucination = metric === 'hallucination' || metric === 'hallucination_score';
          // For hallucination: backend 1.0 = no hallucination, should display as 0%
          // For hallucination: backend 0.0 = complete hallucination, should display as 100%
          const displayScore = isHallucination ?
            ((1 - data.score) * 100).toFixed(0) + '%' : // Invert hallucination score
            formatEvaluationScore(data.score);
          const scoreColor = isHallucination ?
            getScoreColor(data.score) : // Use original score for color (1.0 = good = green)
            getScoreColor(data.score);

          return (
            <div key={metric} className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground truncate" title={displayName}>
                {displayName}
              </span>
              <span className={`text-xs font-medium ${scoreColor}`} title={data.reasoning}>
                {displayScore}
              </span>
            </div>
          );
        })}
        {sortedMetrics.length > 3 && (
          <div className="text-xs text-muted-foreground text-center">
            +{sortedMetrics.length - 3} more
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">User Prompts Tracker</h1>
          <p className="text-muted-foreground">
            Track individual prompts with detailed evaluation scores, cache metrics, and firewall status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={connectionState === 'connected' ? 'default' : 'secondary'}>
            {connectionState === 'connected' ? '🟢 Live' : '🟡 Database'}
          </Badge>
          <Badge variant="secondary">
            🔄 Auto-refresh (30s)
          </Badge>
        </div>
      </div>

      {/* Filters and Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters & Controls
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-4">
            {/* Search */}
            <div className="relative flex-1 min-w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search prompts and responses..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadPrompts()}
                className="pl-10"
              />
            </div>

            {/* User Filter */}
            <Select value={userFilter} onValueChange={setUserFilter}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filter by user" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All users</SelectItem>
                {/* Dynamic user options would be populated here */}
              </SelectContent>
            </Select>

            {/* Date Range */}
            <div className="flex gap-2">
              <Input
                type="datetime-local"
                value={dateRange.start_date.slice(0, 16)}
                onChange={(e) => setDateRange(prev => ({ 
                  ...prev, 
                  start_date: new Date(e.target.value).toISOString() 
                }))}
                className="w-48"
              />
              <Input
                type="datetime-local"
                value={dateRange.end_date.slice(0, 16)}
                onChange={(e) => setDateRange(prev => ({ 
                  ...prev, 
                  end_date: new Date(e.target.value).toISOString() 
                }))}
                className="w-48"
              />
            </div>

            {/* Action Buttons */}
            <Button onClick={() => loadPrompts()} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>Export Format</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => exportData('csv')}>
                  Export as CSV
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => exportData('json')}>
                  Export as JSON
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardContent>
      </Card>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center space-x-2">
              <MessageSquare className="h-4 w-4 text-blue-600" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Prompts</p>
                <p className="text-2xl font-bold">{pagination.total.toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center space-x-2">
              <Shield className="h-4 w-4 text-red-600" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Blocked</p>
                <p className="text-2xl font-bold">
                  {prompts.filter(p => p.was_blocked).length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center space-x-2">
              <Zap className="h-4 w-4 text-green-600" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Cache Hits</p>
                <p className="text-2xl font-bold">
                  {prompts.filter(p => p.cache_hit).length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4 text-purple-600" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Total Cost</p>
                <p className="text-2xl font-bold">
                  ${prompts.reduce((sum, p) => sum + (p.total_cost || 0), 0).toFixed(4)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Data Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Prompts Data</span>
            <Badge variant="outline">{prompts.length} of {pagination.total}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12"></TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Prompt</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Performance</TableHead>
                  <TableHead>AI Quality Metrics</TableHead>
                  <TableHead>Cost</TableHead>
                  <TableHead>Timestamp</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prompts.map((prompt) => (
                  <React.Fragment key={prompt.message_id}>
                    <TableRow className="hover:bg-muted/50">
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleRowExpansion(prompt.message_id)}
                        >
                          {expandedRows.has(prompt.message_id) ? 
                            <ChevronDown className="h-4 w-4" /> : 
                            <ChevronRight className="h-4 w-4" />
                          }
                        </Button>
                      </TableCell>
                      
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <User className="h-4 w-4 text-muted-foreground" />
                          <div>
                            <div className="font-medium">{prompt.username}</div>
                            <div className="text-sm text-muted-foreground">{prompt.full_name}</div>
                          </div>
                        </div>
                      </TableCell>
                      
                      <TableCell className="max-w-md">
                        <div className="space-y-1">
                          <p className="font-medium text-sm truncate" title={prompt.prompt_text}>
                            {prompt.prompt_text}
                          </p>
                          {prompt.response_text && (
                            <p className="text-xs text-muted-foreground truncate" title={prompt.response_text}>
                              {prompt.response_text}
                            </p>
                          )}
                        </div>
                      </TableCell>
                      
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          {prompt.was_blocked ? (
                            <Badge variant="destructive" className="w-fit">
                              <Shield className="h-3 w-3 mr-1" />
                              Blocked
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="w-fit">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Allowed
                            </Badge>
                          )}
                          
                          {prompt.cache_hit !== undefined && (
                            <Badge 
                              variant={prompt.cache_hit ? "default" : "outline"} 
                              className="w-fit text-xs"
                            >
                              <Zap className="h-3 w-3 mr-1" />
                              Cache {prompt.cache_hit ? 'Hit' : 'Miss'}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      
                      <TableCell>
                        <div className="space-y-1 text-sm">
                          {prompt.total_duration_ms && (
                            <div className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {prompt.total_duration_ms.toFixed(0)}ms
                            </div>
                          )}
                          {prompt.total_tokens && (
                            <div className="flex items-center gap-1">
                              <Activity className="h-3 w-3" />
                              {prompt.total_tokens.toLocaleString()} tokens
                            </div>
                          )}
                        </div>
                      </TableCell>
                      
                      <TableCell className="max-w-xs">
                        {renderEvaluationScores(prompt.evaluation_scores)}
                      </TableCell>
                      
                      <TableCell>
                        {prompt.total_cost ? (
                          <div className="font-medium">
                            ${prompt.total_cost.toFixed(4)}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      
                      <TableCell>
                        <div className="text-sm">
                          {format(new Date(prompt.timestamp), 'MMM d, HH:mm')}
                        </div>
                      </TableCell>
                      
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => getPromptDetails(prompt.message_id)}>
                              <Eye className="h-4 w-4 mr-2" />
                              View Details
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                    
                    {/* Expanded Row Details */}
                    {expandedRows.has(prompt.message_id) && (
                      <TableRow>
                        <TableCell colSpan={9}>
                          <div className="p-4 bg-muted/20 rounded-md space-y-4">
                            <Tabs defaultValue="content" className="w-full">
                              <TabsList>
                                <TabsTrigger value="content">Content</TabsTrigger>
                                <TabsTrigger value="metrics">Metrics</TabsTrigger>
                                <TabsTrigger value="evaluations">Evaluations</TabsTrigger>
                                <TabsTrigger value="security">Security</TabsTrigger>
                              </TabsList>
                              
                              <TabsContent value="content" className="space-y-4">
                                <div>
                                  <h4 className="font-medium mb-2">User Prompt</h4>
                                  <p className="text-sm bg-background p-3 rounded border">
                                    {prompt.prompt_text}
                                  </p>
                                </div>
                                {prompt.response_text && (
                                  <div>
                                    <h4 className="font-medium mb-2">AI Response</h4>
                                    <p className="text-sm bg-background p-3 rounded border">
                                      {prompt.response_text}
                                    </p>
                                  </div>
                                )}
                              </TabsContent>
                              
                              <TabsContent value="metrics" className="space-y-4">
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                  {prompt.total_duration_ms && (
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">Total Duration</p>
                                      <p className="text-2xl font-bold">{prompt.total_duration_ms.toFixed(0)}ms</p>
                                    </div>
                                  )}
                                  {prompt.cache_lookup_ms && (
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">Cache Lookup</p>
                                      <p className="text-2xl font-bold">{prompt.cache_lookup_ms.toFixed(0)}ms</p>
                                    </div>
                                  )}
                                  {prompt.llm_duration_ms && (
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">LLM Duration</p>
                                      <p className="text-2xl font-bold">{prompt.llm_duration_ms.toFixed(0)}ms</p>
                                    </div>
                                  )}
                                  {prompt.similarity_score && (
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">Cache Similarity</p>
                                      <p className="text-2xl font-bold">{(prompt.similarity_score * 100).toFixed(1)}%</p>
                                    </div>
                                  )}
                                </div>
                              </TabsContent>
                              
                              <TabsContent value="evaluations" className="space-y-4">
                                {prompt.evaluation_scores && Object.keys(prompt.evaluation_scores).length > 0 ? (
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {Object.entries(prompt.evaluation_scores).map(([metric, data]) => (
                                      <Card key={metric}>
                                        <CardContent className="p-4">
                                          <div className="flex items-center justify-between mb-2">
                                            <h4 className="font-medium">
                                              {EVALUATION_METRICS[metric as keyof typeof EVALUATION_METRICS] || metric}
                                            </h4>
                                            <span className={`font-bold text-lg ${getScoreColor(data.score)}`}>
                                              {formatEvaluationScore(data.score)}
                                            </span>
                                          </div>
                                          <p className="text-sm text-muted-foreground">
                                            {data.reasoning}
                                          </p>
                                        </CardContent>
                                      </Card>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-muted-foreground">No evaluation scores available</p>
                                )}
                              </TabsContent>
                              
                              <TabsContent value="security" className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  <Card>
                                    <CardContent className="p-4">
                                      <h4 className="font-medium mb-2">Firewall Status</h4>
                                      <div className="space-y-2">
                                        <Badge variant={prompt.was_blocked ? "destructive" : "outline"}>
                                          {prompt.was_blocked ? 'Blocked' : 'Allowed'}
                                        </Badge>
                                        {prompt.block_reason && (
                                          <p className="text-sm text-muted-foreground">
                                            Reason: {prompt.block_reason}
                                          </p>
                                        )}
                                        {prompt.rule_category && (
                                          <p className="text-sm text-muted-foreground">
                                            Category: {prompt.rule_category}
                                          </p>
                                        )}
                                        {prompt.risk_score !== undefined && (
                                          <p className="text-sm text-muted-foreground">
                                            Risk Score: {(prompt.risk_score * 100).toFixed(1)}%
                                          </p>
                                        )}
                                      </div>
                                    </CardContent>
                                  </Card>
                                  
                                  {prompt.detected_entities && prompt.detected_entities.length > 0 && (
                                    <Card>
                                      <CardContent className="p-4">
                                        <h4 className="font-medium mb-2">Detected Entities</h4>
                                        <div className="flex flex-wrap gap-2">
                                          {prompt.detected_entities.map((entity, index) => (
                                            <Badge key={index} variant="outline">
                                              {JSON.stringify(entity)}
                                            </Badge>
                                          ))}
                                        </div>
                                      </CardContent>
                                    </Card>
                                  )}
                                </div>
                              </TabsContent>
                            </Tabs>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          </div>
          
          {/* Load More Button */}
          {pagination.has_more && (
            <div className="flex justify-center mt-6">
              <Button onClick={loadMore} disabled={loading} variant="outline">
                {loading ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    Loading...
                  </>
                ) : (
                  <>Load More ({pagination.total - prompts.length} remaining)</>
                )}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Prompt Details</DialogTitle>
          </DialogHeader>
          {selectedPrompt && (
            <div className="space-y-6">
              {/* User and Timing Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="font-medium mb-2">User Information</h4>
                  <p><strong>Username:</strong> {selectedPrompt.username}</p>
                  <p><strong>Full Name:</strong> {selectedPrompt.full_name}</p>
                  <p><strong>User ID:</strong> {selectedPrompt.user_id}</p>
                </div>
                <div>
                  <h4 className="font-medium mb-2">Timing</h4>
                  <p><strong>Prompt Time:</strong> {format(new Date(selectedPrompt.timestamp), 'PPpp')}</p>
                  {selectedPrompt.response_timestamp && (
                    <p><strong>Response Time:</strong> {format(new Date(selectedPrompt.response_timestamp), 'PPpp')}</p>
                  )}
                  {selectedPrompt.total_duration_ms && (
                    <p><strong>Total Duration:</strong> {selectedPrompt.total_duration_ms.toFixed(0)}ms</p>
                  )}
                </div>
              </div>
              
              {/* Content */}
              <div>
                <h4 className="font-medium mb-2">Prompt Content</h4>
                <div className="bg-muted p-4 rounded-md">
                  <p className="whitespace-pre-wrap">{selectedPrompt.prompt_text}</p>
                </div>
              </div>
              
              {selectedPrompt.response_text && (
                <div>
                  <h4 className="font-medium mb-2">AI Response</h4>
                  <div className="bg-muted p-4 rounded-md">
                    <p className="whitespace-pre-wrap">{selectedPrompt.response_text}</p>
                  </div>
                </div>
              )}
              
              {/* Detailed Metrics */}
              <Tabs defaultValue="cache" className="w-full">
                <TabsList>
                  <TabsTrigger value="cache">Cache</TabsTrigger>
                  <TabsTrigger value="llm">LLM</TabsTrigger>
                  <TabsTrigger value="firewall">Firewall</TabsTrigger>
                  <TabsTrigger value="evaluations">Evaluations</TabsTrigger>
                  <TabsTrigger value="technical">Technical</TabsTrigger>
                </TabsList>
                
                <TabsContent value="cache">
                  {selectedPrompt.cache_data ? (
                    <div className="space-y-2">
                      <p><strong>Cache Hit:</strong> {selectedPrompt.cache_data.hit ? 'Yes' : 'No'}</p>
                      {selectedPrompt.cache_data.similarity && (
                        <p><strong>Similarity Score:</strong> {(selectedPrompt.cache_data.similarity * 100).toFixed(2)}%</p>
                      )}
                      {selectedPrompt.cache_data.duration_ms && (
                        <p><strong>Lookup Time:</strong> {selectedPrompt.cache_data.duration_ms.toFixed(0)}ms</p>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No cache data available</p>
                  )}
                </TabsContent>
                
                <TabsContent value="llm">
                  {selectedPrompt.llm_data ? (
                    <div className="space-y-2">
                      {selectedPrompt.llm_data.model && (
                        <p><strong>Model:</strong> {selectedPrompt.llm_data.model}</p>
                      )}
                      {selectedPrompt.llm_data.tokens && (
                        <div>
                          <p><strong>Tokens:</strong></p>
                          <ul className="ml-4 space-y-1">
                            {selectedPrompt.llm_data.tokens.input && (
                              <li>Input: {selectedPrompt.llm_data.tokens.input.toLocaleString()}</li>
                            )}
                            {selectedPrompt.llm_data.tokens.output && (
                              <li>Output: {selectedPrompt.llm_data.tokens.output.toLocaleString()}</li>
                            )}
                            {selectedPrompt.llm_data.tokens.total && (
                              <li>Total: {selectedPrompt.llm_data.tokens.total.toLocaleString()}</li>
                            )}
                          </ul>
                        </div>
                      )}
                      {selectedPrompt.llm_data.cost && (
                        <p><strong>Cost:</strong> ${selectedPrompt.llm_data.cost.toFixed(6)}</p>
                      )}
                      {selectedPrompt.llm_data.duration_ms && (
                        <p><strong>LLM Duration:</strong> {selectedPrompt.llm_data.duration_ms.toFixed(0)}ms</p>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No LLM data available</p>
                  )}
                </TabsContent>
                
                <TabsContent value="firewall">
                  {selectedPrompt.firewall_data ? (
                    <div className="space-y-2">
                      <p><strong>Blocked:</strong> {selectedPrompt.firewall_data.blocked ? 'Yes' : 'No'}</p>
                      {selectedPrompt.firewall_data.reason && (
                        <p><strong>Reason:</strong> {selectedPrompt.firewall_data.reason}</p>
                      )}
                      {selectedPrompt.firewall_data.rule_category && (
                        <p><strong>Rule Category:</strong> {selectedPrompt.firewall_data.rule_category}</p>
                      )}
                      {selectedPrompt.firewall_data.risk_score !== undefined && (
                        <p><strong>Risk Score:</strong> {(selectedPrompt.firewall_data.risk_score * 100).toFixed(2)}%</p>
                      )}
                      {selectedPrompt.firewall_data.detected_entities && selectedPrompt.firewall_data.detected_entities.length > 0 && (
                        <div>
                          <p><strong>Detected Entities:</strong></p>
                          <pre className="text-xs bg-muted p-2 rounded mt-2">
                            {JSON.stringify(selectedPrompt.firewall_data.detected_entities, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No firewall data available</p>
                  )}
                </TabsContent>
                
                <TabsContent value="evaluations">
                  {selectedPrompt.evaluation_data && Object.keys(selectedPrompt.evaluation_data).length > 0 ? (
                    <div className="space-y-4">
                      {Object.entries(selectedPrompt.evaluation_data).map(([metric, data]) => {
                        const evalData = data as { score?: number; reasoning?: string; duration_ms?: number };
                        return (
                        <Card key={metric}>
                          <CardContent className="p-4">
                            <div className="flex items-center justify-between mb-2">
                              <h5 className="font-medium">
                                {EVALUATION_METRICS[metric as keyof typeof EVALUATION_METRICS] || metric}
                              </h5>
                              {evalData.score !== undefined && (
                                <span className={`font-bold ${getScoreColor(evalData.score)}`}>
                                  {formatEvaluationScore(evalData.score)}
                                </span>
                              )}
                            </div>
                            {evalData.reasoning && (
                              <p className="text-sm text-muted-foreground mb-2">
                                {evalData.reasoning}
                              </p>
                            )}
                            {evalData.duration_ms && (
                              <p className="text-xs text-muted-foreground">
                                Evaluation took {evalData.duration_ms.toFixed(0)}ms
                              </p>
                            )}
                          </CardContent>
                        </Card>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No evaluation data available</p>
                  )}
                </TabsContent>
                
                <TabsContent value="technical">
                  <div className="space-y-4">
                    <div>
                      <p><strong>Message ID:</strong> {selectedPrompt.message_id}</p>
                      {selectedPrompt.child_spans_count && (
                        <p><strong>Child Spans:</strong> {selectedPrompt.child_spans_count}</p>
                      )}
                    </div>
                    
                    {selectedPrompt.parent_attributes && (
                      <div>
                        <h5 className="font-medium mb-2">Parent Span Attributes</h5>
                        <pre className="text-xs bg-muted p-3 rounded overflow-auto">
                          {JSON.stringify(selectedPrompt.parent_attributes, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};