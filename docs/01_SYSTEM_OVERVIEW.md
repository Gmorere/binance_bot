# 01 — System Overview

## Objetivo del sistema
Bot de trading orientado a generar señales, transformarlas en planes de orden, simular ejecución y evaluar desempeño mediante backtests y métricas.

## Estado real auditado
- El repo implementa hoy un backtest de breakout sobre Binance UM futures.
- El flujo operativo activo trabaja con datos OHLCV en CSV guardados en `data/raw`.
- La fuente de descarga implementada usa `https://data.binance.vision/data/futures/um/monthly/klines`.
- El mercado real auditado es cripto, no acciones.
- La estrategia ejecutada hoy es breakout de consolidación en `15m`.
- Existen módulos de contexto `4h/1h`, score y riesgo de portafolio, pero no están integrados al backtest activo.

## Flujo general implementado hoy
1. **Datos de mercado**
   - Entrada: DataFrame OHLCV con `timestamp`, `open`, `high`, `low`, `close`, `volume`.
   - Fuente implementada: CSV descargados desde Binance Data y cargados desde `data/raw`.
2. **Indicadores**
   - Se agregan EMA 20, 50, 200, TR, ATR 14 y ATR % 14.
3. **Generación de señal**
   - El builder revisa el histórico hasta `trigger_index`.
   - Detecta consolidación reciente y breakout en `15m`.
4. **Plan de orden**
   - Se construye `OrderPlan`.
   - La entrada se asume en el open de la vela siguiente.
5. **Sizing**
   - El backtest activo usa sizing provisional: `capital * risk_pct / distancia_stop`.
   - En `run_backtest.py` el `risk_pct` está fijo en `0.01`.
6. **Simulación / ejecución**
   - `simulate_trade_v1` procesa stop, TP1, TP2, timeout y end of data.
   - Soporta parcial 40% en TP1 y remanente 60% hacia TP2.
7. **Registro de trades**
   - El runner convierte el resultado a `TradeRecord`.
8. **Backtest y métricas**
   - Se construye equity curve y se calculan métricas agregadas.
9. **Persistencia de outputs**
   - El runner guarda `*_trades.csv`, `*_summary.json` y `*_equity_curve.csv`.

## Componentes activos
- `src.data.data_loader`
- `src.features.indicators`
- `src.strategy.setup_detector`
- `src.strategy.entry_rules.OrderPlan`
- `src.execution.execution_simulator.ExecutionResult`
- `src.backtest.signal_builder`
- `src.backtest.trade_record.TradeRecord`
- `src.backtest.equity_curve.build_equity_curve`
- `src.backtest.metrics.compute_backtest_metrics`
- `src.backtest.backtest_runner.BacktestRunner`

## Componentes presentes pero no integrados al runtime auditado
- `src.strategy.context_filter`
- `src.strategy.scoring_engine`
- `src.risk.risk_engine`
- `src.risk.sizing_engine`

## Principio de arquitectura
La separación entre:
- señal,
- plan de orden,
- simulación,
- métricas,

debe mantenerse.

Lo que no debe asumirse es que todos los módulos existentes ya participan del flujo real. Hoy no ocurre.

## Hechos confirmados
- Timeframe configurado: `4h` contexto, `1h` bias, `15m` entry.
- Timeframe usado por el backtest activo: `15m`.
- Universo configurado: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`.
- Tipo de estrategia activa: breakout de consolidación con momentum por volumen.
- Mercado objetivo implementado: Binance UM futures.
- Sesgo operativo implementado: long y short.
- Fees activas en config: `0.0004` entrada y `0.0004` salida.
- Slippage modelado hoy: solo slippage adverso en gaps contra el stop.

## Inferencias probables
- El objetivo de producto puede evolucionar a un sistema MTF con score y riesgo agregado.
- Ese objetivo todavía no coincide con la ruta de ejecución que hoy genera resultados.

## Riesgos estructurales vigentes
- divergencia entre documentación y comportamiento real,
- módulos “decorativos” de riesgo que no gobiernan el backtest,
- ausencia de tests de regresión,
- resultados no comparables si se refactoriza sin baseline,
- mezcla conceptual entre roadmap y sistema realmente implementado.
