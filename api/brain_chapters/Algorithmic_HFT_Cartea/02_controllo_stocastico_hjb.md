# Capitolo 2: Controllo Stocastico Ottimale ed Equazioni HJB

> **Fonte**: Algorithmic and High-Frequency Trading — Cartea, Jaimungal & Penalva, Cambridge 2015, Cap. 5

## Framework Generale

Il controllo stocastico è lo strumento matematico fondamentale per derivare strategie ottimali di esecuzione e market making.

**Spazio degli stati**: $(x_t, S_t, t)$ dove $x_t$ = inventario, $S_t$ = midprice  
**Controllo**: $u_t$ = tasso di negoziazione / quote postate  
**Criterio di performance**: massimizzare

$$\mathbb{E}\left[\underbrace{W_T}_{\text{cash finale}} - \underbrace{\phi\,x_T^2}_{\text{penalità inventario}}\right]$$

dove $\phi > 0$ è la penalità per inventario residuo a scadenza.

---

## Equazione di Hamilton-Jacobi-Bellman (HJB)

Per la funzione valore $V(t, x, S)$:

$$\frac{\partial V}{\partial t} + \sup_{u_t} \left[\mathcal{L}^{u_t} V\right] = 0$$

con condizione terminale:

$$V(T, x, S) = x\,S - \phi\,x^2$$

dove $\mathcal{L}^u$ è il generatore infinitesimale del processo di stato sotto il controllo $u$.

### Procedura di Soluzione

1. **Ansatz**: $V(t,x,S) = x\,S + f(t,x)$ (lineare in $S$ grazie alla struttura del problema)
2. **Riduzione**: sostituendo l'ansatz, la PDE si riduce a un'ODE/PDE in $f(t,x)$
3. **Soluzione**: analitica per modelli lineari, numerica (griglia finita o Monte Carlo) per non-lineari

```python
import numpy as np
from scipy.integrate import odeint

def solve_riccati_execution(T, sigma, eta, lam, phi, n_steps=1000):
    """
    Risolve l'equazione di Riccati per esecuzione ottimale continua.
    
    Restituisce funzioni a(t) e b(t) dove f(t,x) = a(t)*x^2 + b(t)*x
    
    Cartea-Jaimungal, Cap. 6, eq. (6.16)
    """
    dt = T / n_steps
    t_grid = np.linspace(0, T, n_steps + 1)
    
    # Condizioni terminali: a(T) = -phi, b(T) = 0
    a = np.zeros(n_steps + 1)
    b = np.zeros(n_steps + 1)
    a[-1] = -phi
    b[-1] = 0.0
    
    # Integra all'indietro nel tempo (backward induction)
    for i in range(n_steps - 1, -1, -1):
        # ODE di Riccati per a(t)
        da = -sigma**2 / (2 * eta) * a[i+1]**2 + lam * sigma**2
        # ODE per b(t)
        db = -sigma**2 / (2 * eta) * a[i+1] * b[i+1]
        
        a[i] = a[i+1] - da * dt
        b[i] = b[i+1] - db * dt
    
    return t_grid, a, b

def optimal_rate(x_t, t, t_grid, a, b, eta):
    """Tasso ottimale di esecuzione al tempo t con inventario x_t."""
    idx = np.searchsorted(t_grid, t)
    a_t = a[min(idx, len(a)-1)]
    b_t = b[min(idx, len(b)-1)]
    
    # Tasso ottimale: v_t* = -sigma^2/(2*eta) * (2*a_t*x_t + b_t)
    v_t = -sigma_sq / (2 * eta) * (2 * a_t * x_t + b_t)
    return max(v_t, 0)  # solo vendita
```

---

## Controllo per Processi di Diffusione

**Dinamica generica del midprice**:

$$dS_t = \mu\,dt + \sigma\,dW_t$$

**Funzione valore per problema di controllo a orizzonte finito**:

$$V(t,x,S) = \sup_{\{u_s\}_{s \in [t,T]}} \mathbb{E}_t\left[\int_t^T r(s, x_s, S_s, u_s)\,ds + g(x_T, S_T)\right]$$

**HJB per processi di diffusione**:

$$\partial_t V + \mu\,\partial_S V + \frac{\sigma^2}{2}\,\partial_{SS} V + \sup_u \left[h(t,x,S,u) + f(t,x,S,u)\,\partial_x V\right] = 0$$

---

## Controllo per Processi di Conteggio (Arrivi di Ordini)

Rilevante per market making: gli ordini arrivano come processi di Poisson.

