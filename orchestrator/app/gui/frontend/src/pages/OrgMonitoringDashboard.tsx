import React, { useMemo, useState, useEffect, type ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Activity, RefreshCcw, Download, AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { webSocketService } from "@/services/websocket";

// ---- MoolAI dark theme (from screenshot-inspired palette) ----
const THEME = {
	bg: "#0B0F1A", // app background
	card: "#121826", // card background
	border: "#232A3A", // card borders
	text: "#FFFFFF", // force white text for max contrast
	muted: "#D1D5DB", // softer white/gray
	primary: "#F97316", // orange accents (buttons, highlights)
	secondary: "#22C55E", // green (Connected/success)
	warning: "#F59E0B", // amber for warnings
	danger: "#EF4444", // errors
} as const;

// -----------------------------
// TypeScript Data Types
// -----------------------------
export interface RunRow {
	chatId: string;
	model: string;
	evaluationTime: string; // ISO string
	inputTokens: number;
	outputTokens: number;
	accuracy: number;
	relevance: number;
	hallucination: number;
	diff: number; // delta vs baseline in percent
	status: "running" | "complete";
	evaluationType?: string;
	evaluationId?: number;
}

interface EvaluationRunsResponse {
	time_range: {
		start: string;
		end: string;
	};
	pagination: {
		limit: number;
		offset: number;
		total: number;
	};
	summary: {
		total_evaluations: number;
		completed_evaluations: number;
		avg_accuracy: number;
		avg_relevance: number;
		avg_hallucination: number;
		completion_rate: number;
	};
	runs: RunRow[];
	data_source: string;
}

interface MetricCardProps {
	title: string;
	value: string | number;
	suffix?: string;
	trend?: number;
	icon?: ReactNode;
	helpText?: string;
}

export default function OrgMonitoringDashboard() {
	const [runs, setRuns] = useState<RunRow[]>([]);
	const [summary, setSummary] = useState<EvaluationRunsResponse['summary'] | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
	
	// Real-time WebSocket state
	const [connectionState, setConnectionState] = useState(webSocketService.getConnectionState());
	const [isSubscribed, setIsSubscribed] = useState(false);
	
	// Fetch evaluation runs from backend
	const fetchEvaluationRuns = async () => {
		setLoading(true);
		setError(null);
		
		try {
			// Get last 30 days of data
			const endDate = new Date();
			const startDate = new Date();
			startDate.setDate(startDate.getDate() - 30);
			
			// Get user_id from WebSocket session data
			const sessionData = webSocketService.getSession();
			const userId = sessionData?.user_id || 'default_user';
			
			const params = new URLSearchParams({
				start_date: startDate.toISOString(),
				end_date: endDate.toISOString(),
				limit: '50',
				offset: '0',
				user_id: userId
			});

			const response = await fetch(`/api/v1/analytics/evaluation-runs?${params}`);
			
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}: Failed to fetch evaluation runs`);
			}
			
			const data: EvaluationRunsResponse = await response.json();

			// Convert backend 0-1 values to percentages for display
			const convertedRuns = data.runs.map(run => ({
				...run,
				accuracy: run.accuracy * 100,
				relevance: run.relevance * 100,
				hallucination: (1 - run.hallucination) * 100, // Invert: 1.0 backend = 0% display
			}));

			setRuns(convertedRuns);

			// Convert summary values to percentages for display
			setSummary(data.summary ? {
				...data.summary,
				avg_accuracy: data.summary.avg_accuracy * 100,
				avg_relevance: data.summary.avg_relevance * 100,
				avg_hallucination: data.summary.avg_hallucination, // Keep as-is since composite score calculation uses original values
			} : null);
			setLastRefresh(new Date());
			
		} catch (err) {
			console.error('Failed to fetch evaluation runs:', err);
			setError(err instanceof Error ? err.message : 'Failed to fetch evaluation runs');
		} finally {
			setLoading(false);
		}
	};

	// Load data on component mount and set up auto-refresh
	useEffect(() => {
		fetchEvaluationRuns(); // Load immediately, don't wait for WebSocket
		
		// Establish WebSocket connection with authentication
		if (connectionState === 'disconnected') {
			webSocketService.connect({ user_id: 'default_user' }).catch(error => {
				console.error('Failed to establish WebSocket connection:', error);
			});
		}
		
		// Set up auto-refresh every 30 seconds
		const interval = setInterval(() => {
			if (!loading) {
				fetchEvaluationRuns();
			}
		}, 30000); // 30 seconds

		return () => clearInterval(interval);
	}, []); // Remove connectionState dependency, fetch from database directly

	// Real-time WebSocket subscription for immediate updates
	useEffect(() => {
		const setupSubscription = async () => {
			try {
				if (connectionState === 'connected' && !isSubscribed) {
					// Subscribe to analytics updates for real-time evaluation data
					await webSocketService.subscribeToAnalytics();
					setIsSubscribed(true);
					
					// Listen for evaluation updates
					const cleanup = webSocketService.addEventListener('evaluation_runs_update', (data) => {
						// Add new evaluation run to the beginning of the list
						const newRun: RunRow = {
							chatId: data.chat_id || data.message_id || 'unknown',
							model: data.model || 'unknown',
							evaluationTime: data.timestamp || new Date().toISOString(),
							inputTokens: data.prompt_tokens || 0,
							outputTokens: data.completion_tokens || 0,
							accuracy: (data.evaluation_scores?.answer_correctness?.score || 0) * 100,
							relevance: (data.evaluation_scores?.answer_relevance?.score || 0) * 100,
							hallucination: (1 - (data.evaluation_scores?.hallucination_score?.score || 0)) * 100, // Invert: 1.0 backend = 0% display
							diff: 0, // Could be calculated vs baseline
							status: 'complete',
							evaluationType: 'automated',
							evaluationId: data.message_id
						};
						
						setRuns(prev => [newRun, ...prev]);
						setSummary(prev => prev ? {
							...prev,
							total_evaluations: prev.total_evaluations + 1,
							completed_evaluations: prev.completed_evaluations + 1
						} : null);
						setLastRefresh(new Date());
					});
					
					return cleanup;
				}
			} catch (error) {
				console.error('Failed to set up real-time subscription:', error);
			}
		};

		if (connectionState === 'connected') {
			setupSubscription();
		}
	}, [connectionState, isSubscribed]);

	// Monitor connection state
	useEffect(() => {
		const cleanup = webSocketService.onStateChange(setConnectionState);
		return cleanup;
	}, []);

	// Calculate composite score from summary data
	const composite = useMemo(() => {
		if (!summary) return 0;
		// Summary values are already converted to percentages in fetchEvaluationRuns
		const accuracyPercent = summary.avg_accuracy; // Already percentage
		const relevancePercent = summary.avg_relevance; // Already percentage
		const hallucinationPercent = summary.avg_hallucination * 100; // Original 0-1 value, 100 = no hallucination
		const score = 0.45 * accuracyPercent + 0.45 * relevancePercent + 0.1 * hallucinationPercent;
		return Math.round(score);
	}, [summary]);

	const handleRefresh = () => {
		fetchEvaluationRuns();
	};

	const handleExport = () => {
		// Create CSV export
		const csvHeaders = [
			'Chat ID', 'Model', 'Evaluation Time', 'Input Tokens', 'Output Tokens',
			'Accuracy %', 'Relevance %', 'Hallucination %', 'Diff vs Baseline', 'Status'
		];
		
		const csvRows = runs.map(run => [
			run.chatId,
			run.model,
			run.evaluationTime,
			run.inputTokens.toString(),
			run.outputTokens.toString(),
			run.accuracy.toString(),
			run.relevance.toString(),
			run.hallucination.toString(),
			run.diff.toFixed(1),
			run.status
		]);
		
		const csvContent = [csvHeaders, ...csvRows]
			.map(row => row.map(field => `"${field}"`).join(','))
			.join('\n');
		
		const blob = new Blob([csvContent], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = `evaluation-runs-${new Date().toISOString().split('T')[0]}.csv`;
		link.click();
		URL.revokeObjectURL(url);
	};

	return (
		<div className="p-6 space-y-6" style={{ background: THEME.bg, color: THEME.text }}>
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-2xl font-semibold" style={{ color: THEME.text }}>Organization Monitoring</h1>
					<p className="text-sm" style={{ color: THEME.muted }}>
						Unified view of evaluations across models and environments.
						{lastRefresh && (
							<span className="ml-2">
								Last updated: {lastRefresh.toLocaleTimeString()}
							</span>
						)}
					</p>
				</div>
				<div className="flex items-center gap-2">
					<Badge variant={connectionState === 'connected' ? 'default' : 'secondary'}>
						{connectionState === 'connected' ? '🟢 Live' : '🟡 Database'}
					</Badge>
					<Badge variant="secondary">
						🔄 Auto-refresh (30s)
					</Badge>
					<Button 
						variant="outline" 
						onClick={handleRefresh}
						disabled={loading}
						style={{ color: THEME.text, borderColor: THEME.border, background: "transparent" }}
					>
						<RefreshCcw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
						Refresh
					</Button>
					<Button 
						onClick={handleExport}
						disabled={loading || runs.length === 0}
						style={{ background: THEME.primary, color: THEME.text }}
					>
						<Download className="h-4 w-4 mr-2" />
						Export
					</Button>
				</div>
			</div>

			{/* Error Display */}
			{error && (
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						{error}
						<Button
							variant="ghost"
							size="sm"
							onClick={handleRefresh}
							className="ml-2 h-auto p-1 text-xs"
						>
							Retry
						</Button>
					</AlertDescription>
				</Alert>
			)}

			{/* KPI Row */}
			{summary && (
				<div className="grid grid-cols-1 md:grid-cols-5 gap-4">
					<MetricCard
						title="Composite Score"
						value={`${composite}`}
						suffix="/100"
						icon={<Activity className="h-4 w-4" />}
						helpText="Live weighted average: 45% accuracy + 45% relevance + 10% (no hallucination). Updates in real-time."
					/>
					<MetricCard
						title="Avg Accuracy"
						value={`${summary.avg_accuracy.toFixed(1)}%`}
						helpText="How correctly the AI answers questions. Higher is better."
					/>
					<MetricCard
						title="Avg Relevance"
						value={`${summary.avg_relevance.toFixed(1)}%`}
						helpText="How well the AI response addresses the user's question. Higher is better."
					/>
					<MetricCard
						title="Hallucination Rate"
						value={`${((1 - summary.avg_hallucination) * 100).toFixed(1)}%`}
						helpText="Percentage of responses containing false or fabricated information. Lower is better."
					/>
					<MetricCard
						title="Total Evaluations"
						value={Intl.NumberFormat().format(summary.total_evaluations)}
						helpText="Number of AI responses evaluated in the last 30 days."
					/>
				</div>
			)}

			{/* Loading State */}
			{loading && (
				<div className="flex items-center justify-center p-8">
					<div className="flex items-center space-x-2">
						<RefreshCcw className="h-5 w-5 animate-spin" style={{ color: THEME.primary }} />
						<span style={{ color: THEME.muted }}>Loading evaluation runs...</span>
					</div>
				</div>
			)}

			{/* Runs Table */}
			{!loading && runs.length > 0 && (
				<Card style={{ background: THEME.card, borderColor: THEME.border, color: THEME.text }}>
					<CardHeader>
						<CardTitle className="text-base" style={{ color: THEME.text }}>
							Recent Evaluation Runs ({runs.length} items)
						</CardTitle>
					</CardHeader>
					<CardContent>
						<Table style={{ color: THEME.text }}>
							<TableHeader>
								<TableRow>
									<TableHead style={{ color: THEME.text }}>Conversation ID</TableHead>
									<TableHead style={{ color: THEME.text }}>AI Model</TableHead>
									<TableHead style={{ color: THEME.text }}>Evaluated At</TableHead>
									<TableHead style={{ color: THEME.text }}>Input Size</TableHead>
									<TableHead style={{ color: THEME.text }}>Output Size</TableHead>
									<TableHead style={{ color: THEME.text }}>Accuracy</TableHead>
									<TableHead style={{ color: THEME.text }}>Relevance</TableHead>
									<TableHead style={{ color: THEME.text }}>Hallucination</TableHead>
									<TableHead style={{ color: THEME.text }}>vs Baseline</TableHead>
									<TableHead style={{ color: THEME.text }}>Status</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{runs.map((run) => (
									<TableRow key={`${run.chatId}-${run.evaluationId || run.evaluationTime}`}>
										<TableCell className="font-mono text-xs" style={{ color: THEME.text }}>
											{run.chatId}
										</TableCell>
										<TableCell style={{ color: THEME.text }}>{run.model}</TableCell>
										<TableCell style={{ color: THEME.text }}>
											{new Date(run.evaluationTime).toLocaleString()}
										</TableCell>
										<TableCell style={{ color: THEME.text }}>
											{run.inputTokens.toLocaleString()}
										</TableCell>
										<TableCell style={{ color: THEME.text }}>
											{run.outputTokens.toLocaleString()}
										</TableCell>
										<TableCell style={{ color: THEME.text }}>{run.accuracy.toFixed(1)}%</TableCell>
										<TableCell style={{ color: THEME.text }}>{run.relevance.toFixed(1)}%</TableCell>
										<TableCell style={{ color: THEME.text }}>{run.hallucination.toFixed(1)}%</TableCell>
										<TableCell>
											<Badge variant={run.diff >= 0 ? "default" : "destructive"}>
												{run.diff >= 0 ? "+" : ""}{run.diff.toFixed(1)}%
											</Badge>
										</TableCell>
										<TableCell>
											<Badge variant={run.status === "complete" ? "default" : "secondary"}>
												{run.status}
											</Badge>
										</TableCell>
									</TableRow>
								))}
							</TableBody>
						</Table>
					</CardContent>
				</Card>
			)}

			{/* Empty State */}
			{!loading && !error && runs.length === 0 && (
				<Card style={{ background: THEME.card, borderColor: THEME.border, color: THEME.text }}>
					<CardContent className="text-center py-8">
						<Activity className="h-12 w-12 mx-auto mb-4" style={{ color: THEME.muted }} />
						<h3 className="text-lg font-medium mb-2" style={{ color: THEME.text }}>
							No evaluation runs found
						</h3>
						<p className="text-sm mb-4" style={{ color: THEME.muted }}>
							No evaluation data available for the selected time period.
						</p>
						<Button onClick={handleRefresh} style={{ background: THEME.primary, color: THEME.text }}>
							<RefreshCcw className="h-4 w-4 mr-2" />
							Refresh Data
						</Button>
					</CardContent>
				</Card>
			)}

			{/* Footer */}
			<div className="text-xs" style={{ color: THEME.muted }}>
				Data source: Orchestrator database • 
				Showing evaluations from last 30 days • 
				{summary && `${summary.completion_rate.toFixed(1)}% completion rate`}
			</div>
		</div>
	);
}

function MetricCard({ title, value, suffix = "", trend, icon, helpText }: MetricCardProps) {
	return (
		<Card style={{ background: THEME.card, borderColor: THEME.border, color: THEME.text }}>
			<CardHeader className="pb-2">
				<div className="flex items-center justify-between">
					<CardTitle className="text-sm font-medium" style={{ color: THEME.muted }}>
						{title}
					</CardTitle>
					{icon}
				</div>
			</CardHeader>
			<CardContent>
				<div className="flex items-baseline gap-2">
					<span className="text-2xl font-semibold" style={{ color: THEME.text }}>
						{value}
					</span>
					<span className="text-sm" style={{ color: THEME.muted }}>
						{suffix}
					</span>
				</div>
				{typeof trend === "number" && (
					<div className="text-xs mt-1" style={{ color: trend >= 0 ? THEME.secondary : THEME.danger }}>
						{trend >= 0 ? "+" : ""}
						{trend}% vs prev period
					</div>
				)}
				{helpText && (
					<p className="text-xs mt-2" style={{ color: THEME.muted }}>
						{helpText}
					</p>
				)}
			</CardContent>
		</Card>
	);
}