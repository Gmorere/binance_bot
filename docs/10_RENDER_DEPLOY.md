# 10 - Render Deploy

## Estado real
El repo ya tiene base de despliegue para Render y ya no esta bloqueado por falta de remoto.

Artefactos relevantes:
- [render.yaml](/D:/binance_futures_bot/render.yaml)
- [Dockerfile](/D:/binance_futures_bot/Dockerfile)
- [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml)

Lo que sigue pendiente no es preparar el repo, sino aplicar y validar el worker en Render.

## Base de contenedor actual
- El deploy cloud usa [Dockerfile](/D:/binance_futures_bot/Dockerfile) con `python:3.12-slim`.
- No conviene usar `python:3.14-slim` hoy para este repo en Render porque `pandas==2.2.3` y `numpy==2.1.3` pueden caer a build desde fuente y romper o volver demasiado lento el deploy.

## Que despliega hoy
- un `worker` de Render, no un `web service`,
- runtime Docker,
- un solo proceso (`numInstances: 1`),
- disco persistente montado en `/app/runtime`,
- `paper mode` sobre Binance USD-M futures con refresh REST de market data.
- feed de market data en produccion (`binance.use_testnet_market_data: false`) aunque el path de ordenes siga en testnet.
- gating research `4h/1h`, restricciones por lado y score dinamico alineados con el `core` actual.

## Por que worker y no web
Este bot no expone HTTP ni necesita puerto publico. Forzarlo a `web` seria arquitectura falsa.

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

Sin disco persistente, Render perderia estos archivos en cada restart o redeploy.

## Flujo minimo de deploy
1. Tener el repo accesible desde GitHub para Render.
2. Crear el Blueprint desde [render.yaml](/D:/binance_futures_bot/render.yaml).
3. Confirmar que el servicio quede como `worker`.
4. Confirmar disco persistente montado en `/app/runtime`.
5. Confirmar que use [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
6. Mantener `binance.use_testnet: true` en la primera etapa operativa para account/orders.
7. Mantener `binance.use_testnet_market_data: false` para que el paper use velas reales de produccion.

## Post-deploy minimo
1. Ver logs del worker.
2. Confirmar que crea o reutiliza `/app/runtime/...`.
3. Confirmar que entra en `runtime.mode=paper`.
4. Confirmar que no falla por falta de data ni por permisos de escritura.
5. Confirmar que el refresh REST efectivamente genera o actualiza CSV `15m`.

## Riesgos pendientes
- sigue siendo paper mode, no live,
- no hay healthcheck HTTP porque no es un web service,
- no hay alerting ni observabilidad fuera de logs de Render,
- no hay websocket ni reconciliacion de ordenes,
- el worker todavia necesita validacion operativa real en Render.

## Criterio de exito de esta fase
Esta fase queda realmente cerrada solo cuando el worker:
- builda sin errores,
- inicia `run_paper.py`,
- escribe en `/app/runtime`,
- mantiene estado entre reinicios,
- y no se cae por falta de datos o de permisos.
