# 05 - Testing and Validation

## Objetivo
Evitar refactors prolijos que rompan parciales, fees, `pnl_net_usdt`, persistencia o trazabilidad operativa.

## Estado actual
El repo ya no esta sin cobertura. Hoy existe una suite `unittest` con cobertura sobre los caminos criticos que se implementaron en esta auditoria y en las fases posteriores.

## Comando de validacion base
```bash
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Ultima validacion auditada:
- resultado: `74 tests`, todos OK

## Cobertura confirmada
La suite actual cubre al menos:
- simulacion de ejecucion con TP1, TP2 y stop,
- stop con gap adverso,
- slippage adverso en entrada y salida para backtest,
- proteccion contra doble slippage en stop con gap adverso,
- prioridad conservadora del stop en vela ambigua,
- metricas agregadas del backtest,
- smoke path del `BacktestRunner`,
- seleccion de subset de simbolos para backtest,
- `TradeCandidate` y scanner operativo,
- cliente Binance firmado a nivel unitario,
- updater incremental de klines,
- servicio de market data y scheduler de polling,
- `paper_engine`,
- slippage de entrada en apertura de posiciones paper,
- `paper_runtime`,
- replay candle-by-candle de velas perdidas para posiciones abiertas en paper,
- persistencia atomica de `paper_state.json` sin archivos temporales residuales,
- resolucion portable de config y paths,
- alineacion de sizing entre backtest y paper via `sizing_engine`,
- cap de notional en `signal_builder`,
- resolucion de riesgo dinamico por score en backtest,
- artefactos de baseline multi-simbolo y snapshot de config.
- diagnostico cuantitativo de baseline,
- policy research de contexto y restricciones por simbolo/lado en backtest.
- walk-forward temporal del laboratorio `ETH BREAKOUT + PULLBACK`.

## Archivos de test presentes
- [test_backtest_baseline_artifacts.py](/D:/binance_futures_bot/tests/test_backtest_baseline_artifacts.py)
- [test_backtest_baseline_diagnostics.py](/D:/binance_futures_bot/tests/test_backtest_baseline_diagnostics.py)
- [test_execution_simulator.py](/D:/binance_futures_bot/tests/test_execution_simulator.py)
- [test_backtest_metrics.py](/D:/binance_futures_bot/tests/test_backtest_metrics.py)
- [test_backtest_runner.py](/D:/binance_futures_bot/tests/test_backtest_runner.py)
- [test_context_policy.py](/D:/binance_futures_bot/tests/test_context_policy.py)
- [test_signal_service.py](/D:/binance_futures_bot/tests/test_signal_service.py)
- [test_signal_builder.py](/D:/binance_futures_bot/tests/test_signal_builder.py)
- [test_candidate_scanner.py](/D:/binance_futures_bot/tests/test_candidate_scanner.py)
- [test_binance_client.py](/D:/binance_futures_bot/tests/test_binance_client.py)
- [test_binance_kline_updater.py](/D:/binance_futures_bot/tests/test_binance_kline_updater.py)
- [test_market_data_runtime.py](/D:/binance_futures_bot/tests/test_market_data_runtime.py)
- [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py)
- [test_paper_runtime.py](/D:/binance_futures_bot/tests/test_paper_runtime.py)
- [test_config_loader.py](/D:/binance_futures_bot/tests/test_config_loader.py)
- [test_scoring_policy.py](/D:/binance_futures_bot/tests/test_scoring_policy.py)

## Casos borde que ya son obligatorios
- dataframe vacio,
- dataframe valido sin senales,
- parcial TP1 mas cierre TP2,
- stop loss con gap adverso,
- vela ambigua entre stop y target,
- scheduler que no debe refrescar antes del proximo cierre,
- runtime que no debe reprocesar la misma vela,
- recovery de una posicion abierta cuando paper recibe varias velas pendientes de una sola vez,
- escritura y lectura consistente de `paper_state.json` con replace atomico,
- fill de entrada paper afectado por `execution.slippage`,
- fill de salida backtest afectado por `execution.slippage` sin duplicar castigo en gaps de stop,
- resolucion de paths sin depender de `D:/...`,
- capping de notional por `max_notional_pct`,
- resolucion de `stop_buffer_atr_fraction` via config y overrides por simbolo,
- score alto que sube bucket/risk_pct en backtest,
- score bajo que bloquea trade antes del sizing,
- preservacion del `risk_pct` base por simbolo cuando el score intenta bajarlo por debajo del baseline research,
- bloqueo de apertura paper por score bajo antes del sizing,
- preservacion del riesgo base por simbolo tambien en paper cuando la policy de score intenta bajarlo,
- persistencia de `risk_bucket` en aperturas paper para trazabilidad del score/riesgo efectivo,
- escritura de baseline consolidada y config snapshot,
- escritura de diagnostico consolidado de baseline,
- seleccion de simbolos por `--symbols` con deduplicacion basica.

## Casos borde que siguen faltando
- columnas faltantes en datasets de market data,
- `NaN` en indicadores para el runtime continuo,
- retries o fallas transitorias de Binance REST,
- discrepancias entre estado local y estado real de exchange,
- pruebas de lifecycle de ordenes reales.
- validacion walk-forward completa del laboratorio `ETH BREAKOUT + PULLBACK` en todas las ventanas del historico local.

## Criterio de aceptacion para cambios
Un cambio pasa solo si:
- corre con la `.venv` auditada o con un entorno equivalente,
- mantiene coherencia de fees y `pnl_net_usdt`,
- no rompe tests existentes,
- agrega o ajusta tests si cambia comportamiento critico,
- actualiza documentacion si cambia contratos o flujo operativo,
- explica cualquier delta de metricas o numero de trades.

## Limite de esta validacion
La suite actual no prueba despliegue real en Render ni ejecucion real contra Binance. Tampoco pude validar `docker build` desde este entorno porque `docker` no esta disponible aca.

## Validacion temporal de research
Existe un runner especifico para medir robustez temporal del laboratorio `ETH BREAKOUT + PULLBACK`:

```bash
.\.venv\Scripts\python.exe scripts\validate_eth_pullback_walkforward.py --freq quarterly
```

Uso rapido para smoke:

```bash
.\.venv\Scripts\python.exe scripts\validate_eth_pullback_walkforward.py --freq quarterly --max-periods 1
```
