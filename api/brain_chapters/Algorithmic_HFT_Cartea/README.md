# Algorithmic and High-Frequency Trading — Knowledge Map

> **Autori**: Álvaro Cartea, Sebastian Jaimungal, José Penalva  
> **Editore**: Cambridge University Press, 2015 | **ISBN**: 978-1-107-09114-6  
> **Fonte PDF**: 9781107091146 + preview 9781316455579  
> **Metodo**: Karpathy-style atomic notes — denso, first principles, zero rumore  
> ← [Torna al Master Knowledge Map](../README.md)

---

## 📖 Navigazione Rapida

| File | Cap. libro | Contenuto chiave |
|------|-----------|-----------------|
| [01_mercati_elettronici_lob.md](01_mercati_elettronici_lob.md) | 1–2, 3–4 | LOB, midprice, microprice, spread, tassonomia partecipanti, U-shape volume, price impact |
| [02_controllo_stocastico_hjb.md](02_controllo_stocastico_hjb.md) | 5 | HJB, programmazione dinamica, optimal stopping, processi di salto |
| [03_esecuzione_ottimale.md](03_esecuzione_ottimale.md) | 6–8 | Tasso ottimale, adverse selection, LO+MO misti, dark pool, price limiter |
| [04_market_making.md](04_market_making.md) | 10 | Avellaneda-Stoikov, skew inventario, adverse selection, short-term alpha |
| [05_pairs_trading_order_imbalance.md](05_pairs_trading_order_imbalance.md) | 11–12 | Cointegrazione, OU, posizione ottimale, OI predittivo, Markov chain |

---

## 🗺️ Mappa delle Dipendenze

```
Microstruttura (01)
    ↓
Strumenti Matematici: HJB (02)
    ↓
Esecuzione Ottimale (03) ──→ Market Making (04)
    ↓
Signal & Alpha: OI + Pairs (05)
```

---

## ⚡ Cheat Sheet — Formule Chiave

$$\text{Microprice}: \quad \widetilde{M}_t = \frac{V^a P^a + V^b P^b}{V^a + V^b}$$

$$\text{Tasso esecuzione}: \quad v_t^* = \frac{X_t}{T-t} + \frac{\mu}{2\eta}(T-t)$$

$$\text{Fill rate LO}: \quad \lambda(\delta) = \Lambda\,e^{-\kappa\delta}$$

$$\text{Reservation price MM}: \quad r_t = M_t - \gamma\sigma^2 X_t(T-t)$$

$$\text{Posizione pairs}: \quad q_t^* = \frac{\kappa(\theta - Z_t)}{\gamma\sigma_Z^2(T-t+1/\kappa)}$$

$$\text{Order Imbalance}: \quad OI_t = \frac{N^{buy} - N^{sell}}{N^{buy} + N^{sell}}$$

## ⚡ Cheat Sheet — Quale Modello per Quale Task?

| Task | Modello | File |
|------|---------|------|
| Liquidare un blocco in T giorni | Cartea-Jaimungal continuo | [03](03_esecuzione_ottimale.md) |
| Postare quote in modo ottimale | Avellaneda-Stoikov + skew | [04](04_market_making.md) |
| Ridurre slippage con LOB | Strategia mista LO+MO | [03](03_esecuzione_ottimale.md) |
| Catturare spread mean-reverting | Pairs trading OU ottimale | [05](05_pairs_trading_order_imbalance.md) |
| Timing di ordini intraday | Segnale OI + Markov chain | [05](05_pairs_trading_order_imbalance.md) |
| Derivare strategie con math rigorosa | Framework HJB | [02](02_controllo_stocastico_hjb.md) |
