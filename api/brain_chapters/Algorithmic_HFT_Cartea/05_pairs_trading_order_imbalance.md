# Capitolo 5: Pairs Trading, Cointegrazione e Order Imbalance

> **Fonte**: Algorithmic and High-Frequency Trading — Cartea, Jaimungal & Penalva, Cambridge 2015, Cap. 11–12

## Pairs Trading — Modello OU

### Cointegrazione

Due asset $(S^1, S^2)$ sono **cointegrati** se esiste $\beta$ tale che:

$$Z_t = S^1_t - \beta\,S^2_t \quad \text{è stazionario (mean-reverting)}$$

Stima di $\beta$ con OLS (Engle-Granger):

```python
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS

def find_cointegrated_pairs(prices: pd.DataFrame,
                             significance: float = 0.05) -> list:
    """
    Trova coppie cointegrate in un universo di asset.
    
    Returns: lista di tuple (asset1, asset2, beta, adf_pvalue)
    """
    assets = prices.columns.tolist()
    pairs = []
    
    for i, a1 in enumerate(assets):
        for a2 in assets[i+1:]:
            # Test di cointegrazione Engle-Granger
            _, pvalue, _ = coint(prices[a1], prices[a2])
            
            if pvalue < significance:
                # Stima beta con OLS
                y = prices[a1].values
                X = np.column_stack([prices[a2].values, np.ones(len(y))])
                beta_full = np.linalg.lstsq(X, y, rcond=None)[0]
                beta = beta_full[0]
                
                # ADF test sullo spread
                spread = prices[a1] - beta * prices[a2]
                adf_result = adfuller(spread.dropna())
                
                pairs.append({
                    'asset1': a1, 'asset2': a2,
                    'beta': beta,
                    'coint_pvalue': pvalue,
                    'adf_pvalue': adf_result[1],
                    'adf_stat': adf_result[0]
                })
    
    return sorted(pairs, key=lambda x: x['coint_pvalue'])
```

### Dinamica Ornstein-Uhlenbeck dello Spread

$$dZ_t = \kappa(\theta - Z_t)\,dt + \sigma_Z\,dW_t \qquad \text{(processo OU)}$$

- $\theta$: livello di equilibrio dello spread
- $\kappa$: velocità di mean-reversion
- $\sigma_Z$: volatilità dello spread

**Emivita** della mean-reversion:

$$t_{1/2} = \frac{\ln 2}{\kappa}$$

Target pratico: $t_{1/2} \in [1\,\text{ora},\; 5\,\text{giorni}]$.

```python
from scipy.optimize import minimize
from scipy.stats import norm

def calibrate_ou(spread: pd.Series, dt: float = 1/252) -> dict:
    """
    Calibra parametri OU (kappa, theta, sigma_Z) sullo spread.
    
    Stima con maximum likelihood (discretizzazione Euler-Maruyama).
    """
    spread = spread.dropna().values
    n = len(spread)
    
    def neg_log_likelihood(params):
        kappa, theta, sigma = params
        if kappa <= 0 or sigma <= 0:
            return 1e10
        
        # Distribuzione condizionale: Z_{t+1} | Z_t ~ N(mu, var)
        mu  = spread[:-1] * np.exp(-kappa*dt) + theta*(1 - np.exp(-kappa*dt))
        var = sigma**2 * (1 - np.exp(-2*kappa*dt)) / (2*kappa)
        
        ll = norm.logpdf(spread[1:], loc=mu, scale=np.sqrt(var))
        return -np.sum(ll)
    
    result = minimize(neg_log_likelihood,
                      x0=[1.0, spread.mean(), spread.std()],
                      method='Nelder-Mead')
    
    kappa, theta, sigma_Z = result.x
    half_life = np.log(2) / kappa
    
    return {'kappa': kappa, 'theta': theta, 'sigma_Z': sigma_Z,
            'half_life_days': half_life / dt}
```

---

## Strategia di Pairs Trading Ottimale (Cap. 11)

### Bande Ad Hoc vs Ottimali

