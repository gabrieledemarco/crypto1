# Algorithmic and High-Frequency Trading
## Cartea · Jaimungal · Penalva — Market Microstructure, LOB, Market Making, Pairs Trading

---

## Electronic Markets and the Limit Order Book

### LOB Structure

The **Limit Order Book (LOB)** is the central data structure of electronic markets:
- **Ask side**: resting sell orders sorted ascending by price
- **Bid side**: resting buy orders sorted descending by price
- **Best bid** (B): highest buy price; **Best ask** (A): lowest sell price
- **Mid-price**: M = (A+B)/2
- **Spread**: s = A − B (typically 1–5 bps for liquid instruments)

Order types:
- **Limit order (LO)**: placed in book, waits for matching
- **Market order (MO)**: executes immediately at best available price, consumes liquidity
- **Cancel**: removes a resting limit order

### LOB Dynamics — Key Stylised Facts

1. **Spread mean-reverts** to a liquidity-determined floor
2. **Order flow is autocorrelated**: MO buys cluster after MO buys (herding, momentum)
3. **Depth is asymmetric**: imbalance between bid/ask depth predicts short-term price moves
4. **Trades arrive as Hawkes processes** — self-exciting, clusters in time
5. **Return autocorrelation**: negative at tick frequency (bid-ask bounce), positive at 5–30 min

---

## Stochastic Optimal Control and HJB Equations

The core mathematical tool for optimal execution and market making.

### Framework

State: (x_t, S_t, t) where x_t = inventory, S_t = mid-price  
Control: u_t = trading rate / posted quotes  
Performance criterion: maximise E[terminal wealth + α·inventory_penalty]

### Hamilton-Jacobi-Bellman (HJB) Equation

For value function V(t, x, S):
```
∂V/∂t + sup_u [L^u V] = 0
V(T, x, S) = x·S − φ·x²   (terminal condition: liquidate remaining inventory)
```

where L^u is the infinitesimal generator of the state process under control u, and φ is a terminal inventory penalty.

**General solution approach**:
1. Guess ansatz: V(t,x,S) = x·S + f(t,x) (affine in S)
2. Reduce to PDE/ODE in f(t,x)
3. Solve analytically (linear model) or numerically

---

## Optimal Execution — Continuous Trading

### Models I & II (Cartea-Jaimungal)

**Model I**: trader controls execution rate r_t (shares/time), no adverse selection
```
dS_t = μ dt + σ dW_t               (midprice)
dX_t = r_t dt                       (inventory)
revenue per unit: S_t − η·r_t       (temporary impact η)
```

Optimal rate:
```
r_t* = (x_t / (T−t)) + (μ / (2η))·(T−t)
```
→ VWAP baseline + momentum overlay (trade faster when drift μ is favourable)

**Model II**: includes **adverse selection** — when the market order queue is long, you know momentum is building against you.

Short-term alpha / order-flow signal:
```
α_t = ρ·(N_t^buy − N_t^sell)   (buy minus sell MO arrivals)
```

Optimal rate with adverse selection:
```
r_t* = r_VWAP + c₁·α_t + c₂·(x_t/remaining_time)
```

Trade faster if α_t is in your direction, slower if it signals adverse price move.

---

## Limit and Market Orders Combined

Traders can choose *how* to execute (LO vs MO):
- **LO**: incurs no spread cost but faces **execution risk** (may not fill)
- **MO**: guaranteed fill but pays spread

### Optimal Mixed Strategy

Value function separates into:
- MO component: optimal when inventory deviates too far from target
- LO component: use for gradual accumulation at better prices

**Inventory band**: maintain inventory x_t ∈ [x̄ − Δ, x̄ + Δ]. When inventory breaches the band, send an MO to rebalance; otherwise, lean on LOs.

**Fill probability of LO at distance δ from mid**:
```
P(fill) ≈ exp(−κ·δ)
```
where κ is the order-book depth parameter (estimated from historical queue data).

---

## Volume Targeting: VWAP and POV

### VWAP (Volume-Weighted Average Price)

Target: execute at or better than VWAP = ∑(P_i·V_i)/∑V_i

**Algorithm**: track cumulative volume fraction and match it with your execution fraction
```
participation_rate = target_volume / total_volume
quantity_t = participation_rate · V_t^market
```

**Shortfall vs VWAP**: VWAP benchmarks are gamed. IS (implementation shortfall) is harder to game but requires predicting total volume.

### POV (Percentage of Volume)

Simpler: trade a fixed fraction ρ of every market print.
```
quantity_t = ρ · V_t^market
```

Risk: if ρ > 0.3, you become the market; your orders generate the volume you track → feedback loop.

**Optimal ρ** given urgency τ:
```
ρ* = min(ρ_max, T / (T + τ_alpha_decay))
```

---

## Market Making

### Avellaneda-Stoikov Model

Market maker posts bid quote q^b = M − δ^b and ask quote q^a = M + δ^a.

Inventory dynamics:
```
dX_t = dN_t^a − dN_t^b    (buy fills minus sell fills)
```

