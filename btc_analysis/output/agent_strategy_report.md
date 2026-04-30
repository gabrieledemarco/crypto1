# Strategy Report: ATR Breakout + GARCH Filter (V5 Default)

## Note
This is the default V5 strategy used when no API key is configured.
Set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` to let the AI agent design
a custom strategy from the statistical analysis results.

## Strategy Summary
- **Type**: Breakout
- **Entry**: price breaks 6-bar rolling high/low with EMA trend alignment
- **SL**: 2×ATR14  |  **TP**: 5×ATR14
- **Filter**: GARCH regime (skip LOW-vol periods), RSI, active hours 06-22 UTC