**Regola pratica (bande ad hoc)**:
- Entra **long spread** se $Z_t < \theta - 2\sigma_Z$
- Entra **short spread** se $Z_t > \theta + 2\sigma_Z$
- Esci se $Z_t \approx \theta$

**Problema**: le bande ad hoc ignorano costi di transazione e rischi di rottura della cointegrazione.

### Strategia Ottimale con Controllo Stocastico (Cap. 11.4)

Con processo OU e utility quadratica, la posizione ottimale nello spread è:

$$q_t^* = \frac{\kappa(\theta - Z_t)}{\gamma\,\sigma_Z^2} \cdot \frac{1}{T-t + 1/\kappa}$$

- Posizione **contrarian** rispetto allo spread (long se spread basso, short se alto)
- Scala con l'urgenza del segnale $(\theta - Z_t)/\sigma_Z$ (standardizzato)
- Decade a zero verso la scadenza $T$

```python
def optimal_pairs_position(Z_t: float, theta: float, kappa: float,
                            sigma_Z: float, gamma: float,
                            T_remaining: float) -> float:
    """
    Posizione ottimale nello spread — Cartea-Jaimungal Cap. 11.
    
    Returns: q_t* (+ = long spread, - = short spread)
    """
    # Normalizzazione del segnale
    signal_strength = kappa * (theta - Z_t)
    
    # Fattore di scadenza
    time_factor = 1.0 / (T_remaining + 1.0 / kappa)
    
    # Denominatore: avversione al rischio * varianza
    risk_adj = gamma * sigma_Z**2
    
    q_optimal = signal_strength / risk_adj * time_factor
    return q_optimal

def pairs_pnl_simulation(Z_series: pd.Series, ou_params: dict,
                          gamma: float = 1.0, T: float = 20,
                          transaction_cost: float = 0.001) -> pd.Series:
    """
    Simula il P&L della strategia ottimale su uno spread storico.
    """
    kappa    = ou_params['kappa']
    theta    = ou_params['theta']
    sigma_Z  = ou_params['sigma_Z']
    
    pnl = []
    q_prev = 0.0
    
    for i, (t_idx, Z_t) in enumerate(Z_series.items()):
        T_rem = max(T - i / 252, 0.01)
        
        q_new = optimal_pairs_position(Z_t, theta, kappa, sigma_Z, gamma, T_rem)
        
        # Costo transazione per variazione di posizione
        trade_cost = transaction_cost * abs(q_new - q_prev)
        
        # P&L: variazione posizione * variazione spread
        if i > 0:
            dZ = Z_series.iloc[i] - Z_series.iloc[i-1]
            step_pnl = q_prev * dZ - trade_cost
            pnl.append(step_pnl)
        
        q_prev = q_new
    
    return pd.Series(pnl, index=Z_series.index[1:])
```

### Rischi del Pairs Trading

| Rischio | Descrizione | Mitigazione |
|---------|-------------|-------------|
| **Cointegration breakdown** | La relazione cambia per causa fondamentale | Rolling test ADF; stop se $|Z_t| > 4\sigma_Z$ |
| **Illiquidità** | Spread bid-ask erode alpha | Usa solo coppie con spread < 5 bps |
| **Correlation regime** | Correlazione crolla in crisi | Ridimensiona in alta volatilità |
| **Execution risk** | Leg 1 eseguita, leg 2 no | Usa ordini condizionali |

---

## Order Imbalance e Segnale di Breve Termine (Cap. 12)

### Definizioni

**Order Imbalance (OI) da flusso**:

$$OI_t = \frac{N_t^{buy} - N_t^{sell}}{N_t^{buy} + N_t^{sell}} \in [-1,\; +1]$$

**OI da profondità del book**:

$$OI_t^{depth} = \frac{V_t^b - V_t^a}{V_t^b + V_t^a}$$

### Potere Predittivo

Il segnale OI prevede la variazione di midprice a breve:

$$\mathbb{E}[\Delta M_{t+\tau} \mid OI_t] \approx \alpha \cdot OI_t \qquad \tau \in [1\,s,\; 5\,\text{min}]$$

