# Optimal Execution of Portfolio Transactions
## Almgren-Chriss Model · Implementation Shortfall · Adaptive Strategies

---

## Core Problem

You hold X shares and must liquidate them within T periods. Every trade moves the market against you (market impact). Sell too fast → large impact costs. Sell too slow → large price-risk exposure. The goal: find the trajectory {x_t} that minimises a mean-variance objective over total execution cost.

**Implementation Shortfall (IS)** = paper-portfolio value − actual proceeds
= ∑ v_t · h(v_t)·Δt + ∑ g(v_t)·x_t·Δt

where v_t = dx/dt is the trading rate, h(v) is **temporary impact**, g(v) is **permanent impact**.

---

## Market Model

**Arithmetic random walk** (Almgren-Chriss):
```
S_t = S_{t-1} + σ·ξ_t    (ξ_t i.i.d. N(0,1))
```

**Effective (realised) price per share**:
```
S̃_t = S_t − h(v_t)
```

**Temporary impact** (linear default): `h(v) = η·v`  
**Permanent impact** (linear default): `g(v) = γ·v`

η = temporary impact coefficient ($/share per share/day)  
γ = permanent impact coefficient (price change per unit volume)

---

## Mean-Variance Objective

Minimise:
```
E[IS] + λ · Var[IS]
```

λ = risk-aversion parameter (higher λ → faster execution to cut variance)

**Expected cost**:
```
E[IS] = η·∫v²dt + (γ/2)·X²
```

**Variance**:
```
Var[IS] = σ²·∫x_t² dt
```

where x_t = shares remaining at time t (x_0 = X, x_T = 0).

---

## Static Optimal Trajectory (Almgren-Chriss)

The closed-form optimal schedule is:
```
x_t = X · sinh(κ(T−t)) / sinh(κT)
```

**Urgency parameter**:
```
κ = √(λσ²/η)
```

Trading rate:
```
v_t = −ẋ_t = X·κ·cosh(κ(T−t)) / sinh(κT)
```

**Interpretation of κ**:
- κ → 0: uniform (VWAP-like) schedule, slow, low impact
- κ → ∞: front-loaded, fast, high variance reduction
- Typical range for equities: 0.1–2.0 day⁻¹

**Efficient Frontier of Execution**: varying λ traces a curve in (E[IS], Var[IS]) space, analogous to Markowitz. Each point represents a different urgency level.

---

## Adaptive Strategies

Static trajectories fix the schedule at t=0 regardless of price moves. Adaptive strategies condition on the price path and outperform statics in mean-variance terms.

**Key insight** (Lorenz 2008): Once you model the full joint distribution over price paths, you can construct path-dependent policies:

```
v_t = f(S_t, x_t, t)
```

that achieve strictly lower expected cost at the same variance, or lower variance at the same cost — i.e., **they shift the efficient frontier toward the origin**.

### Aggressive-in-the-Money (AIM) Principle

The most important heuristic in execution:

> **If the price moves in your favour (favourable for liquidation), accelerate. If it moves against you, slow down.**

For a sell programme:
- Price rises → higher proceeds per share → sell faster to lock in gains
- Price falls → lower proceeds → wait, avoid selling into weakness

Formally, AIM strategies have ∂v_t/∂S_t < 0 for a sell (sell faster when price is higher).

**Why this works**: It exploits short-term mean reversion and locks in gains from transient price rises, at the cost of slightly higher execution variance.

---

## Portfolio Market Power

Define the **market power parameter**:
```
μ = γX / σ√T
```

- μ >> 1: large order relative to volatility-scaled volume; permanent impact dominates
- μ << 1: small order; market impact negligible

The adaptive advantage over static strategies grows with μ. For large institutional orders (μ ≈ 0.5–2), adaptive scheduling meaningfully reduces costs.

---

## Practical Heuristics

1. **Estimate η from intraday data**: regress price impact on order flow; typical η ≈ 0.1–1.0 bps per % of ADV.

2. **Set λ from your mandate**: if tracking TE limits your risk, use higher λ. If you have a wide window, use smaller λ (VWAP-like).

3. **Front-loading bias**: most real strategies are slightly front-loaded vs TWAP because early hours have lower spread, higher liquidity.

4. **Volume participation**: common proxy for urgency: target 10–25% of volume (POV). Maps to specific κ values per stock.

5. **Time limit**: for small-cap illiquid names, T is effectively bounded by liquidity; run IS model to find if shortfall-optimal T is longer or shorter.

6. **Transaction cost model calibration**: backtest simulated IS vs. actual IS. If model under-predicts, η is underestimated — recalibrate after every 50–100 executions.

---

## Connections to Strategy Design

When building a strategy, factor in execution costs:

- **Alpha decay**: if your signal decays with half-life τ, urgency κ should be ~ 1/τ
- **Post-trade analysis**: compare expected IS (model) to actual IS to detect execution alpha or slippage
- **Liquidation planning**: for leveraged strategies, pre-compute liquidation IS at multiple urgency levels; add to risk limit
- **Market impact in backtest**: subtract estimated IS from each trade's PnL using: `cost ≈ η·v·|trade_size|`

---

## Key Formulas Summary

| Quantity | Formula |
|----------|---------|
| Urgency | κ = √(λσ²/η) |
| Optimal remaining shares | x_t = X·sinh(κ(T−t))/sinh(κT) |
| Trading rate | v_t = Xκ·cosh(κ(T−t))/sinh(κT) |
| Expected IS | E[IS] ≈ η·X²κ·coth(κT)/2 |
| Variance of IS | Var[IS] ≈ σ²X²·(T − tanh(κT)/κ)/2 |
| Market power | μ = γX/(σ√T) |

---

## References

- Almgren & Chriss (2001), "Optimal execution of portfolio transactions", *J. Risk* 3(2)
- Lorenz (2008), "Optimal trading strategies", ETH Zurich
- Gatheral (2010), "No-dynamic-arbitrage and market impact"
