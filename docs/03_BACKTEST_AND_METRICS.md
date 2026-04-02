# 03 - Backtest and Metrics

## Alcance real
Este documento cubre solo el modo `backtest`.

El repo ya no es solo research offline: hoy tambien existe `paper mode` con loop continuo. Aun asi, las metricas de este archivo siguen siendo las del backtest por simbolo y no describen portfolio live ni estado real de cuenta.

## Runner activo
El entrypoint principal es [run_backtest.py](/D:/binance_futures_bot/run_backtest.py).

Ese script:
- carga `config/base.yaml` o el override definido por `BOT_CONFIG_PATH`,
- resuelve paths desde la base del proyecto,
- carga `15m`, `1h` y `4h` por simbolo desde `data/raw`,
- resuelve `runtime.backtest_risk_bucket`,
- traduce ese bucket a `risk_pct`,
- construye un `signal_fn` a partir de `TradeCandidate`,
- puede aplicar `strategy.backtest_policy` para gatear por contexto y lado permitido,
- puede resolver riesgo por score del setup si `strategy.dynamic_risk_by_score.enabled=true`,
- resuelve `filters` efectivos por simbolo con fallback al bloque global y soporte para `filters.by_symbol`,
- usa `sizing_engine` por simbolo,
- ejecuta `BacktestRunner`,
- guarda outputs por simbolo y baseline consolidada bajo `outputs/backtests/`.

## Flujo implementado
1. Carga los dataframes del simbolo para `15m`, `1h` y `4h`.
2. Recorre el dataset vela por vela.
3. Pide un `TradeCandidate` a la capa de senal.
4. Si la policy research esta activa, bloquea candidates fuera de contexto o fuera del lado permitido.
5. Si hay setup valido, resuelve riesgo y sizing por config.
6. Simula entrada, parciales y salida final.
7. Registra un `TradeRecord`.
8. Avanza el indice hasta el cierre del trade para evitar superposicion artificial.
9. Construye la equity curve.
10. Calcula metricas agregadas.
11. Exporta outputs por simbolo y artefactos de corrida.

## Lo que si hace hoy
- opera por simbolo,
- usa la cadena operable basada en `TradeCandidate`,
- usa bucket de riesgo configurado,
- usa `sizing_engine` y `max_notional_pct` por simbolo,
- ya puede usar contexto `1h/4h` como gating research,
- ya puede traducir score del setup a bucket/risk_pct dinamico antes del sizing,
- ya puede excluir simbolos y restringir lados por simbolo desde config,
- ya puede usar filtros de entrada distintos por simbolo sin duplicar la logica de setup,
- ya puede soportar `allowed_setups_by_symbol` y habilitar `PULLBACK` experimental en research,
- calcula fees y `pnl_net_usdt`,
- soporta TP1, TP2 y stop,
- deja trazabilidad exportable por corrida.

## Lo que no hace hoy
- no modela portfolio multi-posicion real,
- no aplica limites agregados diarios o semanales para bloquear nuevas aperturas,
- no modela lifecycle real de ordenes Binance,
- no gobierna todavia el runtime live real,
- no convierte leverage configurado en control de exposicion agregado a nivel portfolio,
- no modela reconciliacion de fills ni estado de exchange.

## Divergencia importante frente a paper mode
Backtest y paper comparten `TradeCandidate`, bucket configurable y `sizing_engine`, pero no son identicos:
- en backtest la entrada se aproxima desde la siguiente vela segun el builder,
- en paper la entrada por defecto se aproxima al `close` de la vela de senal,
- en paper ya existen limites diarios, semanales y de riesgo abierto durante el ciclo,
- en backtest el flujo sigue siendo por simbolo y sin estado agregado de portfolio.

Eso significa que un resultado de backtest no debe venderse como si fuera el mismo comportamiento del runtime automatizado.

