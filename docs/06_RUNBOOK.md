# 06 - Runbook

## Operacion normal
1. Mantener datos actualizados o habilitar refresh REST.
2. Ejecutar backtest o paper mode segun el objetivo.
3. Revisar trades exportados, eventos del runtime y estado persistido.
4. Revisar `baseline_summary.json`, `baseline_symbols.csv` y `config_snapshot.json` en backtest.
5. Revisar metricas, drawdown y riesgo abierto.
6. Validar que no haya cambios inesperados frente a baseline.

## Modos reales del repo
- `backtest`: research reproducible por simbolo.
- `paper`: runtime continuo con estado local y market data actualizable.
- `live`: runtime `v0.1` seguro disponible para reconciliacion minima de cuenta Binance y heartbeat operativo, con ejecucion real bloqueada por default (`LIVE_ENABLED=false`).

El camino operativo serio sigue siendo `backtest -> paper -> live v0.1 seguro -> live con routing real`.

## Operacion cloud esperada
- El proceso corre dentro de un contenedor o runtime Linux.
- La configuracion activa entra por `BOT_CONFIG_PATH`.
- Los paths de trabajo se resuelven desde `BOT_BASE_DIR` o por overrides explicitos.
- `data/` y `outputs/` deben vivir en volumen persistente si no queres perder estado al reiniciar.

