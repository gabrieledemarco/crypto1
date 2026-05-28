# Optimal Execution — Knowledge Map

> **Autore**: Julian Lorenz (ETH Zürich, 2008) | basato su Almgren & Chriss (2001)  
> **Fonte**: "Optimal Trading Strategies", ETH Zürich; "Optimal Execution of Portfolio Transactions", *Journal of Risk* 3(2)  
> **Metodo**: Karpathy-style atomic notes  
> ← [Torna al Master Knowledge Map](../README.md)

---

## 📖 Contenuto

| File | Contenuto chiave |
|------|-----------------|
| [01_optimal_execution_almgren_chriss.md](01_optimal_execution_almgren_chriss.md) | Modello Almgren-Chriss, IS, traiettoria ottimale $\sinh$, urgenza $\kappa$, frontiera efficiente, principio AIM, market power $\mu$ |

---

## 🗺️ Aree di Conoscenza

```
Implementation Shortfall
    ↓
Modello di Mercato (impatto temporaneo + permanente)
    ↓
Obiettivo Media-Varianza
    ↓
Traiettoria Ottimale (sinh formula)
    ↓
Frontiera Efficiente di Esecuzione
    ↓
Strategie Adattive + AIM
```

## ⚡ Cheat Sheet

| Task | Formula | File |
|------|---------|------|
| Traiettoria ottimale | $x_t = X\sinh(\kappa(T-t))/\sinh(\kappa T)$ | [01](01_optimal_execution_almgren_chriss.md) |
| Urgenza | $\kappa = \sqrt{\lambda\sigma^2/\eta}$ | [01](01_optimal_execution_almgren_chriss.md) |
| Market power | $\mu = \gamma X / (\sigma\sqrt{T})$ | [01](01_optimal_execution_almgren_chriss.md) |
| Costo backtest | $\text{cost} \approx \eta v |q|$ per trade | [01](01_optimal_execution_almgren_chriss.md) |