**Decadimento**: il potere predittivo decade come $\tau^{-0.5}$, è trascurabile oltre 5 minuti.

```python
def compute_order_imbalance(trade_data: pd.DataFrame,
                             window: str = '1min') -> pd.Series:
    """
    Calcola OI rolling da dati di trade.
    
    trade_data: DataFrame con ['timestamp', 'side', 'qty']
                side = 'B' (buy) o 'S' (sell)
    """
    df = trade_data.copy()
    df['signed_qty'] = df['qty'] * df['side'].map({'B': 1, 'S': -1})
    df = df.set_index('timestamp')
    
    buy_vol  = df['qty'][df['side'] == 'B'].resample(window).sum()
    sell_vol = df['qty'][df['side'] == 'S'].resample(window).sum()
    
    OI = (buy_vol - sell_vol) / (buy_vol + sell_vol + 1e-8)
    return OI.fillna(0)

def oi_predictive_power(midprice: pd.Series, OI: pd.Series,
                         horizons_sec: list = [5, 30, 60, 300]) -> pd.DataFrame:
    """
    Misura il potere predittivo di OI per vari orizzonti.
    """
    results = []
    
    for tau in horizons_sec:
        # Variazione futura del midprice
        freq = pd.infer_freq(midprice.index) or '1s'
        shifts = int(tau / pd.Timedelta(freq).total_seconds())
        
        future_ret = midprice.shift(-shifts) / midprice - 1
        
        # Allinea OI e returns
        combined = pd.DataFrame({'OI': OI, 'ret': future_ret}).dropna()
        
        # Correlazione di Spearman (IC)
        ic = combined['OI'].corr(combined['ret'], method='spearman')
        
        results.append({
            'horizon_sec': tau,
            'IC': ic,
            'IC_annualized': ic * np.sqrt(252 * 6.5 * 3600 / tau)
        })
    
    return pd.DataFrame(results)
```

### Uso dell'OI nell'Esecuzione

**Per un programma di vendita**:
- $OI_t > 0.5$ (pressione di acquisto) → rinvia la vendita (il prezzo potrebbe salire)
- $OI_t < -0.5$ (pressione di vendita) → anticipa la vendita (evita di vendere dopo altri)

**Per market making**:
- $OI_t > 0$ → lean verso ask (c'è chi vuole comprare, sell is easy)
- $OI_t < 0$ → lean verso bid (c'è chi vuole vendere, buy is easy)

### Modello Catena di Markov (Cap. 12.2)

Il segnale OI può essere modellato come catena di Markov con stati $\{-1, 0, +1\}$:

$$\mathbf{P} = \begin{pmatrix} p_{-,-} & p_{-,0} & p_{-,+} \\ p_{0,-} & p_{0,0} & p_{0,+} \\ p_{+,-} & p_{+,0} & p_{+,+} \end{pmatrix}$$

L'autocorrelazione positiva del flusso implica $p_{+,+} > p_{-,+}$ e $p_{-,-} > p_{+,-}$.

```python
def fit_oi_markov_chain(OI_series: pd.Series,
                         threshold: float = 0.3) -> np.ndarray:
    """
    Stima la matrice di transizione della catena di Markov per OI.
    
    Stati: -1 (sell pressure), 0 (neutro), +1 (buy pressure)
    """
    # Discretizza OI in 3 stati
    states = pd.cut(OI_series, bins=[-1, -threshold, threshold, 1],
                    labels=[-1, 0, 1]).astype(float)
    
    # Conta transizioni
    P = np.zeros((3, 3))
    state_map = {-1: 0, 0: 1, 1: 2}
    
    for i in range(len(states) - 1):
        if pd.notna(states.iloc[i]) and pd.notna(states.iloc[i+1]):
            from_s = state_map[states.iloc[i]]
            to_s   = state_map[states.iloc[i+1]]
            P[from_s, to_s] += 1
    
    # Normalizza per riga
    row_sums = P.sum(axis=1, keepdims=True)
    P = P / np.where(row_sums > 0, row_sums, 1)
    
    return P
```
