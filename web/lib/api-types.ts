/**
 * Shared TypeScript types for FastAPI response shapes.
 * Components and hooks import from here rather than defining inline casts.
 */

export interface ApiRunListItem {
  id: string;
  name: string;
  ticker: string;
  timeframe: string;
  status: string;
  strategy_id?: string | null;
  params: Record<string, unknown>;
  created_at: string;
  start_date?: string | null;
  end_date?: string | null;
  sharpe?: number | null;
  cagr?: number | null;
  max_dd?: number | null;
  pf?: number | null;
  n_trades?: number | null;
  win_rate?: number | null;
}

export interface ApiTrade {
  entry_time: string;
  exit_time: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  exit_reason?: string;
}

export interface ApiEquityPoint {
  i: number;
  v: number;
  dd: number;
  oos?: boolean;
}

export interface ApiMCResult {
  p_profit?: number;
  p_ruin?: number;
  sharpe_ci?: [number, number];
  sharpe_lower?: number;
  sharpe_upper?: number;
  p_daily_dd_1?: number;
  p_daily_dd_5?: number;
  p_daily_dd_10?: number;
  var_95?: number;
  cvar_95?: number;
  finals?: number[];
  cagr_p5?: number;
  cagr_p50?: number;
  cagr_p95?: number;
  dd_p5?: number;
  dd_p50?: number;
  dd_p95?: number;
  paths?: number[][];
}

export interface ApiWfoFold {
  fold: number;
  is_start?: string | null;
  is_end?: string | null;
  oos_start?: string | null;
  oos_end?: string | null;
  is_sharpe?: number | null;
  oos_sharpe?: number | null;
  is_cagr?: number | null;
  oos_cagr?: number | null;
  is_trades?: number | null;
  oos_trades?: number | null;
}

export interface ApiStrategy {
  id: string;
  name: string;
  strategy_type?: string;
  config?: Record<string, unknown>;
  code?: string;
  starred?: boolean;
  status?: string;
  run_ref?: string | null;
  created_at?: string;
}

export interface EvaluationScores {
  alpha_source: number;       // 1-5
  signal_logic: number;
  risk_management: number;
  regime_sensitivity: number;
  statistical_robustness: number;
  implementation_quality: number;
}

export interface StrategyEvaluation {
  scores: EvaluationScores;
  overall_score: number;      // 1.0-10.0
  strengths: string[];
  weaknesses: string[];
  specific_improvements: string[];
  fatal_flaws: string[];
  verdict: 'promote' | 'iterate' | 'reject';
  verdict_rationale: string;
}

export interface StrategyBrief {
  regime_assessment: string;
  dominant_pattern: string;
  strategy_type: string;
  entry_logic: string;
  recommended_indicators: string[];
  entry_filters: string[];
  risk_params: {
    sl_mult: number;
    tp_mult: number;
    active_hours: [number, number];
    direction: string;
    risk_per_trade: number;
  };
  patterns_to_avoid: string[];
  edge_hypothesis: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface VibeV2Progress {
  phase: string;
  pct?: number;
  msg?: string;
  text?: string;
  brief?: StrategyBrief;
  metrics?: Record<string, unknown>;
  result?: StrategyEvaluation;
  verdict?: string;
  attempt?: number;
  strategy_id?: string;
  name?: string;
}
