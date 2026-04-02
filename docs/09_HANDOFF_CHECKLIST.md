# 09 - Handoff Checklist

## Documentacion
- [x] [AGENTS.md](/D:/binance_futures_bot/AGENTS.md) revisado
- [x] [README.md](/D:/binance_futures_bot/README.md) presente y consistente con el enfoque actual
- [x] [01_SYSTEM_OVERVIEW.md](/D:/binance_futures_bot/docs/01_SYSTEM_OVERVIEW.md) actualizado
- [x] [02_TRADING_LOGIC.md](/D:/binance_futures_bot/docs/02_TRADING_LOGIC.md) actualizado
- [x] [03_BACKTEST_AND_METRICS.md](/D:/binance_futures_bot/docs/03_BACKTEST_AND_METRICS.md) actualizado
- [x] [04_SETUP_AND_ENV.md](/D:/binance_futures_bot/docs/04_SETUP_AND_ENV.md) actualizado
- [x] [05_TESTING_AND_VALIDATION.md](/D:/binance_futures_bot/docs/05_TESTING_AND_VALIDATION.md) actualizado
- [x] [06_RUNBOOK.md](/D:/binance_futures_bot/docs/06_RUNBOOK.md) actualizado
- [x] [07_OPEN_ITEMS.md](/D:/binance_futures_bot/docs/07_OPEN_ITEMS.md) actualizado
- [x] [08_CHANGELOG_AND_DECISIONS.md](/D:/binance_futures_bot/docs/08_CHANGELOG_AND_DECISIONS.md) actualizado
- [x] [10_RENDER_DEPLOY.md](/D:/binance_futures_bot/docs/10_RENDER_DEPLOY.md) actualizado

## Codigo y entorno
- [x] El repo corre al menos en backtest y paper mode
- [x] La config ya no depende de rutas absolutas Windows
- [x] Existe [.env.example](/D:/binance_futures_bot/.env.example)
- [x] No hay `secrets` versionados en la raiz auditada
- [x] Existe base cloud portable con [Dockerfile](/D:/binance_futures_bot/Dockerfile) y [render.yaml](/D:/binance_futures_bot/render.yaml)
- [x] Existe repo remoto para habilitar el deploy en Render
- [ ] El worker de Render fue aplicado y validado operativamente

## Validacion
- [x] La suite minima de tests pasa en `.venv`
- [x] CODEX puede entender arquitectura, entrypoints y modulos criticos sin pedir contexto basico
- [x] CODEX puede ejecutar pruebas simples y seguir la trazabilidad del runtime
- [x] CODEX puede identificar modulos criticos y deuda real
- [x] CODEX puede proponer cambios sin romper invariantes principales
- [ ] Existe baseline multi-simbolo fijada y reproducible
- [ ] Existe validacion real de lifecycle de ordenes en Binance

## Riesgos que siguen abiertos en handoff
- `live` sigue siendo un objetivo, no una capacidad terminada,
- el sizing no esta todavia alineado entre backtest y paper,
- contexto y score siguen fuera del flujo operativo dominante,
- Render esta preparado pero no verificado en produccion de paper.
