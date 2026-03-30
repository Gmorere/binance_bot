# 10 - Render Deploy

## Hecho confirmado
El repo ya tiene una base de despliegue para Render:
- [render.yaml](/D:/binance_futures_bot/render.yaml)
- [Dockerfile](/D:/binance_futures_bot/Dockerfile)
- [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml)

## Lo que despliega hoy
- Un `worker` de Render, no un `web service`.
- Runtime Docker.
- Un solo proceso (`numInstances: 1`).
- Disco persistente montado en `/app/runtime`.
- Paper mode sobre Binance Futures con refresh REST de market data.

## Por que worker y no web
Este bot hoy no expone HTTP ni necesita puerto publico. Forzarlo a `web` seria arquitectura falsa.

## Archivos clave
- Blueprint: [render.yaml](/D:/binance_futures_bot/render.yaml)
- Config de Render: [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml)
- Entry point del worker: [run_paper.py](/D:/binance_futures_bot/run_paper.py)

## Variables usadas en Render
El Blueprint fija estas variables:
- `BOT_CONFIG_PATH=/app/config/render.paper.yaml`
- `BOT_BASE_DIR=/app`
- `BOT_RAW_DATA_PATH=/app/runtime/data/raw`
- `BOT_PROCESSED_DATA_PATH=/app/runtime/data/processed`
- `BOT_OUTPUTS_PATH=/app/runtime/outputs`
- `PYTHONUNBUFFERED=1`

## Persistencia
El estado y los datasets del worker deben vivir en el disco persistente:
- raw data: `/app/runtime/data/raw`
- processed data: `/app/runtime/data/processed`
- outputs: `/app/runtime/outputs`

Sin disco persistente, Render perderia estos archivos en cada restart/redeploy.

## Limitacion actual que bloquea deploy real
Este workspace no es un repo git y no tiene remoto.

Render Blueprints necesitan un repositorio Git accesible por Render. Entonces hoy se puede preparar el Blueprint, pero no aplicarlo desde Dashboard con este workspace tal como esta.

## Paso minimo para desplegar de verdad
1. Inicializar git si todavia no existe.
2. Crear un repo en GitHub/GitLab/Bitbucket.
3. Subir este proyecto con `render.yaml` ya incluido.
4. En Render, crear el Blueprint desde ese repo.
5. Confirmar que el worker quede en plan pago con disco persistente.

## Post-deploy minimo
1. Ver logs del worker.
2. Confirmar que crea o reutiliza `/app/runtime/...`.
3. Confirmar que entra en `runtime.mode=paper`.
4. Confirmar que no falla por falta de data ni permisos de escritura.
5. Confirmar que `binance.use_testnet=true` siga activo en la primera etapa.

## Riesgos pendientes
- Sigue siendo paper mode, no live.
- No hay healthcheck HTTP porque no es un web service.
- No hay alerting ni observabilidad fuera de logs de Render.
- No hay websocket ni reconciliacion de ordenes.
