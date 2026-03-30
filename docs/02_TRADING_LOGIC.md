# 02 — Trading Logic

## Cadena lógica del trade implementada hoy
1. Se analiza una barra `15m`.
2. `signal_fn(df, i)` llama a `build_breakout_signal_for_index`.
3. Se detecta consolidación reciente y breakout sobre el histórico hasta `i`.
4. Si hay setup válido, se construye un `OrderPlan`.
5. La entrada se fija en el open de la vela siguiente.
6. El tamaño se calcula con riesgo fijo provisional.
7. Se abre trade simulado sobre una ventana futura.
8. El trade puede cerrarse por:
   - `STOP_LOSS`
   - `TP2`
   - `TIMEOUT`
   - `END_OF_DATA`
   - `NO_EXIT`
9. `TP1` existe como evento parcial, pero el cierre final del trade queda etiquetado por el motivo que cierra el remanente.
10. Se descuentan fees de entrada y salida.
11. Se calcula PnL bruto y neto.

## Qué está implementado
- parciales TP1/TP2,
- trade abierto/cerrado,
- fee de entrada,
- fee de salida,
- PnL neto,
- notas de ejecución,
- slippage adverso en gap contra stop,
- cierre por timeout,
- cierre por fin de datos si se fuerza.

## Qué no está integrado todavía
- filtros de contexto `4h/1h`,
- score de setup,
- bucket de riesgo por score,
- límites diarios/semanales de pérdida,
- límites de riesgo agregado del portafolio,
- tope de notional por símbolo aplicado en runtime.

## Decisiones implementadas hoy

### Entrada
- La entrada ocurre en el open de la siguiente vela después de la vela gatillo.

### Stop
- El stop se evalúa intrabar.
- Si hay gap adverso que abre peor que el stop, la salida se toma al open de esa vela.

### Prioridad intrabar
- Regla conservadora implementada: si en la misma vela se tocan stop y target, manda stop.
- Antes de TP1:
  - LONG: `stop -> tp2 directo -> tp1`
  - SHORT: `stop -> tp2 directo -> tp1`
- Después de TP1:
  - LONG: `stop remanente -> tp2`
  - SHORT: `stop remanente -> tp2`

### Parciales
- TP1 liquida 40% de la posición.
- El remanente 60% sigue abierto hasta `TP2`, `STOP_LOSS`, `TIMEOUT` o `END_OF_DATA`.

### Fees
- Se cobra fee de entrada sobre el notional total al abrir.
- Se cobra fee de salida sobre cada ejecución parcial/final.
- El valor activo en config es `0.0004` por lado.

### Sizing
- El runtime actual no usa el motor de sizing/riesgo del repo.
- El tamaño activo es provisional: `capital * risk_pct / distancia_stop`.
- En el runner actual, `risk_pct` está fijado en `1%`.

### Liquidez y slippage
- El simulador asume liquidez suficiente para ejecutar al precio teórico.
- Solo modela deslizamiento adverso en gaps de stop.
- No modela slippage general por símbolo ni profundidad de mercado, aunque exista config para eso.

## Invariantes que no deben romperse
- Un trade no puede cerrar dos veces.
- TP1 no debe liquidar el 100% si existe remanente hacia TP2.
- El cierre final debe reconciliar cantidades parciales.
- El PnL neto debe ser consistente con PnL bruto menos fees.
- Las notas de ejecución deben reflejar lo que realmente pasó.

## Riesgos de la lógica actual
- la ruta real no usa contexto MTF ni score,
- el sizing activo ignora topes de exposición configurados,
- el slippage configurado por símbolo no participa del cálculo,
- el sistema está más cerca de un prototipo de research que de un motor de ejecución robusto.