## Render actual
- El target actual es un `worker` de Render, no un `web service`.
- El Blueprint esta en [render.yaml](/D:/binance_futures_bot/render.yaml).
- La config usada por ese worker esta en [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
- El disco persistente esperado se monta en `/app/runtime`.
- El paso pendiente no es "subir el repo", sino aplicar y validar el worker en Render.

## Camino recomendado hacia Binance operativo
1. Validar senal y riesgo en backtest.
2. Correr `paper mode` con dataset estable o refresh REST.
3. Dejar paper corriendo 24/7 en cloud con estado persistente.
4. Validar conectividad Binance con testnet.
5. Reemplazar o complementar REST polling con market data mas cercana a tiempo real.
6. Recien despues habilitar lifecycle real de ordenes y reconciliacion.

## Backtest operativo actual
- Puede correrse completo o por subset con `run_backtest.py --symbols ...`.
- Guarda outputs por simbolo y baseline consolidada de corrida.
- Si se corre por tramos, la baseline consolidada final se puede reconstruir con [rebuild_backtest_baseline.py](/D:/binance_futures_bot/scripts/rebuild_backtest_baseline.py).
- [config/base.yaml](/D:/binance_futures_bot/config/base.yaml) ahora representa el `core` research: `BTCUSDT` y `ETHUSDT`, ambos `SHORT` only.
- [config/research.xrp_long.yaml](/D:/binance_futures_bot/config/research.xrp_long.yaml) deja `XRPUSDT` como laboratorio separado `LONG` only y sin exigir contexto.

## Que hace hoy el paper mode
- Reutiliza `TradeCandidate` como fuente unica del setup.
- Usa `runtime.paper_risk_bucket` como base y puede resolver riesgo por score si `strategy.dynamic_risk_by_score.enabled=true`.
- Aplica sizing con `sizing_engine`.
- Gestiona TP1, TP2 y stop sobre la ultima vela cerrada.
- Persiste estado local en `outputs/paper/paper_state.json`.
- La persistencia del state ya se escribe via archivo temporal + `replace`, para reducir corrupcion si el proceso cae durante el write.
- Puede correr en loop continuo y solo procesa simbolos con vela nueva.
- Consume un servicio de market data con contrato `poll()`.
- Si el servicio informa `next_poll_after_ms`, el loop duerme hasta esa marca en vez de iterar siempre por `poll_interval_seconds`.
- La implementacion concreta actual puede refrescar `15m`, `1h` y `4h` por REST solo cuando ya deberia existir una vela nueva cerrada.
- Si la config activa `strategy.backtest_policy`, paper aplica el mismo gating research de contexto/lado antes de abrir.
- Si la config activa `strategy.dynamic_risk_by_score`, paper puede bloquear setups por score bajo antes del sizing y deja `risk_bucket` persistido en estado/eventos cuando abre.
- Si el proceso estuvo caido y vuelven varias velas de golpe, paper ya recorre vela por vela para gestionar posiciones abiertas antes de decidir nuevas aperturas.

## Lo que NO hace todavia
- no consume websocket ni user stream,
- no sincroniza ordenes ni posiciones reales con Binance,
- no ejecuta routing de ordenes reales en `live v0.1` (guard-rail activo),
- score ya puede gobernar aperturas paper si la config lo habilita, pero todavia no gobierna live,
- no abre trades retroactivos sobre velas perdidas; el replay solo corrige gestion de posiciones abiertas,
- el precio de entrada de paper sigue aproximado al `close` de la vela de senal.

## Servicio de market data actual
- `paper_runtime` no conoce detalles de refresh REST ni de carga de CSV.
- El contrato actual es un servicio con `poll()` que devuelve snapshot, resultados de refresh y `next_poll_after_ms`.
- La implementacion concreta hoy es `PollingMarketDataService`.
- Si `data.refresh_from_binance_rest=true`, el servicio agenda el siguiente refresh segun cierre real de vela (`ultimo_timestamp` de apertura + `2*timeframe + grace`).
- Si el proximo cierre esperado todavia no llego, devuelve snapshot cacheado y loguea `data_refresh_skip`.

## Chequeo operativo minimo en Render
- Confirmar que Render lea [render.yaml](/D:/binance_futures_bot/render.yaml).
- Confirmar que `BOT_CONFIG_PATH=/app/config/render.paper.yaml`.
- Confirmar que el worker tenga disco persistente montado en `/app/runtime`.
- Confirmar permisos de escritura sobre `/app/runtime/data` y `/app/runtime/outputs`.
- Mantener `binance.use_testnet: true` para account/orders hasta validar un paso posterior.
- Mantener `binance.use_testnet_market_data: false` si queres que paper use velas reales de produccion.

## Refresh REST en paper mode
- Activar `data.refresh_from_binance_rest: true`.
- Ajustar `data.candle_close_grace_seconds` si Binance publica la vela cerrada con retraso.
- Ajustar `data.refresh_error_backoff_seconds` para espaciar reintentos cuando Binance devuelve bloqueos temporales (`418`/throttling infra).
- Ajustar `binance.market_data_limit` si hace falta acelerar bootstrap o reducir payloads.
- Ajustar `binance.rest_max_retries` y `binance.rest_retry_backoff_ms` para tolerar cortes REST transitorios (`429/5xx` o red).
- El updater mergea por timestamp y descarta la vela todavia abierta.
- Si Binance REST falla para algun simbolo/timeframe, el runtime loguea `data_refresh_error`, sigue con snapshot local y aplica `data_refresh_error_backoff` antes del proximo intento.

## Troubleshooting rapido
### Render no crea el servicio
- revisar que el repo tenga [render.yaml](/D:/binance_futures_bot/render.yaml) en la raiz
- revisar permisos del repo en Render
- revisar que el plan soporte disco persistente

### El worker arranca pero no encuentra datos
- revisar `BOT_CONFIG_PATH`
- revisar overrides de `BOT_*_PATH`
- revisar que el disco persistente este montado en `/app/runtime`
- revisar si `data.refresh_from_binance_rest` esta apagado y no hay CSV base

### El runtime no ve velas nuevas
- revisar que `data.refresh_from_binance_rest` este activo o que los CSV se actualicen por fuera
- revisar que `data.candle_close_grace_seconds` no sea demasiado alto
- revisar que el servicio de market data este devolviendo timestamps nuevos
- revisar que `processed_candle_timestamps` no este adelantado por estado viejo

### El runtime parece dormir demasiado
- revisar `next_poll_after_ms` en logs
- revisar `data.candle_close_grace_seconds`
- revisar si el ultimo timestamp local quedo atrasado y el scheduler esta usando `min_spacing`

### La baseline queda parcial despues de un run largo
- correr los simbolos faltantes con `run_backtest.py --symbols ...`
- reconstruir baseline con `scripts\rebuild_backtest_baseline.py`
- verificar que `baseline_summary.json` muestre `symbol_count` esperado

### Quiero medir `XRP` sin contaminar el core
- usar `BOT_CONFIG_PATH=config/research.xrp_long.yaml`
- idealmente usar tambien `BOT_OUTPUTS_PATH` separado para no pisar `outputs/backtests`
- generar diagnostico propio con `scripts\analyze_backtest_baseline.py`

## Logs que deberian existir
- `data_refresh ...`
- `data_refresh_skip ...`
- `data_refresh_schedule ...`
- `sleep_seconds=...`
- `opened=... closed=... updated=... equity=... decisions={...}`
- apertura de trade
- `risk_bucket=...` en apertura si hubo resolucion de riesgo
- cierre parcial
- cierre final
- motivo de salida
- fees cobrados
- snapshot de config
