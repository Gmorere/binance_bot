# Handoff del bot a CODEX

Este paquete deja el proyecto listo para que CODEX pueda entenderlo, modificarlo y verificarlo con menos ambiguedad.

## Que incluye
- `AGENTS.md`: reglas operativas para CODEX.
- `docs/01_SYSTEM_OVERVIEW.md`: vision general del sistema.
- `docs/02_TRADING_LOGIC.md`: logica de trading y flujo de decision.
- `docs/03_BACKTEST_AND_METRICS.md`: flujo de backtesting y validacion.
- `docs/04_SETUP_AND_ENV.md`: setup local/cloud, variables y dependencias.
- `docs/05_TESTING_AND_VALIDATION.md`: como validar cambios.
- `docs/06_RUNBOOK.md`: operacion diaria y troubleshooting.
- `docs/07_OPEN_ITEMS.md`: deudas tecnicas, riesgos y tareas pendientes.
- `docs/08_CHANGELOG_AND_DECISIONS.md`: decisiones clave y cambios estructurales.
- `docs/09_HANDOFF_CHECKLIST.md`: checklist final para entregar el proyecto.
- `docs/10_RENDER_DEPLOY.md`: despliegue actual en Render.

## Proposito
El objetivo no es solo documentar que hace el bot, sino **reducir ambiguedad operativa** para que un agente como CODEX pueda:
1. entender la arquitectura,
2. ubicar rapido los modulos sensibles,
3. evitar romper la logica de riesgo,
4. ejecutar pruebas utiles,
5. proponer cambios con contexto.

## Estado actual relevante
- El repo ya no depende de rutas absolutas Windows para correr.
- `config/base.yaml` usa paths relativos portables.
- Se puede sobreescribir config y rutas por variables de entorno para despliegue cloud.
- El repo incluye `Dockerfile`, `.dockerignore` y `render.yaml`.
- El target cloud actual asumido es Render worker con disco persistente.

## Recomendacion de uso
1. Abrir el repo en CODEX.
2. Hacer que CODEX lea primero `AGENTS.md`.
3. Pedirle que resuma arquitectura segun `docs/01_SYSTEM_OVERVIEW.md`.
4. Recien despues asignarle tareas de cambios o refactor.

## Arranque rapido cloud
```bash
# build

docker build -t binance-futures-bot .

# paper mode

docker run --rm \
  -e BOT_CONFIG_PATH=/app/config/base.yaml \
  -e BOT_BASE_DIR=/app \
  binance-futures-bot
```

## Limitacion actual para Render
Este workspace no es un repo git. El Blueprint ya existe, pero Render no puede aplicarlo desde Dashboard hasta que el proyecto viva en GitHub, GitLab o Bitbucket.

## Estado de esta documentacion
Esta base fue preparada con la informacion disponible del proyecto en conversacion. Donde falten datos especificos del repo real, quedo indicado como **[COMPLETAR]** para cerrarlo antes del traspaso final.
