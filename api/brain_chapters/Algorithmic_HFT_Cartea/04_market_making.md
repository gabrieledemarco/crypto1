# Capitolo 4: Market Making — Avellaneda-Stoikov e Adverse Selection

> **Fonte**: Algorithmic and High-Frequency Trading — Cartea, Jaimungal & Penalva, Cambridge 2015, Cap. 10

## Modello Base di Market Making (Avellaneda-Stoikov)

Il market maker posta simultaneamente un **ask LO** a $P^a_t = M_t + \delta^a$ e un **bid LO** a $P^b_t = M_t - \delta^b$.

**Dinamica del midprice**:

$$dS_t = \sigma\,dW_t$$

**Intensità di fill** (decrescente nella distanza dal midprice):

$$\lambda^a(\delta^a) = \Lambda\,e^{-\kappa\,\delta^a} \qquad \lambda^b(\delta^b) = \Lambda\,e^{-\kappa\,\delta^b}$$

**Parametri stimati dai dati**:
- $\Lambda$: tasso di arrivo degli MO (count per secondo)
- $\kappa$: sensitività del fill rate alla distanza [$\text{tick}^{-1}$]

```python
import numpy as np
from scipy.stats import linregress

def calibrate_fill_model(historical_lo_data: pd.DataFrame) -> dict:
    """
    Calibra Lambda e kappa dal modello lambda = Lambda * exp(-kappa * delta).
    
    historical_lo_data: DataFrame con colonne ['delta', 'filled', 'time_in_book']
    """
    # Fill rate empirico per distanza
    groups = historical_lo_data.groupby('delta')
    fill_rates = groups['filled'].mean()
    deltas = fill_rates.index.values
    
    # Stima log-lineare: log(lambda) = log(Lambda) - kappa * delta
    log_rates = np.log(fill_rates.values + 1e-8)
    slope, intercept, r, _, _ = linregress(deltas, log_rates)
    
    return {
        'Lambda': np.exp(intercept),
        'kappa':  -slope,          # kappa > 0
        'r_squared': r**2
    }
```

---

## Quote Ottimali (Risk-Neutral)

Senza avversione al rischio e senza penalità inventario, le distanze ottimali sono **simmetriche**:

$$\delta^{a*} = \delta^{b*} = \frac{1}{\kappa} + \frac{\gamma\,\sigma^2}{2}\,(T-t)$$

**Interpretazione**:
- $1/\kappa$: distanza minima dettata dal book depth
- $\gamma\sigma^2(T-t)/2$: allargamento per rischio inventario (cresce col tempo)

---

## Skew delle Quote per Gestire l'Inventario

Con inventario $X_t \neq 0$, il market maker inclina le quote verso il lato che riduce l'inventario.

**Reservation price** (centro ottimale delle quote):

$$r_t = M_t - \gamma\,\sigma^2\,X_t\,(T-t)$$

Se **long** ($X_t > 0$): $r_t < M_t$ → ask più vicino al mid (vende più facilmente), bid più lontano.

**Quote ottimali asimmetriche**:

$$\delta^{a*} = r_t - M_t + \frac{1}{\kappa} + \frac{\gamma\,\sigma^2}{2}(T-t)$$

$$\delta^{b*} = M_t - r_t + \frac{1}{\kappa} + \frac{\gamma\,\sigma^2}{2}(T-t)$$

```python
def optimal_quotes(S_mid: float, X_t: float, t: float, T: float,
                   sigma: float, gamma: float, kappa: float,
                   Lambda: float) -> dict:
    """
    Calcola le quote ottimali ask e bid — Avellaneda-Stoikov con skew inventario.
    
    Args:
        S_mid: midprice corrente
        X_t:   inventario corrente (+ = long, - = short)
        gamma: avversione al rischio di inventario
        kappa: sensitività fill rate
    """
    T_rem = T - t
    
    # Reservation price
    r_t = S_mid - gamma * sigma**2 * X_t * T_rem
    
    # Spread base
    base_spread = 1/kappa + (gamma * sigma**2 / 2) * T_rem
    
    # Quote
    ask = r_t + base_spread
    bid = r_t - base_spread
    
    # Distanze dal midprice
    delta_a = ask - S_mid
    delta_b = S_mid - bid
    
    # Fill rate attesi
    fill_a = Lambda * np.exp(-kappa * delta_a)
    fill_b = Lambda * np.exp(-kappa * delta_b)
    
    return {
        'ask': ask, 'bid': bid,
        'delta_a': delta_a, 'delta_b': delta_b,
        'reservation_price': r_t,
        'fill_rate_ask': fill_a, 'fill_rate_bid': fill_b,
        'expected_pnl_per_dt': fill_a * delta_a + fill_b * delta_b
    }
```

