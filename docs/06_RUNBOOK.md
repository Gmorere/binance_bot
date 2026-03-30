# 06 - Runbook

## Operacion normal
1. Mantener datos actualizados o habilitar refresh REST.
2. Ejecutar backtest o paper mode segun el objetivo.
3. Revisar trades exportados y eventos del runtime.
4. Revisar metricas, drawdown y riesgo abierto.
5. Validar que no haya cambios inesperados frente a baseline.

## Operacion cloud esperada
- El proceso corre dentro de un contenedor o runtime Linux, no depende de una PC Windows.
- La configuracion activa entra por `BOT_CONFIG_PATH`.
- Los paths de trabajo se resuelven desde `BOT_BASE_DIR` o por overrides explicitos.
- `data/` y `outputs/` deben vivir en volumen persistente si no queres perder estado al reiniciar el contenedor.

## Render actual
- El target actual es un `worker` de Render, no un `web service`.
- El Blueprint esta en [render.yaml](/D:/binance_futures_bot/render.yaml).
- La config usada por ese worker esta en [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
- El disco persistente esperado se monta en `/app/runtime`.

## Camino recomendado hacia Binance live
1. Validar senal y riesgo en backtest.
2. Activar `runtime.mode=paper` y correr `run_paper.py` en contenedor/Render.
3. Si se quiere menos operacion manual, activar `data.refresh_from_binance_rest=true`.
4. Validar conectividad Binance con testnet.
5. Reemplazar el servicio de polling por una fuente mas cercana a tiempo real.
6. Recien despues habilitar lifecycle real de ordenes.

## Que hace hoy el paper mode
- Reutiliza `TradeCandidate` como fuente unica de setup.
- Usa el bucket `runtime.paper_risk_bucket` para elegir riesgo por trade.
- Aplica sizing con `calculate_position_size`.
- Gestiona TP1, TP2 y stop sobre la ultima vela cerrada.
- Persiste estado local en `outputs/paper/paper_state.json`.
- Puede correr en loop continuo y solo procesa simbolos con vela nueva.
- Consume un servicio de market data con contrato `poll()`.
- Si el servicio informa `next_poll_after_ms`, el loop duerme hasta esa marca en vez de usar siempre `poll_interval_seconds`.
- La implementacion actual del servicio refresca `15m` por REST solo cuando ya deberia existir una vela nueva cerrada.

## Lo que NO hace todavia
- No consume websocket ni user stream.
- No sincroniza ordenes ni posiciones reales con Binance.
- No coloca ordenes reales.
- No refresca `1h` ni `4h` en runtime.
- No usa todavia contexto/score como gating operativo real.
- El precio de entrada de paper sigue aproximado al close de la vela de senal.

## Servicio de market data actual
- `paper_runtime` no conoce detalles de refresh REST ni carga de CSV.
- El contrato actual es un servicio con `poll()` que devuelve snapshot, resultados de refresh y `next_poll_after_ms`.
- La implementacion concreta hoy es `PollingMarketDataService`.
- Si `data.refresh_from_binance_rest=true`, el servicio agenda el siguiente refresh segun `ultimo_timestamp + timeframe + grace`.
- Si el proximo cierre esperado todavia no llego, el servicio devuelve snapshot cacheado y loguea `data_refresh_skip`.

## Chequeo operativo Render
- Confirmar que el repo ya esta subido a GitHub/GitLab/Bitbucket.
- Confirmar que Render lea [render.yaml](/D:/binance_futures_bot/render.yaml).
- Confirmar que `BOT_CONFIG_PATH=/app/config/render.paper.yaml`.
- Confirmar que el worker tenga disco persistente montado en `/app/runtime`.
- Mantener `binance.use_testnet: true` hasta validar paper/live controlado.

## Refresh REST en paper mode
- Activar `data.refresh_from_binance_rest: true`.
- Ajustar `data.candle_close_grace_seconds` si Binance publica la vela cerrada con retraso.
- Ajustar `binance.market_data_limit` si hace falta acelerar bootstrap o reducir payloads.
- El updater mergea por timestamp y descarta la vela todavia abierta.
- Si Binance REST falla, el ciclo falla; no hay fallback silencioso.

## Troubleshooting rapido
### Render no crea el servicio
- revisar que el repo tenga `render.yaml` en la raiz
- revisar que el repo exista en GitHub/GitLab/Bitbucket
- revisar que el workspace de Render tenga acceso al repo

### El worker arranca pero no encuentra datos
- revisar `BOT_CONFIG_PATH`
- revisar overrides de `BOT_*_PATH`
- revisar que el disco persistente este montado en `/app/runtime`

### El runtime no ve velas nuevas
- revisar que `data.refresh_from_binance_rest` este activo o que los CSV se actualicen por fuera
- revisar que `data.candle_close_grace_seconds` no sea demasiado alto
- revisar que el servicio de market data este devolviendo timestamps nuevos
- revisar que `processed_candle_timestamps` no este adelantado por estado viejo

### El runtime parece dormir demasiado
- revisar `next_poll_after_ms` en logs
- revisar `data.candle_close_grace_seconds`
- revisar si el ultimo timestamp local quedo atrasado y el scheduler esta usando `min_spacing`

## Logs que deberian existir
- `data_refresh ...`
- `data_refresh_skip ...`
- `data_refresh_schedule ...`
- `sleep_seconds=...`
- apertura de trade
- cierre parcial
- cierre final
- motivo de salida
- fees cobrados
- snapshot de config
