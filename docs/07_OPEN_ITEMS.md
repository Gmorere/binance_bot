# 07 - Open Items

## Abiertos despues de la auditoria
- [ ] reemplazar `PollingMarketDataService` por una fuente mas cercana a tiempo real con websocket o polling dedicado
  — **Diferido a live**: para estrategia 15m la latencia REST (~2-4s vs websocket) no afecta el edge. Relevante cuando haya ordenes reales donde la latencia de entrada importe.
- [ ] separar claramente market data polling vs user/account sync
  — **Diferido a live**: no aplica hasta tener account sync real. En paper mode no hay estado de cuenta externo que sincronizar.
- [ ] definir reconciliacion de ordenes y posiciones ante respuestas `503` y estado desconocido
- [ ] integrar limites agregados de portafolio y perdida al research de forma coherente con el runtime
- [x] decidir si el score dinamico debe pasar tambien a live o si queda limitado a backtest/paper por ahora
  — **Decision 2026-04-16**: el score va a live sin excepcion. No es un feature experimental sino el sistema de riesgo del core. Backtest y paper fueron validados con score activo; desactivarlo en live seria inconsistente. La implementacion es parte del routing de ordenes (ver item de reconciliacion).
- [x] decidir si `SOLUSDT` y `XRPUSDT` siguen en el universo research actual o requieren mas recorte
  — **Decision 2026-04-16**: SOLUSDT y XRPUSDT cortados del universo. XRP: PF 1.12, 31 trades, break-even. SOL: PF 1.37, 22 trades, MaxDD desproporcionado. Eliminados de `base.yaml`. Labs de research conservados en `config/research.xrp_long.yaml`.
- [x] decidir si `ETH PULLBACK` sigue vivo como research; hoy el walk-forward trimestral mejora solo por `2` trades extra y necesita mas historico antes de promotion
  — **Decision 2026-04-16**: ETH PULLBACK se mantiene como research, no se promueve. Walk-forward completo (Q1 2025 - Q1 2026 con slippage correcto): solo 2 trades extra en 5 trimestres. En los 4 trimestres perdedores no rescata el resultado. Re-evaluar cuando haya 2-3 trimestres mas de datos.
- [ ] decidir si el slippage simple actual alcanza o si hace falta modelado mas realista por tipo de salida/latencia
- [ ] definir metricas de portafolio y no solo por simbolo
- [ ] convertir `max_drawdown` a una convencion unica y explicita
- [x] aplicar y validar el worker de Render en entorno real
  — **Validado 2026-04-16**: worker desplegado en Render Frankfurt, descarga datos REST BTC+ETH, corre ciclos de paper sin errores. Instancia primaria de paper trading.
- [x] agregar observabilidad y alertas operativas en Render
  — **Implementado 2026-04-16**: Telegram bot con alertas de trade (open/close), errores de ciclo, heartbeat diario y comandos /help /status /pos /pnl /pause /resume.

## Hechos confirmados que cambian el backlog
- [x] el repo ya no depende de rutas absolutas Windows para correr
- [x] la config ya soporta base dir y overrides por entorno para despliegue cloud
- [x] el repo ya tiene [Dockerfile](/D:/binance_futures_bot/Dockerfile), [.dockerignore](/D:/binance_futures_bot/.dockerignore) y [render.yaml](/D:/binance_futures_bot/render.yaml)
- [x] el target cloud actual definido es Render worker con disco persistente
- [x] el repo ya fue subido a GitHub, asi que el bloqueo "falta repo remoto" ya no aplica
- [x] el paper runtime ya no depende de una funcion mixta de snapshot y refresh; consume un servicio de market data explicito
- [x] el refresh actual ya puede cubrir `15m`, `1h` y `4h` si la config operativa los declara
- [x] el refresh actual usa REST y solo velas cerradas; no resuelve latencia intrabar ni estado de cuenta
- [x] el servicio actual ya evita refresh redundante antes del proximo cierre esperado de vela
- [x] el loop ahora puede dormir segun `next_poll_after_ms` en vez de iterar siempre por intervalo fijo
- [x] backtest y paper ya comparten bucket configurable de riesgo
- [x] backtest y paper ya comparten `sizing_engine` y `max_notional_pct` por simbolo
- [x] paper ya puede usar market data de produccion aunque el cliente Binance siga en testnet
- [x] paper ya puede aplicar el mismo gating `4h/1h` y restricciones por lado del research si la config lo habilita
- [x] paper ya hace replay candle-by-candle de velas perdidas para gestionar posiciones abiertas
- [x] `paper_state.json` ya se escribe de forma atomica y tiene test de roundtrip sin residuos temporales
- [x] paper runtime ya reporta `decision_counts` por ciclo (opened/no_candidate/policy/risk/sizing/etc.) para diagnosticar por que no abre trades
- [x] `execution.slippage` ya no es decorativo; backtest y paper aplican slippage adverso por simbolo
- [x] `ExitReason` ya usa un contrato unico entre `src/core/models.py` y `src/execution/execution_simulator.py`
- [x] `stop_buffer_atr_fraction` ya sale de config y no de un hardcode en el runner
- [x] backtest ya puede resolver `risk_pct` dinamicamente por score del setup
- [x] el backtest ya guarda snapshot de config y baseline consolidada por corrida
- [x] el backtest research actual ya usa `1h/4h` como gating y restricciones por lado/simbolo
- [x] ya existe baseline v2 recortada y diagnostico consolidado reproducible

## Deuda tecnica confirmada
- `live v0.1` ya existe en modo seguro, pero todavia sin routing de ordenes,
- score ya gobierna backtest y paper, pero todavia no live,
- la baseline v2 mejoro fuerte, pero sigue siendo fragil y heterogenea por simbolo,
- el deploy Render ya fue validado operativamente (2026-04-16), pero sin observabilidad ni alertas,
- la cobertura automatizada mejoro, pero todavia no cubre reconciliacion ni exchange live.

## Riesgos de la siguiente fase
- conectar websocket sin preservar trazabilidad y reproducibilidad,
- introducir cambios en sizing sin explicar impacto en exposicion,
- mezclar market data con account state sin una capa explicita,
- pasar a ordenes reales antes de cerrar reconciliacion, baseline y observabilidad.