## Metricas actuales
El modulo actual calcula:
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
- metricas proxy de uso de capital por simbolo y agregadas:
  - `avg_notional_pct_of_capital`
  - `avg_margin_pct_of_capital`
  - `time_in_market_share`
  - `time_weighted_notional_usage_pct`
  - `time_weighted_margin_usage_pct`
  - `capital_idle_share_proxy`

## Semantica actual
- `max_drawdown` esta en USDT, no en porcentaje.
- `profit_factor` se fuerza a `999999.0` si no hay perdidas.
- `tp1` no tiene rate final propio porque no es motivo final de cierre.
- la equity curve se construye sobre `pnl_net_usdt` acumulado.

## Outputs reales
Por simbolo, el runner guarda:
- `{symbol}_trades.csv`
- `{symbol}_summary.json`
- `{symbol}_equity_curve.csv`

Por corrida, el runner guarda:
- `config_snapshot.json`
- `baseline_summary.json`
- `baseline_symbols.csv`

Directorio por defecto:
- [outputs/backtests](/D:/binance_futures_bot/outputs/backtests)

## Contrato actual de filtros research
La config mantiene un bloque `filters` global y puede sumar overrides por simbolo en `filters.by_symbol`.

Ejemplo vigente del `core`:
- `BTCUSDT`
  - `stop_buffer_atr_fraction = 0.10`
  - `min_breakout_volume_multiple = 1.0`
  - `max_consolidation_range_atr_multiple = 1.2`
  - `max_trigger_candle_atr_multiple = 1.6`
- `ETHUSDT`
  - `stop_buffer_atr_fraction = 0.10`
  - `min_breakout_volume_multiple = 1.0`
  - `max_consolidation_range_atr_multiple = 1.4`
  - `max_trigger_candle_atr_multiple = 1.6`

Regla actual:
- si un simbolo no tiene override en `filters.by_symbol`, usa el bloque global.
- si existe override por simbolo, solo pisa las claves informadas y hereda el resto.

## Contrato actual de setups research
- `strategy.allowed_setups` define el universo de setups soportados.
- `strategy.allowed_setups_by_symbol` permite restringir por simbolo que setup se evalua realmente.
- El repo ya soporta `BREAKOUT` y `PULLBACK` en backtest.
- El `core` oficial hoy sigue activo solo con:
  - `BTCUSDT`: `BREAKOUT`
  - `ETHUSDT`: `BREAKOUT`
- El laboratorio [results.md](/D:/binance_futures_bot/outputs/eth_pullback_lab/results.md) mostro que `PULLBACK` sube frecuencia en `ETH`, pero no gana suficiente por si solo para entrar al `core`.

## Contrato actual de gestion temporal
La config ya soporta `trade_management.max_bars_in_trade` con overrides por simbolo en `trade_management.by_symbol`.

Ejemplo vigente del `core`:
- `BTCUSDT`
  - `max_bars_in_trade = 16`
- `ETHUSDT`
  - `max_bars_in_trade = 32`

Regla actual:
- si un simbolo no tiene override, usa el timeout global.
- si existe override por simbolo, ese valor reemplaza al global solo para ese simbolo.

## Contrato actual de deployment del capital
El `core` ya no usa el bucket `normal` en backtest. Hoy corre con `runtime.backtest_risk_bucket = strong`, que traduce a `risk_pct base = 0.0085`, y ya no opera con `max_notional_pct = 0.60`.

Ejemplo vigente del `core`:
- `BTCUSDT`
  - `max_notional_pct = 0.80`
- `ETHUSDT`
  - `max_notional_pct = 0.90`

Lectura correcta:
- primero la mejora vino de liberar el cap de notional,
- despues se promovio `risk_pct base = 0.0085` porque con `max_notional_pct = 0.80` ya empezo a mover `PnL` real,
- despues se promovio `ETHUSDT max_notional_pct = 0.90` porque `ETH` es el principal motor del `core` y el laboratorio de overweight mejoro `PnL` total sin bajar `BTCUSDT` a `0.70`,
- despues se promovio `ETHUSDT risk_pct = 0.0100` via `risk.backtest_by_symbol` porque mejora el agregado sin tocar `BTCUSDT` ni `leverage`,
- `ETHUSDT risk_pct = 0.0110` no se promovio porque acerca demasiado el simbolo al cap y empuja drawdown mas de lo prudente para esta etapa,
- no se toco `leverage`.

