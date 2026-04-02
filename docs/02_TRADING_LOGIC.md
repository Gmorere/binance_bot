# 02 - Trading Logic

## Cadena logica del trade hoy
1. Se analiza una barra `15m` ya cerrada.
2. Se detecta breakout valido sobre historico hasta `trigger_index`.
3. En backtest research tambien puede detectarse un `PULLBACK` continuation de forma experimental si el simbolo/config lo habilitan.
4. Se construye `TradeCandidate` con un `entry_reference_price` inyectado por el caller.
5. En backtest research se puede bloquear el `TradeCandidate` por contexto `1h/4h` y por restricciones de lado/simbolo.
6. El caller decide el modo de ejecucion:
   - backtest: usa el open de la vela siguiente
   - paper: usa el close de la vela de senal como referencia operativa local
7. Se construye `OrderPlan`.
8. Se resuelve riesgo y sizing segun el bucket configurado y los limites del simbolo.
9. Se gestiona salida por stop, TP1, TP2, timeout o fin de datos/estado.
10. Se descuentan fees y se registra PnL neto.

## Diferencia importante entre backtest y paper
### Backtest
- La referencia de entrada es el open de la vela siguiente.
- Esto esta implementado en [signal_builder.py](/D:/binance_futures_bot/src/backtest/signal_builder.py).
- Usa `runtime.backtest_risk_bucket` y [sizing_engine.py](/D:/binance_futures_bot/src/risk/sizing_engine.py).
- Puede exigir alineacion con contexto `4h/1h` y lados permitidos por simbolo via [context_policy.py](/D:/binance_futures_bot/src/strategy/context_policy.py).
- Luego simula la vida completa del trade sobre una ventana futura.

### Paper
- La referencia de entrada por defecto es el close de la vela de senal.
- Esto esta implementado via [candidate_scanner.py](/D:/binance_futures_bot/src/live/candidate_scanner.py).
- Usa `runtime.paper_risk_bucket`, limites diarios y semanales, riesgo abierto y `sizing_engine`.
- No es ejecucion real de exchange; es una aproximacion local para validar contratos operativos.

## Que esta implementado
- parciales TP1/TP2,
- fee de entrada,
- fee de salida,
- PnL neto,
- slippage adverso por simbolo en entrada y salida,
- proteccion contra doble castigo cuando un stop ya sale por gap adverso al open,
- prioridad conservadora del stop en vela ambigua,
- paper state persistente,
- limites diarios y semanales en paper,
- riesgo abierto y maximo de posiciones en paper,
- scheduler de market data para evitar polling inutil,
- bucket de riesgo configurable en backtest y paper,
- riesgo dinamico por score en backtest y paper cuando la config lo habilita,
- sizing por `sizing_engine` en backtest y paper,
- filtro research de contexto `4h/1h` y lado permitido en backtest.

## Que NO esta integrado todavia
- score como bucket operativo dinamico real en live,
- lifecycle live de ordenes en Binance,
- reconciliacion de fills y estado,
- account sync,
- limites agregados de portafolio dentro del backtest por simbolo,
- contexto `4h/1h` y restricciones por lado dentro de live real.

## Decisiones implementadas hoy
### Entrada
- Backtest: siguiente open.
- Paper: close de la vela de senal por defecto.
- Live: no implementado.
- `PULLBACK` experimental: usa el mismo esquema de entrada en backtest que `BREAKOUT`, pero con stop anclado al extremo del pullback y no a una consolidacion.
- `PULLBACK` ya soporta un filtro adicional de `body/ATR` para bloquear velas de reanudacion demasiado violentas; esta regla no afecta a `BREAKOUT`.

### Stop
- El stop se evalua intrabar en backtest y en paper sobre la vela cerrada mas reciente.
- Si hay gap adverso peor que el stop, la salida se resuelve al open de esa vela.

### Prioridad intrabar
- Regla conservadora: si una vela puede tocar stop y target, manda stop.
- Antes de TP1:
  - LONG: `stop -> tp2 directo -> tp1`
  - SHORT: `stop -> tp2 directo -> tp1`
- Despues de TP1:
  - LONG: `stop remanente -> tp2`
  - SHORT: `stop remanente -> tp2`

### Parciales
- TP1 liquida 40%.
- TP2 o stop cierran el remanente 60%.

### Fees
- Se cobra fee de entrada al abrir.
- Se cobra fee de salida por cada ejecucion parcial o final.
- La config actual usa `0.0004` por lado.

### Sizing y riesgo
- Backtest y paper ya usan [sizing_engine.py](/D:/binance_futures_bot/src/risk/sizing_engine.py).
- Paper puede usar bucket fijo de runtime o resolver riesgo dinamico por score si la config lo habilita.
- Backtest y paper pueden seguir usando bucket fijo de runtime o resolver `risk_pct` dinamicamente por score si `strategy.dynamic_risk_by_score.enabled=true`.
- El score actual usa contexto `4h/1h`, estructura, momentum, volumen, liquidez y correlacion base para mapear el setup a `small`, `normal`, `strong` o `exceptional`.
- Backtest sigue siendo economicamente distinto de paper porque cambia el precio de entrada, aplica gating research adicional y no replica limites agregados del mismo modo.

### Timeout / ventana maxima
- Backtest usa `trade_management.max_bars_in_trade` como cierre temporal forzado.
- Ese valor ya puede venir con override por simbolo via `trade_management.by_symbol`.
- `core` actual:
  - `BTCUSDT`: `16` barras
  - `ETHUSDT`: `32` barras
- La motivacion actual no es cosmetica: en `ETH` los `TIMEOUT` venian siendo positivos y al extender la ventana de `24` a `32` barras mejoraron `PnL`, `profit factor` y `expectancy`.

### Liquidez y slippage
- No hay profundidad de mercado real.
- Hay slippage adverso simple por simbolo aplicado de punta a punta en backtest y paper.
- Los stops con gap siguen usando el open adverso y no duplican castigo con otro slippage encima.
- Sigue siendo un modelo simple; no representa libro, profundidad ni latencia real.

## Invariantes que no deben romperse
- Un trade no puede cerrar dos veces.
- TP1 no debe cerrar 100% si existe remanente.
- El PnL neto debe reconciliar fees de entrada y salida.
- `TradeCandidate` debe seguir siendo la fuente unica del setup operable.
- Paper y backtest no deben mezclar datos futuros para decidir la senal actual.

## Riesgos vigentes de la logica
- backtest y paper siguen sin ser equivalentes por la entrada y los limites agregados,
- falsa sensacion de live readiness por existencia del cliente Binance,
- score ya gobierna riesgo en backtest y paper cuando la config lo habilita, pero todavia no live,
- el `PULLBACK` nuevo ya existe en codigo y ya tiene un filtro especifico de `body/ATR`, pero la muestra valida sigue siendo chica y todavia no justifica promotion al core,
- ausencia de ejecucion real y reconciliacion.
