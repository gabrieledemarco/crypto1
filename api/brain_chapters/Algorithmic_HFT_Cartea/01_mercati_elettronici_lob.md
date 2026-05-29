# Capitolo 1: Mercati Elettronici e Limit Order Book

> **Fonte**: Algorithmic and High-Frequency Trading — Cartea, Jaimungal & Penalva, Cambridge 2015, Cap. 1–2

## Struttura del Limit Order Book (LOB)

Il **Limit Order Book** è la struttura dati centrale dei mercati elettronici:

| Lato | Contenuto | Ordinamento |
|------|-----------|-------------|
| **Ask** | Ordini di vendita a riposo | Prezzo crescente |
| **Bid** | Ordini di acquisto a riposo | Prezzo decrescente |
| **Best bid** $P^b$ | Miglior prezzo di acquisto | — |
| **Best ask** $P^a$ | Miglior prezzo di vendita | — |

**Grandezze fondamentali**:

$$\text{Midprice}: \quad M_t = \frac{P^a_t + P^b_t}{2}$$

$$\text{Spread quotato}: \quad s_t = P^a_t - P^b_t \quad [\text{solitamente 1–5 bps per asset liquidi}]$$

$$\text{Microprice}: \quad \widetilde{M}_t = \frac{V^a_t}{V^a_t + V^b_t}\,P^a_t + \frac{V^b_t}{V^a_t + V^b_t}\,P^b_t$$

dove $V^a_t, V^b_t$ sono i volumi al best ask/bid. Il microprice è più accurato del midprice perché incorpora lo **squilibrio di profondità**.

```python
import pandas as pd
import numpy as np

def compute_lob_metrics(lob_snapshot: dict) -> dict:
    """
    Calcola metriche LOB da uno snapshot.
    
    lob_snapshot: {'bid_price': float, 'ask_price': float,
                   'bid_vol': float, 'ask_vol': float}
    """
    Pb, Pa = lob_snapshot['bid_price'], lob_snapshot['ask_price']
    Vb, Va = lob_snapshot['bid_vol'], lob_snapshot['ask_vol']
    
    midprice  = (Pa + Pb) / 2
    spread    = Pa - Pb
    microprice = (Va * Pa + Vb * Pb) / (Va + Vb)
    
    # Order imbalance (OI) da profondità
    oi_depth  = (Vb - Va) / (Vb + Va)   # > 0 = pressione acquisto
    
    return {
        'midprice':   midprice,
        'spread':     spread,
        'spread_bps': spread / midprice * 10_000,
        'microprice': microprice,
        'oi_depth':   oi_depth,
    }
```

---

## Tipi di Ordine

| Ordine | Descrizione | Impatto |
|--------|-------------|---------|
| **Market Order (MO)** | Esecuzione immediata al miglior prezzo | Consuma liquidità, paga spread |
| **Limit Order (LO)** | Attende in coda al prezzo specificato | Fornisce liquidità, riceve rebate (maker) |
| **Cancel** | Rimuove un LO in coda | Nessun fill |
| **Iceberg** | Mostra solo parte del volume | Nasconde dimensione |
| **IOC** | Fill immediato o cancellato | No walk del book |
| **FOK** | Fill completo o nulla | Nessun fill parziale |

**"Walking the book"**: un MO di grandi dimensioni che esaurisce il volume al best ask comincia a eseguire ai livelli successivi (prezzi peggiori). Fenomeno osservato nel Flash Crash (6 maggio 2010) con *stub quotes*.

---

## Tassonomia dei Partecipanti di Mercato

**Tre classi fondamentali** (Cartea et al., Cap. 1):

**1. Trader fondamentali / noise / liquidità**  
- Motivazione: esigenza esterna (hedging, ribilanciamento, liquidazione di portafoglio)
- Comportamento: inviano MO di grandi dimensioni, previsibilmente uninformati a breve termine

**2. Trader informati**  
- Motivazione: segnale privato o previsione statistica del prezzo a breve
- Comportamento: eseguono gradualmente (LO + MO) per nascondere la propria informazione

**3. Market maker**  
- Motivazione: cattura dello spread; gestione dell'inventario
- Comportamento: postano LO su entrambi i lati del book, assorbono il flusso

