# Capitolo 1: Esecuzione Ottimale di Transazioni di Portafoglio

> **Fonte**: "Optimal Trading Strategies" — Julian Lorenz, ETH Zürich (2008); basato su Almgren & Chriss, "Optimal Execution of Portfolio Transactions", *Journal of Risk* 3(2), 2001

## Il Problema dell'Esecuzione

Un gestore detiene $X$ azioni e deve liquidarle entro $T$ periodi. Ogni transazione muove il mercato contro di noi (**market impact**). Obiettivo: trovare la traiettoria di esecuzione $\{x_t\}$ che minimizza il costo totale in termini media-varianza.

**Implementation Shortfall (IS)** = valore paper portfolio − proventi effettivi

$$IS = \sum_{t=1}^{T} v_t \cdot h(v_t)\,\Delta t + \sum_{t=1}^{T} g(v_t)\cdot x_t\,\Delta t$$

dove $v_t = -\dot{x}_t$ è il tasso di negoziazione, $h(v)$ è l'**impatto temporaneo**, $g(v)$ è l'**impatto permanente**.

---

## Modello di Mercato Almgren-Chriss

**Random walk aritmetico** per il prezzo mid:

$$S_t = S_{t-1} + \sigma\,\xi_t \qquad \xi_t \overset{iid}{\sim} \mathcal{N}(0,1)$$

**Prezzo effettivo per azione** (realizzato dopo impatto):

$$\tilde{S}_t = S_t - h(v_t)$$

**Impatto temporaneo** (lineare nel caso base):

$$h(v) = \eta \cdot v \qquad [\text{€/azione per azione/giorno}]$$

**Impatto permanente** (lineare):

$$g(v) = \gamma \cdot v \qquad [\text{variazione prezzo per unità di volume}]$$

| Parametro | Significato | Range tipico (azioni) |
|-----------|------------|----------------------|
| $\sigma$ | Volatilità giornaliera del prezzo | 1–3% |
| $\eta$ | Coefficiente impatto temporaneo | 0.1–1 bps per % ADV |
| $\gamma$ | Coefficiente impatto permanente | $\sim\eta/2$ |

---

## Obiettivo Media-Varianza

Minimizzare il trade-off tra costo atteso e varianza del costo:

$$\min_{\{v_t\}} \quad \mathbb{E}[IS] + \lambda \cdot \text{Var}[IS]$$

dove $\lambda \geq 0$ è il parametro di **avversione al rischio di esecuzione**.