---

## Adverse Selection (Cap. 10.4)

Quando arriva un MO, è più probabile che sia informato se:
- Dimensione grande rispetto alla profondità del book
- Arriva subito dopo una notizia
- Segue altri MO nella stessa direzione (clustering)

**Costo di adverse selection per trade** (stima empirica):

$$AS = \mathbb{E}[\Delta M_{t+\tau} \mid \text{MO fill a }t] \approx c\,\sigma$$

Dopo un fill, il midprice si sposta **contro** il market maker di circa $AS$.

**P&L netto per fill**:

$$\text{P\&L per fill} = \underbrace{\delta}_{\text{spread catturato}} - \underbrace{AS}_{\text{adverse selection}} - \underbrace{I_{risk}}_{\text{rischio inventario}}$$

### Short-Term Alpha (STA)

Il flusso di ordini contiene informazione di breve termine. Il market maker può stimare:

$$\alpha_t = \mathbb{E}[dS_t \mid \mathcal{F}_t^{order flow}] \approx \beta \cdot OI_t$$

e aggiustare le quote di conseguenza (vedi Cap. 10.4.2).

```python
def estimate_adverse_selection(trade_data: pd.DataFrame,
                                midprice: pd.Series,
                                tau_seconds: int = 30) -> float:
    """
    Stima il costo di adverse selection medio.
    
    Per ogni fill, misura variazione midprice a tau secondi dopo.
    AS = E[sign(side) * (M_{t+tau} - M_t)]
    """
    AS_samples = []
    
    for _, trade in trade_data.iterrows():
        t_fill = trade['timestamp']
        t_future = t_fill + pd.Timedelta(seconds=tau_seconds)
        
        M_fill   = midprice.asof(t_fill)
        M_future = midprice.asof(t_future)
        
        if pd.notna(M_future):
            # side = +1 se MM ha venduto, -1 se ha comprato
            AS = trade['mm_side'] * (M_future - M_fill)
            AS_samples.append(AS)
    
    return np.mean(AS_samples)
```

---

## Gestione del Rischio di Inventario

### Limiti Hard

```python
class InventoryManager:
    def __init__(self, max_inventory: float, soft_threshold: float,
                 gamma: float, kappa: float):
        self.I_max  = max_inventory
        self.I_soft = soft_threshold
        self.gamma  = gamma
        self.kappa  = kappa
    
    def should_quote(self, X_t: float, side: str) -> bool:
        """Decide se postare quote su un lato."""
        if abs(X_t) >= self.I_max:
            # Limite hard: quota solo il lato che riduce inventario
            return (side == 'bid' and X_t < 0) or \
                   (side == 'ask' and X_t > 0)
        return True
    
    def inventory_penalty(self, X_t: float, T_rem: float) -> float:
        """Penalità di inventario per il reservation price."""
        return self.gamma * (0.30**2) * X_t * T_rem
```

### Regole Pratiche

| Scenario | Azione |
|----------|--------|
| $|X_t| < I_{soft}$ | Quote simmetriche (Avellaneda-Stoikov) |
| $I_{soft} \leq |X_t| < I_{max}$ | Allarga quote sul lato che aumenta inventario |
| $|X_t| \geq I_{max}$ | Ritira quote sul lato che aumenta inventario |
| P&L inventario $< -L$ | Stop-loss: liquida con MO |

---

## Calibrazione Pratica del Modello

```python
import pandas as pd
import numpy as np

def calibrate_mm_model(lob_data: pd.DataFrame,
                        trade_data: pd.DataFrame,
                        sigma: float) -> dict:
    """
    Calibra i parametri del modello di market making dai dati storici.
    
    Returns: dict con gamma, kappa, Lambda, AS_cost
    """
    # 1. Stima kappa e Lambda dal fill rate vs distanza
    fill_params = calibrate_fill_model(trade_data)
    
    # 2. Stima adverse selection
    midprice = (lob_data['bid'] + lob_data['ask']) / 2
    AS_cost  = estimate_adverse_selection(trade_data, midprice)
    
    # 3. Gamma da P&L ottimale: gamma s.t. E[P&L] > 0
    # Condizione minima: delta > AS_cost → 1/kappa > AS_cost
    gamma_min = 0.0
    gamma = max(gamma_min, 2 * fill_params['kappa'] * AS_cost)
    
    return {
        'Lambda':  fill_params['Lambda'],
        'kappa':   fill_params['kappa'],
        'gamma':   gamma,
        'AS_cost': AS_cost,
        'min_spread_bps': 2 / fill_params['kappa'] / 0.01 * 10_000
    }
```
