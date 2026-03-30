# 07 - Open Items

## Abiertos despues de la auditoria
- [ ] reemplazar `PollingMarketDataService` por una fuente mas cercana a tiempo real con websocket o polling dedicado
- [ ] separar claramente market data polling vs user/account sync
- [ ] definir reconciliacion de ordenes/posiciones ante respuestas 503 y estado desconocido
- [ ] agregar tests de persistencia de `paper_state.json`
- [ ] integrar `risk_engine` al flujo real del backtest
- [ ] integrar `sizing_engine` y aplicar `max_notional_pct` sin desalinear paper/backtest
- [ ] integrar contexto `4h/1h` y score al runtime o removerlos del roadmap inmediato
- [ ] decidir si el sistema sera solo research/backtest o tambien paper/live
- [ ] definir modelado real de slippage por simbolo
- [ ] definir metricas de portafolio y no solo por simbolo
- [ ] convertir `max_drawdown` a una convencion unica y explicita
- [ ] guardar snapshot de config por corrida
- [ ] generar baseline multi-simbolo reproducible
- [ ] subir el repo a GitHub/GitLab/Bitbucket para que Render pueda aplicar el Blueprint
- [ ] agregar observabilidad y alertas operativas en Render

## Hechos confirmados que cambian el backlog
- [x] el repo ya no depende de rutas absolutas Windows para correr
- [x] la config ya soporta base dir y overrides por entorno para despliegue cloud
- [x] el repo ya tiene `Dockerfile`, `.dockerignore` y `render.yaml`
- [x] el target cloud actual definido es Render worker con disco persistente
- [x] el paper runtime ya no depende de una funcion mixta de snapshot/refresh; consume un servicio de market data explicito
- [x] el refresh actual opera solo sobre `15m` porque el runtime operable hoy no consume `1h/4h`
- [x] el refresh actual usa REST y solo velas cerradas; no resuelve latencia intrabar ni estado de cuenta
- [x] el servicio actual ya evita refreshs redundantes antes del proximo cierre esperado de vela
- [x] el loop ahora puede dormir segun `next_poll_after_ms` en vez de iterar siempre por intervalo fijo

## Deuda tecnica confirmada
- tests historicamente inexistentes o insuficientes,
- modulos de riesgo y contexto presentes pero no conectados al flujo dominante,
- baseline parcial solo para `BTCUSDT`,
- el deploy Render todavia no es aplicable desde este workspace porque falta repo git remoto.

## Riesgos de la siguiente fase
- conectar websocket sin preservar trazabilidad y reproducibilidad,
- introducir cambios en sizing sin explicar impacto en exposicion,
- mezclar market data con account state sin una capa explicita,
- mover a ordenes reales antes de cerrar reconciliacion y baseline.
