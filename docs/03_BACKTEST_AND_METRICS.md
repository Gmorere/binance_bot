# 03 — Backtest and Metrics

## Runner principal
El runner activo es `BacktestRunner` y recibe:
- `symbol`
- `market_df`
- `signal_fn`
- `output_dir`
- `initial_capital`
- `save_outputs`

## Flujo del backtest implementado
1. Normaliza `market_df` con `reset_index(drop=True).copy()`.
2. Recorre el dataset índice por índice.
3. Evalúa señales con `signal_fn`.
4. Si hay señal, usa el `execution_result` ya simulado por el builder.
5. Registra un `TradeRecord`.
6. Avanza el índice hasta el cierre del trade para evitar superposición.
7. Construye equity curve.
8. Calcula métricas.
9. Guarda outputs si corresponde.

## Importante
- El backtest activo opera hoy por símbolo, no como portafolio multi-posición real.
- No usa el motor de riesgo agregado ni de límite diario/semanal.
- La curva de equity es una suma acumulada simple de `pnl_net_usdt`.

## Métricas actuales
El módulo actual calcula:
- `total_trades`
- `closed_trades`
- `open_trades`
- `win_rate`
- `profit_factor`
- `expectancy`
- `max_drawdown`
- `net_pnl_usdt`
- `gross_profit_usdt`
- `gross_loss_usdt`
- `avg_win`
- `avg_loss`
- `stop_loss_rate`
- `tp2_rate`
- `timeout_rate`
- `end_of_data_rate`

## Semántica actual de métricas
- `max_drawdown` está en USDT, no en porcentaje.
- `profit_factor` se fuerza a `999999.0` si no hay pérdidas.
- `tp1` no tiene rate propio porque no es motivo final de cierre del trade.

## Outputs reales
Por símbolo, el runner guarda:
- `{symbol}_trades.csv`
- `{symbol}_summary.json`
- `{symbol}_equity_curve.csv`

## Baseline auditada disponible
Archivo observado: `outputs/backtests/BTCUSDT_summary.json`

Resultado auditado:
- símbolo: `BTCUSDT`
- trades: `97`
- win rate: `31.96%`
- profit factor: `0.5621`
- expectancy: `-29.7648 USDT`
- max drawdown: `-3704.2785 USDT`
- net pnl: `-2887.1875 USDT`

## Validaciones mínimas obligatorias
- Equity curve consistente con trades cerrados.
- No usar barras futuras para decidir la señal actual.
- Fechas en orden y sin duplicados.
- Capital inicial explícito.
- Naming de outputs estable.

## Riesgos comunes del backtest actual
- sobreestimar robustez porque existen módulos que todavía no gobiernan el runtime,
- confundir drawdown absoluto con drawdown porcentual,
- usar el mismo dataset para iterar la idea y luego “validarla”,
- asumir que leverage configurado ya implica control de riesgo real,
- interpretar slippage configurado como si estuviera aplicado.