## Contrato actual de score dinamico
- `strategy.dynamic_risk_by_score.enabled=true` activa el mapeo `score -> risk bucket` en backtest.
- `strategy.dynamic_risk_by_score.preserve_symbol_base_risk=true` evita que el score baje el `risk_pct` por debajo del baseline research ya validado por simbolo.
- El score se calcula sobre:
  - contexto `4h/1h`,
  - estructura del setup,
  - momentum/volumen,
  - liquidez del simbolo,
  - correlacion base.
- El score resultante se mapea via `risk.map_score_to_risk` a:
  - `small`
  - `normal`
  - `strong`
  - `exceptional`
- Si el score no supera `score_thresholds.min_trade`, el trade se bloquea antes del sizing.
- Si falta contexto suficiente, el runner cae al bucket/risk_pct base para no romper compatibilidad.
- Con la politica vigente (`min_trade = 75` + `preserve_symbol_base_risk = true`), el score actual funciona mas como filtro economico y trazabilidad de calidad que como recorte agresivo del sizing ya validado.

## Baseline auditada disponible
Baseline `core` actual:
- archivo: [baseline_summary.json](/D:/binance_futures_bot/outputs/backtests/baseline_summary.json)
- simbolos incluidos: `BTCUSDT`, `ETHUSDT`
- `BNBUSDT`, `SOLUSDT` y `XRPUSDT` quedan fuera del `core` por `strategy.backtest_policy.excluded_symbols`
- trades agregados: `63`
- net pnl agregado: `524.7745 USDT`
- mejor simbolo por net pnl: `ETHUSDT`
- peor simbolo por net pnl: `BTCUSDT`
- `aggregate_time_in_market_share_proxy`: `1.84%`
- `aggregate_time_weighted_margin_usage_pct_proxy`: `0.19%`
- `aggregate_capital_idle_share_proxy`: `99.81%`

Lectura correcta:
- esta baseline ya incluye score dinamico corregido en backtest,
- la comparacion valida ya no es contra la baseline vieja pre-slippage,
- en el engine actual, la politica corregida de score mejora al fixed-risk actual porque bloquea trades mas flojos y preserva el riesgo base por simbolo,
- `ETHUSDT` sigue corriendo con override research `risk_pct = 0.0100`, mientras `BTCUSDT` mantiene `0.0085`,
- el edge y la utilizacion de capital mejoraron, pero el capital sigue extremadamente subutilizado en el tiempo,
- esto sigue sin ser validacion suficiente para paper/live automatizado,
- y `paper/live` todavia no consumen esta politica de score.

## Validaciones minimas obligatorias
- no usar barras futuras para decidir la senal actual,
- equity curve consistente con trades cerrados,
- fechas en orden y sin duplicados,
- capital inicial explicito,
- naming de outputs estable,
- snapshot de config guardado por corrida,
- baseline consolidada multi-simbolo guardada por corrida,
- baseline diagnostica disponible via `scripts/analyze_backtest_baseline.py`,
- cualquier delta fuerte de numero de trades o `pnl_net_usdt` debe explicarse,
- cualquier cambio de bucket o sizing debe explicarse porque altera exposicion y fee drag.

## Riesgos del backtest actual
- confundir backtest por simbolo con portfolio real,
- sobreestimar robustez porque todavia no existen limites agregados dentro del runner,
- asumir que leverage configurado ya implica control de riesgo completo,
- asumir que el slippage simple actual representa friccion de mercado real,
- asumir que score dinamico en backtest ya valida paper/live,
- comparar corridas usando `max_drawdown` sin aclarar que esta en valor absoluto,
- vender como validacion un resultado que todavia depende de una entrada distinta de paper o live,
- asumir que una baseline apenas positiva ya resuelve el problema de edge.