**Relazione critica**: i market maker devono distinguere il flusso tossico (informato) da quello non tossico. Se rilevano **adverse selection**, allargano le quote o ritirano liquidità.

---

## Struttura delle Exchange

### Fee Maker-Taker

| Ruolo | Tipo ordine | Fee tipica |
|-------|------------|-----------|
| **Taker** | MO (rimuove liquidità) | −0.3 bps (paga) |
| **Maker** | LO (fornisce liquidità) | +0.2 bps (riceve rebate) |

Le exchange "inverted" applicano fee inverse per attrarre flusso aggressivo.

### Dark Pool vs Mercati Lit

| Caratteristica | Lit market | Dark pool |
|---------------|------------|-----------|
| Visibilità LOB | Completa pre-trade | Nessuna pre-trade |
| Prezzo di esecuzione | Miglior prezzo disponibile | Midprice (senza spread) |
| Fill guarantee | Dipende da liquidità | Solo se matching interno |
| Tipica quota volume | 80–90% | 10–20% |

### Colocation

Server co-locati presso il matching engine: latenza ≈ 100 μs vs ≈ 1–10 ms per trader remoti. Rilevante solo per strategie HFT che competono su priorità di coda o first-mover advantage.

---

## Fatti Stilizzati sulla Microstruttura

1. **Spread si media-reverte** verso un floor dettato dalla liquidità del mercato
2. **Order flow autocorrelato**: gli MO buy si raggruppano dopo altri MO buy (herding)
3. **Profondità asimmetrica**: lo squilibrio bid/ask prevede la direzione del prezzo a breve
4. **Arrivi di trade come processo di Hawkes** — auto-eccitante, si concentra nel tempo
5. **Autocorrelazione dei rendimenti**: negativa alla frequenza tick (bid-ask bounce), positiva a 5–30 min
6. **Volatilità U-shape intraday**: alta all'apertura (09:30–10:00 ET), bassa a metà giornata, alta alla chiusura

```python
from arch import arch_model
import pandas as pd

def estimate_lob_features(tob_data: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola features LOB rolling da Top-Of-Book tick data.
    
    tob_data: DataFrame con colonne bid, ask, bid_size, ask_size, timestamp
    """
    df = tob_data.copy()
    df['midprice']   = (df['bid'] + df['ask']) / 2
    df['spread']     = df['ask'] - df['bid']
    df['oi_depth']   = (df['bid_size'] - df['ask_size']) / \
                       (df['bid_size'] + df['ask_size'])
    df['microprice'] = (df['ask_size'] * df['bid'] + df['bid_size'] * df['ask']) / \
                       (df['bid_size'] + df['ask_size'])
    
    # Segnale di imbalance rolling (5 eventi)
    df['oi_smooth'] = df['oi_depth'].rolling(5).mean()
    
    # Direzione predetta dal microprice
    df['micro_signal'] = np.sign(df['microprice'] - df['midprice'])
    
    return df[['midprice', 'spread', 'oi_depth', 'microprice', 'micro_signal']]
```

---

## Pattern Empirici Intraday (Cap. 3–4)

### Volume a U-Shape

Il volume giornaliero segue un pattern a U: elevato in apertura e chiusura, basso a metà seduta.

**Implicazione per VWAP**: aumenta il tasso di partecipazione in apertura (09:30–10:30) e in chiusura (15:00–16:00); riduci a metà giornata.

### Legge della Radice Quadrata (Price Impact)

Per ordini grandi, l'impatto di prezzo segue:

$$\Delta P \approx \gamma \cdot Q^{\alpha} \qquad \alpha \approx 0.5\text{–}0.7 \quad \text{(square root law)}$$

- Per $Q < 5\%$ ADV: $\alpha \approx 1$ (lineare)
- Per $Q > 5\%$ ADV: $\alpha \approx 0.5$ (radice quadrata)

### Decomposizione dello Spread

$$s = 2\cdot(\underbrace{c_{AS}}_{\text{adverse selection}} + \underbrace{c_{inv}}_{\text{inventario}} + \underbrace{c_{fix}}_{\text{tick floor}})$$

- $c_{AS}$ domina per asset illiquidi/volatili
- $c_{fix}$ domina per large-cap liquidi (spread = 1 tick)
- Empiricamente: $s \propto \sigma^{0.5}$
