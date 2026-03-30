# 08 - Changelog and Decisions

## Decisiones de arquitectura que deben mantenerse
1. Separar senal, order plan, ejecucion y metricas.
2. Mantener calculo explicito de fees.
3. Mantener soporte para parciales TP1/TP2.
4. Guardar outputs de backtest para auditoria.
5. No mezclar market data de runtime con account state sin una capa explicita.
6. No volver a introducir rutas absolutas de entorno local como fuente de verdad.
7. Para cloud, tratar el bot como `worker`, no como `web service`, hasta que realmente exponga HTTP util.

## Decisiones auditadas sobre el estado actual
1. El runtime activo hoy sigue siendo paper/backtest, no Binance live.
2. Los modulos de contexto, score y parte del riesgo existen pero todavia no gobiernan el flujo real dominante.
3. La documentacion debe describir comportamiento implementado y separar claramente roadmap de runtime.
4. Antes de tocar ordenes reales, el repo necesita market data mas robusto, reconciliacion y baseline reproducible.
5. El loop operativo debe depender de un contrato de market data, no del mecanismo concreto de refresh.
6. La base cloud debe ser proveedor-agnostica hasta que haya una decision operativa concreta.
7. El despliegue cloud concreto elegido hoy es Render worker con disco persistente.

## Registro de cambios
### 2026-03-30
- Cambio: sincronizacion de documentacion con la implementacion real auditada.
- Motivo: la doc describia un sistema mas completo que el runtime efectivo.
- Impacto esperado: menos ambiguedad antes de refactors de riesgo y estrategia.
- Validacion realizada: contraste manual doc vs codigo y smoke run parcial con `.venv`.
- Riesgo residual: la estrategia sigue siendo provisional y el motor de riesgo aun no esta integrado de punta a punta.

### 2026-03-30
- Cambio: `TradeCandidate` paso a ser la fuente unica del setup operable para backtest y paper runtime.
- Motivo: evitar duplicacion entre research y automatizacion futura en Binance.
- Impacto esperado: menor divergencia entre backtest y runtime automatizado.
- Validacion realizada: suite de tests ampliada con scanner y path de signal builder.
- Riesgo residual: todavia no existe lifecycle real de ordenes ni reconciliacion con exchange.

### 2026-03-30
- Cambio: implementacion de paper mode local con estado persistente, sizing real y gestion de parciales/stop sobre vela cerrada.
- Motivo: crear una fase intermedia entre backtest y Binance live real.
- Impacto esperado: validar contratos operativos antes de conectar ordenes reales.
- Validacion realizada: tests de apertura y gestion TP1/TP2 en `paper_engine` y loop continuo en `paper_runtime`.
- Riesgo residual: sigue faltando account sync, websocket y lifecycle live.

### 2026-03-30
- Cambio: refresh incremental de klines `15m` desde Binance REST antes de cada snapshot de paper mode, con merge por timestamp y descarte de vela abierta.
- Motivo: eliminar la dependencia de recarga manual de CSV para el runtime continuo.
- Impacto esperado: paper mode mas cercano a una operacion automatizada sin mezclar todavia market data con ordenes reales.
- Validacion realizada: tests unitarios del updater, tests del runtime de market data y suite completa de `unittest`.
- Riesgo residual: sigue siendo polling REST, no websocket; `1h/4h` siguen fuera del runtime porque contexto/score todavia no gobiernan aperturas reales.

### 2026-03-30
- Cambio: introduccion de `PollingMarketDataService` como contrato explicito entre el loop operativo y la adquisicion de market data.
- Motivo: evitar que `paper_runtime` dependa de funciones mixtas que cargan datos y refrescan CSV a la vez.
- Impacto esperado: facilitar el reemplazo futuro de REST polling por websocket sin reescribir el loop de paper.
- Validacion realizada: tests del servicio con `poll()` y tests del loop usando un servicio fake.
- Riesgo residual: el contrato ya esta desacoplado, pero la implementacion concreta sigue siendo REST sobre CSV persistido.

### 2026-03-30
- Cambio: el servicio de polling ahora agenda el siguiente refresh segun cierre teorico de vela mas una gracia configurable y devuelve cache si el refresh aun no corresponde.
- Motivo: evitar llamadas REST redundantes entre cierres de vela y acercar el runtime a un comportamiento live mas disciplinado.
- Impacto esperado: menos ruido operativo, menos polling inutil y trazabilidad explicita via logs `data_refresh_skip` y `data_refresh_schedule`.
- Validacion realizada: tests unitarios que verifican skip antes del siguiente close y refresh al vencer la ventana.
- Riesgo residual: sigue siendo una heuristica temporal; no reemplaza confirmacion por websocket ni sincronizacion con reloj del exchange.

### 2026-03-30
- Cambio: `paper_runtime` ahora duerme segun `next_poll_after_ms` reportado por el servicio de market data en vez de depender siempre de `poll_interval_seconds`.
- Motivo: evitar que el loop itere a ciegas cuando el servicio ya conoce el proximo momento util de wake-up.
- Impacto esperado: menos ciclos inutiles y un runtime mas alineado con cierres de vela reales.
- Validacion realizada: tests del scheduler, tests del loop con servicio fake y suite completa de `unittest`.
- Riesgo residual: si el servicio agenda tarde por datos viejos o clock skew, el loop tambien va a dormir tarde; eso todavia no se corrige con senales del exchange.

### 2026-03-30
- Cambio: base cloud proveedor-agnostica con config portable, overrides por entorno, entrypoints sin rutas Windows y contenedor Docker.
- Motivo: dejar de depender del filesystem local para ejecutar backtest, paper mode y bootstrap de datos.
- Impacto esperado: despliegue reproducible en VPS o plataforma cloud sin reescribir paths a mano.
- Validacion realizada: tests nuevos de `config_loader`, suite completa de `unittest` y smoke de carga de `config/base.yaml` con resolucion de paths.
- Riesgo residual: sigue faltando un despliegue cloud concreto con observabilidad, volumen persistente administrado y healthchecks.

### 2026-03-30
- Cambio: se agrego Blueprint de Render y config especifica `render.paper.yaml` para desplegar un worker Docker con disco persistente.
- Motivo: concretar un primer destino cloud operativo sobre el proveedor elegido sin mezclar todavia live trading ni servicios HTTP inventados.
- Impacto esperado: camino claro para levantar paper mode 24/7 en Render una vez que el repo viva en GitHub/GitLab/Bitbucket.
- Validacion realizada: smoke de parseo de `render.yaml`, smoke de carga de `config/render.paper.yaml` y suite completa de `unittest`.
- Riesgo residual: no se pudo aplicar el Blueprint porque este workspace no es un repo git ni tiene remoto; ademas no se valido con Render CLI ni Dashboard desde este entorno.

## Baseline auditada disponible
- simbolo: `BTCUSDT`
- timeframe operativo: `15m`
- periodo observado en outputs: `2025-01` a `2026-03`
- capital inicial: `10000 USDT`
- numero de trades: `97`
- pnl neto: `-2887.1875 USDT`
- max drawdown: `-3704.2785 USDT`
- profit factor: `0.5621`
- origen: `outputs/backtests/BTCUSDT_summary.json`
- commit hash: no disponible en este workspace