**Intensità di fill** del LO a distanza $\delta$ dal midprice:

$$\lambda(\delta) = \Lambda\,e^{-\kappa\,\delta} \qquad [\text{fill per unità di tempo}]$$

**HJB per processi di salto**:

$$\partial_t V + \mathcal{L}_{diff} V + \sup_{\delta^a, \delta^b} \left[\lambda(\delta^a)\left(V(t, x-1, S; \delta^a) - V\right) + \lambda(\delta^b)\left(V(t, x+1, S; \delta^b) - V\right)\right] = 0$$

dove il primo termine è il fill di un ask LO (vende 1 unità) e il secondo di un bid LO (acquista 1 unità).

---

## Arresto Ottimale (Optimal Stopping)

Applicazione: decidere **quando** liquidare una posizione o smettere di fare market making.

**Equazione di complementarità**:

$$\max\left\{-\partial_t V - \mathcal{L}V,\; V - g\right\} = 0$$

dove $g(x,S)$ è il payoff di arresto immediato.

```python
def solve_optimal_stopping(S_grid, V_terminal, mu, sigma, r, dt, T):
    """
    Risolve problema di arresto ottimale con programmazione dinamica.
    
    Backward induction su griglia di prezzo.
    """
    V = V_terminal.copy()
    n_steps = int(T / dt)
    
    for _ in range(n_steps):
        # Evoluzione diffusiva (Crank-Nicolson o esplicita)
        V_evolved = _diffusion_step(V, S_grid, mu, sigma, r, dt)
        
        # Condizione di complementarità: max{continua, arresta}
        exercise_value = np.maximum(S_grid - 1.0, 0)  # esempio: call payoff
        V = np.maximum(V_evolved, exercise_value)
    
    return V

def _diffusion_step(V, S_grid, mu, sigma, r, dt):
    """Schema esplicito per diffusione."""
    dS = S_grid[1] - S_grid[0]
    V_new = V.copy()
    for i in range(1, len(S_grid)-1):
        drift = mu * (V[i+1] - V[i-1]) / (2*dS)
        diff  = 0.5 * sigma**2 * (V[i+1] - 2*V[i] + V[i-1]) / dS**2
        V_new[i] = V[i] + dt * (drift + diff - r*V[i])
    return V_new
```

---

## Principio di Programmazione Dinamica

**Bellman principle**: la funzione valore soddisfa

$$V(t, x, S) = \sup_u \mathbb{E}_t\left[V(t+dt, x_{t+dt}, S_{t+dt})\right] + r(t,x,S,u)\,dt$$

**Algoritmo generico** (backward induction in tempo discreto):

```python
def dynamic_programming_trading(N, n_states, n_actions,
                                 transition_fn, reward_fn, terminal_fn):
    """
    Programmazione dinamica per strategia di trading ottimale.
    
    N: numero di passi temporali
    n_states: dimensione dello spazio degli stati
    n_actions: numero di azioni discrete
    """
    # Condizioni terminali
    V = terminal_fn(n_states)
    policy = np.zeros((N, n_states), dtype=int)
    
    # Backward induction
    for t in range(N-1, -1, -1):
        V_new = np.full(n_states, -np.inf)
        for s in range(n_states):
            best_val, best_act = -np.inf, 0
            for a in range(n_actions):
                # Valore atteso dello stato successivo
                expected_V = sum(
                    transition_fn(s, a, s_next) * V[s_next]
                    for s_next in range(n_states)
                )
                val = reward_fn(t, s, a) + expected_V
                if val > best_val:
                    best_val, best_act = val, a
            V_new[s] = best_val
            policy[t, s] = best_act
        V = V_new
    
    return V, policy
```

---

## Tabella Riassuntiva per Tipo di Problema

| Problema | Stato | Controllo | Tipo processo | Capitolo |
|----------|-------|-----------|--------------|---------|
| Esecuzione continua | $(x_t, S_t)$ | Tasso $v_t$ | Diffusione | 6–7 |
| Esecuzione con LO | $(x_t, S_t)$ | $\delta^a, \delta^b$ | Diffusione + salti | 8 |
| Market making | $(X_t, S_t)$ | $\delta^a, \delta^b$ | Salti (Poisson) | 10 |
| Pairs trading | $(q_t, Z_t)$ | Posizione $q_t$ | Diffusione (OU) | 11 |
| Volume targeting | $(x_t, V_t)$ | Tasso $v_t$ | Diffusione + Poisson | 9 |
