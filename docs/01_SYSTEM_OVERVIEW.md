# 01 - System Overview

## Objetivo del sistema
Bot de trading orientado a:
- detectar setups operables,
- convertirlos en planes de orden,
- simular y registrar ejecucion,
- medir desempeno en backtest,
- correr paper mode continuo sobre Binance USD-M Futures.

## Estado real confirmado hoy
- El repo ya no es solo backtest: hoy tiene `backtest` y `paper mode`.
- El mercado implementado es Binance USD-M Futures.
- El universo configurado es `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`.
- El timeframe operativo real sigue siendo `15m`.
- El backtest research actual ya usa contexto `4h/1h` como gating y restricciones por simbolo/lado.
- Paper mode ya puede consumir `4h/1h`, aplicar el mismo gating de contexto/lado del research y resolver score dinamico opcional cuando la config lo habilita.
- Existe cliente REST de Binance y base cloud/Render, pero no existe lifecycle live completo de ordenes.

## Modos operativos actuales
### 1. Backtest
- Runner principal: `run_backtest.py`
- Usa [BacktestRunner](/D:/binance_futures_bot/src/backtest/backtest_runner.py)
- Opera por simbolo, no como portafolio real multi-posicion
- Consume `TradeCandidate`
- Ya usa bucket de riesgo configurado y [sizing_engine.py](/D:/binance_futures_bot/src/risk/sizing_engine.py)
- Ya puede gatear el setup con [context_policy.py](/D:/binance_futures_bot/src/strategy/context_policy.py) usando `1h/4h`
- La estrategia research actual excluye `BNBUSDT` y restringe lados por simbolo desde [config/base.yaml](/D:/binance_futures_bot/config/base.yaml)

### 2. Paper mode
- Entry point: `run_paper.py`
- Usa [run_paper_runtime_loop](/D:/binance_futures_bot/src/live/paper_runtime.py)
- Mantiene estado local, posiciones, PnL, riesgo abierto y timestamps procesados
- Puede refrescar `15m`, `1h` y `4h` desde Binance REST y correr en loop continuo
- Usa bucket de riesgo configurado, limites locales y `sizing_engine`
- Ya puede reutilizar la politica research de lado y contexto al abrir trades

### 3. Live
- Existe `live v0.1` en modo seguro (reconciliacion minima + heartbeat)
- La ejecucion real de ordenes sigue bloqueada por defecto (`LIVE_ENABLED=false`)
- Hay cliente exchange en [binance_usdm_client.py](/D:/binance_futures_bot/src/exchange/binance_usdm_client.py)
- Falta lifecycle real de ordenes, reconciliacion completa y account sync en tiempo real

## Flujo operativo implementado hoy
1. Market data en `data/raw` o refresh REST incremental.
2. Enriquecimiento con EMA 20/50/200, TR, ATR 14 y ATR % 14.
3. Deteccion de setup breakout.
4. Soporte experimental de setup `PULLBACK` en backtest research.
5. Construccion de `TradeCandidate`.
6. En backtest, gating opcional por contexto `1h/4h` y restricciones por simbolo/lado.
7. Conversion a `OrderPlan`.
8. Resolucion de riesgo y sizing segun modo.
9. Ejecucion segun modo:
   - backtest: simulacion futura
   - paper: apertura y gestion de posicion local
10. Registro de eventos, trades, equity y outputs.

## Componentes activos del flujo dominante
- [src/core/config_loader.py](/D:/binance_futures_bot/src/core/config_loader.py)
- [src/data/data_loader.py](/D:/binance_futures_bot/src/data/data_loader.py)
- [src/data/binance_kline_updater.py](/D:/binance_futures_bot/src/data/binance_kline_updater.py)
- [src/features/indicators.py](/D:/binance_futures_bot/src/features/indicators.py)
- [src/strategy/signal_service.py](/D:/binance_futures_bot/src/strategy/signal_service.py)
- [src/strategy/context_policy.py](/D:/binance_futures_bot/src/strategy/context_policy.py)
- [src/strategy/context_filter.py](/D:/binance_futures_bot/src/strategy/context_filter.py)
- [src/live/candidate_scanner.py](/D:/binance_futures_bot/src/live/candidate_scanner.py)
- [src/backtest/signal_builder.py](/D:/binance_futures_bot/src/backtest/signal_builder.py)
- [src/risk/risk_engine.py](/D:/binance_futures_bot/src/risk/risk_engine.py)
- [src/risk/sizing_engine.py](/D:/binance_futures_bot/src/risk/sizing_engine.py)
- [src/execution/execution_simulator.py](/D:/binance_futures_bot/src/execution/execution_simulator.py)
- [src/live/paper_engine.py](/D:/binance_futures_bot/src/live/paper_engine.py)
- [src/live/market_data_runtime.py](/D:/binance_futures_bot/src/live/market_data_runtime.py)
- [src/live/paper_runtime.py](/D:/binance_futures_bot/src/live/paper_runtime.py)

## Componentes presentes pero no integrados al flujo dominante
- [src/strategy/scoring_engine.py](/D:/binance_futures_bot/src/strategy/scoring_engine.py)

## Hechos confirmados
- `TradeCandidate` es la fuente unica del setup operable.
- Backtest y paper reutilizan la misma deteccion de setup.
- Backtest y paper ya comparten bucket de riesgo configurado y `sizing_engine`.
- El backtest research actual ya filtra por contexto y por lado/simbolo desde config.
- Paper ya puede usar market data de produccion aunque `binance.use_testnet` siga activo para el path de ordenes.
- El repo ya soporta `PULLBACK` en el flujo de backtest, pero el `core` oficial no lo activa todavia.
- Render esta preparado para paper mode, no para live.

## Inferencias probables
- El producto final apunta a Binance automatizado primero y acciones despues.
- El siguiente salto tecnico serio es reconciliacion y account sync, no mas backtest logic aislada.

## Riesgos estructurales vigentes
- backtest y paper todavia difieren en el precio de entrada y en limites agregados,
- score ya puede gobernar backtest y paper si la config lo habilita, pero sigue fuera de live,
- ausencia de live execution de punta a punta,
- dependencia actual de REST polling para market data,
- baseline v2 apenas positiva y todavia fragil.