Fill intensities (decreasing in spread):
```
λ^a(δ^a) = Λ·exp(−κ·δ^a)
λ^b(δ^b) = Λ·exp(−κ·δ^b)
```

**Optimal quotes** (risk-neutral, continuous):
```
δ^a* = δ^b* = (1/κ) + (γσ²/2)·(T−t)
```

**Skewed quotes** to manage inventory:
```
r_t = M − γσ²·x_t·(T−t)       (reservation price, biased vs mid)
δ^a* = r_t + (1/κ) + (γσ²/2)·(T−t)
δ^b* = r_t − (1/κ) − (γσ²/2)·(T−t)
```

→ If long (x_t > 0), r_t < M: post ask closer to mid, bid further → lean to sell inventory

### Adverse Selection

When a market order arrives, it's more likely informed (toxic) if:
- Order size is large relative to displayed depth
- It arrives shortly after a news event
- It is followed by further same-direction orders

**Adverse selection cost** per trade:
```
AS = E[ΔM | MO arrival] ≈ c · σ
```

Maker quotes must be wide enough: `δ > AS + spread_cost/2`

**Net P&L per fill** = δ (spread captured) − AS (adverse selection) − inventory_risk

### Inventory Risk Management

- **Hard inventory limit**: |x_t| ≤ I_max → force rebalance with MO
- **Soft limit**: widen quotes symmetrically when |x_t| > threshold
- **Asymmetric quoting**: pull quotes on one side when inventory is extreme
- **Stop-loss on inventory**: if position P&L < −L, liquidate immediately

---

## Pairs Trading and Statistical Arbitrage

### Cointegrated Pairs

Two assets (S¹, S²) are cointegrated if:
```
Z_t = S_t¹ − β·S_t²    is stationary (mean-reverting)
```

Estimate β using OLS or Engle-Granger cointegration test.

**Spread dynamics**:
```
dZ_t = κ(θ − Z_t)dt + σ_z·dW_t    (Ornstein-Uhlenbeck)
```

Half-life of mean reversion: `t_{1/2} = ln(2)/κ`

### Optimal Pairs Trading Strategy

Control: q_t = position in spread (long spread = long S¹, short S²)

HJB solution gives optimal position:
```
q_t* = (θ − Z_t) · κ / (γσ_z²)·(1/(T−t+1/κ))
```

**Practical rule**: enter when |Z_t − θ| > 2σ_z, exit when Z_t ≈ θ

**Risk**: cointegration breaks (regime change, fundamental divergence). Stop-loss: close position if |Z_t| > 4σ_z or if cointegration test fails on rolling window.

---

## Order Imbalance and Short-Term Alpha

**Order Imbalance (OI)**:
```
OI_t = (N_t^buy − N_t^sell) / (N_t^buy + N_t^sell) ∈ [−1, +1]
```

**Predictive power**: OI over last 5–60 seconds predicts next 1–30 second midprice change.

```
E[ΔM_{t+τ} | OI_t] ≈ α·OI_t
```

**Using OI in execution**: if selling, delay execution when OI > threshold (buyers dominate = price likely to rise → sell at better price shortly)

**Using OI in market making**: lean quotes toward seller when OI > 0 to avoid filling on the toxic side.

**Decay of predictive power**: OI signal decays as power law ~ τ^{−0.5} for τ in seconds. Useless beyond 5 minutes for most assets.

---

## Stochastic Optimal Control Summary

| Problem | State | Control | Key Insight |
|---------|-------|---------|-------------|
| Optimal execution | (x_t, S_t) | trading rate r_t | Balance IS vs. price risk |
| Market making | (X_t, S_t) | δ^a, δ^b | Inventory + adverse selection tradeoff |
| Pairs trading | (q_t, Z_t) | position q_t | OU process → contrarian sizing |
| VWAP targeting | (x_t, V_t^cum) | r_t | Match volume participation rate |

---

## Key Parameters to Estimate from Data

| Parameter | Estimation Method |
|-----------|------------------|
| σ (volatility) | Realised vol from 1-min returns |
| κ (mean-reversion rate) | OLS on spread differences: ΔZ_t = −κ·Z_t + ε |
| η (temporary impact) | Regress price impact on signed order flow |
| κ (fill rate decay) | Regress fill probability on LOB queue position |
| Λ (order arrival rate) | Count MOs per unit time, fit Poisson/Hawkes |
| AS (adverse selection) | Measure midprice change post-fill: E[M_{t+τ}−M_t | fill] |

---

## Integration with Strategy Generation

1. **Pre-trade**: use IS model to estimate execution cost, net of which alpha exceeds hurdle
2. **During trade**: use OI and LOB imbalance to time individual orders
3. **Market making sub-strategy**: add MM overlay to a directional strategy to reduce slippage
4. **Pairs signals**: use cointegration-based signals as a component in multi-factor alpha
5. **Post-trade**: reconcile expected vs actual IS; adjust impact model

---

## References

- Cartea, Jaimungal & Penalva (2015), *Algorithmic and High-Frequency Trading*, Cambridge
- Avellaneda & Stoikov (2008), "High-frequency trading in a limit order book"
- Guo, de Larrard & Ruan (2017), "Optimal posting price of limit orders"