**Costo atteso** (componente quadratica nell'impact):

$$\mathbb{E}[IS] = \eta \int_0^T v_t^2\,dt + \frac{\gamma}{2} X^2$$

**Varianza del costo** (dipende dalla posizione residua):

$$\text{Var}[IS] = \sigma^2 \int_0^T x_t^2\,dt$$

---

## Traiettoria Ottimale Statica (Almgren-Chriss)

Minimizzando il funzionale lagrangiano, la soluzione in forma chiusa è:

$$\boxed{x_t = X \cdot \frac{\sinh\bigl(\kappa(T-t)\bigr)}{\sinh(\kappa T)}}$$

**Parametro di urgenza** $\kappa$:

$$\kappa = \sqrt{\frac{\lambda\,\sigma^2}{\eta}}$$

**Tasso di negoziazione ottimale**:

$$v_t = -\dot{x}_t = X\kappa \cdot \frac{\cosh\bigl(\kappa(T-t)\bigr)}{\sinh(\kappa T)}$$

### Interpretazione di $\kappa$

| Valore di $\kappa$ | Comportamento | Regime |
|-------------------|--------------|--------|
| $\kappa \to 0$ | Schedule uniforme (TWAP) | Basso rischio, alto impatto |
| $\kappa \sim 1\,\text{giorno}^{-1}$ | Leggero front-loading | Bilanciato |
| $\kappa \gg 1$ | Tutto eseguito subito | Alto rischio, basso impatto |

**Range pratico per azioni**: $\kappa \in [0.1,\; 2.0]$ giorno$^{-1}$.

---

## Frontiera Efficiente dell'Esecuzione

Variando $\lambda$ si ottiene una curva nel piano $(\mathbb{E}[IS],\; \text{Var}[IS])$, analoga alla frontiera di Markowitz.

```python
import numpy as np
import matplotlib.pyplot as plt

def almgren_chriss_frontier(X, T, sigma, eta, gamma, n_lambda=100):
    """
    Calcola la frontiera efficiente IS per un programma di liquidazione.
    
    Args:
        X: posizione iniziale (azioni)
        T: orizzonte temporale (giorni)
        sigma: volatilità giornaliera
        eta: impatto temporaneo
        gamma: impatto permanente
    """
    lambdas = np.logspace(-4, 2, n_lambda)
    E_IS, Var_IS = [], []
    
    for lam in lambdas:
        kappa = np.sqrt(lam * sigma**2 / eta)
        
        # Costo atteso (formula chiusa)
        if kappa * T < 1e-6:  # limite TWAP
            e_is = eta * X**2 / T + gamma * X**2 / 2
            var_is = sigma**2 * X**2 * T / 3
        else:
            e_is = (eta * X**2 * kappa * np.cosh(kappa*T) / np.sinh(kappa*T) / 2
                    + gamma * X**2 / 2)
            var_is = sigma**2 * X**2 * (T/2 - np.tanh(kappa*T/2)/(2*kappa))
        
        E_IS.append(e_is)
        Var_IS.append(var_is)
    
    return np.array(E_IS), np.array(Var_IS)

# Esempio: liquidare 10.000 azioni in 5 giorni
X, T = 10_000, 5
E_IS, Var_IS = almgren_chriss_frontier(X, T,
    sigma=0.30, eta=0.0005, gamma=0.0003)

plt.plot(np.sqrt(Var_IS), E_IS)
plt.xlabel('Std Dev del Costo (€)'); plt.ylabel('Costo Atteso (€)')
plt.title('Frontiera Efficiente di Esecuzione Almgren-Chriss')
```

---

## Strategie Adattive (Lorenz 2008)

Le traiettorie statiche fissano il programma a $t=0$ indipendentemente da come si muove il prezzo. Le strategie **adattive** condizionano la velocità di esecuzione alla traiettoria del prezzo:

$$v_t = f(S_t,\; x_t,\; t)$$

**Risultato di Lorenz**: le strategie adattive ottengono una frontiera efficiente **strettamente dominante** — per ogni livello di varianza, il costo atteso è inferiore.

### Principio "Aggressive-in-the-Money" (AIM)

> **Se il prezzo si muove a favore, accelera. Se si muove contro, rallenta.**

Per un programma di **vendita**:
- $S_t \uparrow$ → proventi per azione più alti → vendi più velocemente (lock-in gains)
- $S_t \downarrow$ → proventi ridotti → aspetta, evita di vendere in debolezza

**Formalmente**: $\partial v_t / \partial S_t < 0$ per un programma di vendita.

```python
def adaptive_schedule(x, S, S_bar, kappa, eta, sigma, dt):
    """
    Tasso adattivo con logica AIM.
    
    S_bar: prezzo di riferimento al momento t
    Logica: accelera se S > S_bar, rallenta se S < S_bar
    """
    base_rate = x * kappa  # tasso base (Almgren-Chriss)
    alpha = sigma / (2 * eta)  # sensibilità al prezzo
    
    price_adj = alpha * (S - S_bar)
    v_t = base_rate - price_adj  # vendi di più se prezzo alto
    
    return max(v_t, 0)  # no acquisto in programma di liquidazione
```

---

## Market Power del Portafoglio

**Parametro di market power**:

$$\mu = \frac{\gamma X}{\sigma \sqrt{T}}$$

| $\mu$ | Regime | Impatto dominante |
|-------|--------|------------------|
| $\mu \ll 1$ | Ordine piccolo | Impatto trascurabile |
| $\mu \approx 0.5\text{–}2$ | Ordine medio-grande | Adattivo batte statico |
| $\mu \gg 1$ | Ordine molto grande | Impatto permanente domina |

Il **vantaggio adattivo** sul programma statico cresce monotonicamente con $\mu$.

---

## Formule di Sintesi

| Grandezza | Formula chiusa |
|-----------|---------------|
| Urgenza | $\kappa = \sqrt{\lambda\sigma^2/\eta}$ |
| Azioni residue | $x_t = X\,\sinh(\kappa(T-t))/\sinh(\kappa T)$ |
| Tasso ottimale | $v_t = X\kappa\,\cosh(\kappa(T-t))/\sinh(\kappa T)$ |
| IS atteso | $\mathbb{E}[IS] \approx \eta X^2\kappa\,\coth(\kappa T)/2$ |
| Varianza IS | $\text{Var}[IS] \approx \sigma^2 X^2\bigl(T - \tanh(\kappa T)/\kappa\bigr)/2$ |
| Market power | $\mu = \gamma X/(\sigma\sqrt{T})$ |

---

## Connessione con la Generazione di Strategie

1. **Alpha decay**: se il segnale decade con emivita $\tau$, usa $\kappa \approx \ln(2)/\tau$
2. **Cost nel backtest**: sottrai $\eta\,v_t\,|q|$ da ogni trade (impatto temporaneo)
3. **Stop-loss esecuzione**: se $IS > IS_{max}$, passa a TWAP di emergenza
4. **Limite liquidazione**: per strategie leverage, pre-calcola IS di liquidazione a vari $\kappa$

```python
def execution_cost_backtest(trades_df, eta=0.0005, gamma=0.0003):
    """
    Stima il costo di esecuzione IS per un dataframe di trade.
    
    trades_df: DataFrame con colonne ['qty', 'price', 'adv'] (ADV = avg daily volume)
    """
    costs = []
    for _, row in trades_df.iterrows():
        v = row['qty'] / row['adv']          # tasso come % ADV
        temp_impact = eta * v * abs(row['qty'])    # impatto temporaneo (€)
        perm_impact = gamma * v * abs(row['qty'])  # impatto permanente (€)
        costs.append(temp_impact + perm_impact / 2)
    return sum(costs)
```
