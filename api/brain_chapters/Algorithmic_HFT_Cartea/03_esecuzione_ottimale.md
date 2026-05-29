# Capitolo 3: Esecuzione Ottimale — Trading Continuo

> **Fonte**: Algorithmic and High-Frequency Trading — Cartea, Jaimungal & Penalva, Cambridge 2015, Cap. 6–8

## Modello I: Esecuzione Continua con Solo Impatto Temporaneo

**Dinamica del midprice** (con drift):

$$dS_t = \mu\,dt + \sigma\,dW_t$$

**Inventario** (si azzera a $T$):

$$dX_t = -v_t\,dt \qquad X_0 = x_0, \quad X_T = 0$$

**Cassa** (cresce con i proventi di vendita, ridotta dall'impatto):

$$dW_t = v_t\,(S_t - \eta\,v_t)\,dt \qquad \eta = \text{coefficiente impatto temporaneo}$$

**Tasso ottimale** (Cartea-Jaimungal, Cap. 6, soluzione in forma chiusa):

$$\boxed{v_t^* = \frac{X_t}{T - t} + \frac{\mu}{2\eta}\,(T-t)}$$

- **Primo termine**: liquidazione VWAP-like dell'inventario residuo
- **Secondo termine**: overlay momentum (se $\mu > 0$, vendi più velocemente)

**Interpretazione**: con drift positivo del prezzo, il trader vende più lentamente inizialmente (aspetta prezzi più alti), poi accelera.

```python
import numpy as np

def cartea_jaimungal_rate(x_t, t, T, mu, eta):
    """
    Tasso ottimale di esecuzione — Modello I Cartea-Jaimungal (Cap. 6).
    
    Args:
        x_t: inventario residuo al tempo t
        T:   orizzonte finale
        mu:  drift del midprice (annualizzato)
        eta: impatto temporaneo
    """
    time_remaining = T - t
    if time_remaining <= 0:
        return x_t  # esegui tutto il residuo
    
    vwap_component     = x_t / time_remaining
    momentum_component = (mu / (2 * eta)) * time_remaining
    
    return vwap_component + momentum_component

def simulate_execution(x0, T, mu, sigma, eta, n_steps=100, n_paths=1000,
                       seed=42):
    """Simula l'esecuzione ottimale e calcola l'IS medio."""
    rng = np.random.default_rng(seed)
    dt  = T / n_steps
    IS_samples = []
    
    for _ in range(n_paths):
        x, S, W = x0, 100.0, 0.0
        
        for step in range(n_steps):
            t = step * dt
            v = cartea_jaimungal_rate(x, t, T, mu, eta)
            v = np.clip(v, 0, x / dt if dt > 0 else x)  # no short
            
            # Aggiorna cassa e inventario
            W += v * (S - eta * v) * dt
            x -= v * dt
            
            # Prezzo stocastico
            S += mu * dt + sigma * np.sqrt(dt) * rng.standard_normal()
        
        # IS = initial value - actual proceeds
        IS_samples.append(x0 * 100.0 - W)
    
    return np.mean(IS_samples), np.std(IS_samples)
```

---

## Modello II: Adverse Selection e Segnale di Flusso

Quando il book mostra pressione di acquisto, il prezzo tende a salire. Un trader informato può incorporare questa informazione nel tasso di esecuzione.

**Segnale di flusso (order flow signal)**:

$$\alpha_t = \rho\,(N_t^{buy} - N_t^{sell}) \qquad \rho > 0$$

dove $N^{buy}$, $N^{sell}$ sono conteggi di MO buy/sell in una finestra recente.

**Tasso ottimale con adverse selection**:

$$v_t^* = v_{VWAP} + c_1\,\alpha_t + c_2\,\frac{X_t}{T-t}$$

- $c_1 > 0$: accelera se $\alpha_t > 0$ (flusso di acquisto → prezzo salirà)
- $c_2$: aggiustamento per il residuo

```python
def estimate_order_flow_signal(trade_data: pd.DataFrame,
                               window_seconds: int = 60,
                               rho: float = 0.01) -> pd.Series:
    """
    Calcola il segnale di flusso d'ordini $alpha_t$.
    
    trade_data: DataFrame con colonne ['timestamp', 'side', 'qty']
                side = +1 buy, -1 sell
    """
    trade_data = trade_data.set_index('timestamp').sort_index()
    
    # Flusso netto buy - sell nel rolling window
    net_flow = (trade_data['side'] * trade_data['qty'])\
               .rolling(f'{window_seconds}s').sum()
    
    return rho * net_flow  # alpha_t
```

---

## Modello con LO: Esecuzione tramite Ordini Limite

Un trader può eseguire il programma **solo con LO** (no MO), accettando il rischio di non essere riempito ma evitando di pagare lo spread.

**Intensità di fill** al prezzo $S_t - \delta$ (distanza $\delta$ dal midprice sul bid):

$$\lambda^b(\delta) = \Lambda\,e^{-\kappa\,\delta}$$

**Equazione HJB** (Cap. 8):

$$\partial_t H + \frac{\sigma^2}{2}\,\partial_{SS}H + \sup_{\delta \geq 0} \Lambda e^{-\kappa\delta}\left[H(t,x+1,W-(S-\delta),S) - H\right] = 0$$

**Soluzione**: la distanza ottimale dipende dall'inventario residuo e dal tempo:

$$\delta^*(x, t) = \frac{1}{\kappa} + h(x, T-t)$$

dove $h$ è la soluzione di una Riccati e cresce con l'urgenza di liquidare.

### Strategia Mista LO + MO (Cap. 8)

Ottimale usare **entrambi** i tipi:
- LO per esecuzione ordinaria (risparmia lo spread)
- MO per rebalancing urgente quando l'inventario devia eccessivamente

**Banda ottimale di inventario**: mantieni $X_t \in [\bar{x} - \Delta, \bar{x} + \Delta]$.  
- Fuori dalla banda → invia MO per rientrare
- Dentro la banda → usa LO graduali

```python
def mixed_lo_mo_strategy(x_t, x_target, delta_band, S_t, kappa, Lambda,
                          T_remaining, eta, phi):
    """
    Strategia mista LO + MO per esecuzione ottimale.
    
    Restituisce: (action_type, quantity, lo_distance)
    """
    deviation = x_t - x_target
    
    if abs(deviation) > delta_band:
        # Fuori banda: MO per rientrare
        qty_mo = deviation - np.sign(deviation) * delta_band
        return 'MO', qty_mo, None
    else:
        # Dentro banda: LO ottimale
        # Distanza ottimale dal midprice
        urgency = phi * (x_t ** 2) / max(T_remaining, 0.001)
        lo_dist = 1 / kappa + urgency / (2 * Lambda)
        return 'LO', None, lo_dist
```

---

## Esecuzione con Price Limiter (Cap. 7)

Variante: l'esecuzione prosegue solo se il prezzo non scende sotto una soglia $\bar{S}$.

$$\tau^* = \min\left(T,\; \inf\{t : S_t \leq \bar{S}\}\right)$$

**Soluzione**: funzione valore con barriera assorbente. L'agente si comporta come se avesse un put sul prezzo di esecuzione.

**Strategia**: negozia più aggressivamente quando il prezzo è vicino al limite, conservativamente quando è lontano.

---

## Dark Pool + Mercato Lit (Cap. 7)

**Setup duale**: l'agente può simultaneamente:
- Inviare ordini al mercato **lit** (impatto visibile, fill certo)
- Inviare blocchi al **dark pool** (no impatto, fill al midprice con probabilità $p_t$)

**Probabilità di fill dark pool**:

$$p_t \approx \lambda_{dark}\,\min\left(q^{dark},\; V_{dark}\right)\,dt$$

dove $V_{dark}$ è il volume disponibile nel dark pool.

**Risultato**: è sempre ottimale mandare simultaneamente al dark pool mentre si esegue sul lit. Il fill del dark riduce l'impatto atteso proporzionalmente alla liquidità disponibile.

```python
def dual_venue_execution(x0, T, eta_lit, lambda_dark, p_dark, n_steps=100):
    """
    Simula esecuzione ottimale su mercato lit + dark pool.
    """
    dt = T / n_steps
    x = x0
    total_IS = 0.0
    
    for step in range(n_steps):
        t_rem = T - step * dt
        
        # Tasso sul lit (Cartea-Jaimungal base)
        v_lit = x / t_rem
        
        # Quantità al dark pool (funzione dell'inventario)
        q_dark = min(x * 0.3, x)  # invia 30% al dark (da ottimizzare)
        
        # Fill dark con probabilità p_dark
        dark_fill = q_dark if np.random.random() < p_dark * dt else 0.0
        
        # Aggiorna inventario
        lit_exec = v_lit * dt
        x -= lit_exec + dark_fill
        x  = max(x, 0)
        
        # Costo lit (paga impatto), dark (solo midprice)
        total_IS += eta_lit * v_lit**2 * dt  # impatto lit
        # dark: zero impatto (eseguito a midprice)
    
    return total_IS
```

---

## Metriche di Valutazione dell'Esecuzione

| Metrica | Formula | Target |
|---------|---------|--------|
| **IS assoluto** | $\text{IS} = x_0 S_0 - W_T$ | Minimizza |
| **IS normalizzato** | $\text{IS}/x_0 S_0$ [bps] | < 10 bps per ordini medi |
| **Slippage vs VWAP** | $P_{exec} - P_{VWAP}$ | ≈ 0 per VWAP target |
| **Market impact** | $S_{post} - S_{pre}$ | Monitora vs modello |
| **Fill rate LO** | Fill / Submitted | > 70% in mercati normali |
