# Handoff del bot a CODEX

Este paquete deja el proyecto listo para que CODEX pueda entenderlo, modificarlo y verificarlo con menos ambiguedad.

## Que incluye
- `AGENTS.md`: reglas operativas para CODEX.
- `docs/01_SYSTEM_OVERVIEW.md`: vision general del sistema.
- `docs/02_TRADING_LOGIC.md`: logica de trading y flujo de decision.
- `docs/03_BACKTEST_AND_METRICS.md`: flujo de backtesting y validacion.
- `docs/04_SETUP_AND_ENV.md`: setup local y cloud, variables y dependencias.
- `docs/05_TESTING_AND_VALIDATION.md`: como validar cambios.
- `docs/06_RUNBOOK.md`: operacion diaria y troubleshooting.
- `docs/07_OPEN_ITEMS.md`: deuda tecnica, riesgos y tareas pendientes.
- `docs/08_CHANGELOG_AND_DECISIONS.md`: decisiones clave y cambios estructurales.
- `docs/09_HANDOFF_CHECKLIST.md`: checklist final para entregar el proyecto.
- `docs/10_RENDER_DEPLOY.md`: despliegue actual en Render.

## Proposito
El objetivo no es solo documentar que hace el bot, sino reducir ambiguedad operativa para que CODEX pueda:
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
- El target cloud actual es Render worker con disco persistente.
- `backtest` y `paper` ya comparten bucket de riesgo configurable y `sizing_engine`.
- `paper` ya puede usar market data de produccion aunque `binance.use_testnet` siga activo para el path de ordenes.
- `paper` ya puede aplicar el mismo gating research `4h/1h`, restricciones por lado del `core` y score dinamico opcional si la config lo habilita.
- El `core` de research actual en [config/base.yaml](/D:/binance_futures_bot/config/base.yaml) ya esta recortado a `BTCUSDT` y `ETHUSDT`, ambos `SHORT` only.
- El `core` ya soporta `filters.by_symbol`; hoy `BTCUSDT` usa un rango mas estricto que `ETHUSDT`.
- El `core` ya soporta `trade_management.by_symbol`; hoy `ETHUSDT` usa `max_bars_in_trade = 32` y `BTCUSDT` usa `16`.
- El backtest research ya puede resolver riesgo por score del setup cuando `strategy.dynamic_risk_by_score.enabled=true`, pero la politica vigente preserva el `risk_pct` base por simbolo como piso y hoy opera mas como gating economico que como recorte agresivo de sizing.
- El backtest ya soporta un segundo setup `PULLBACK` de forma experimental, incluyendo un filtro especifico `body/ATR` para la vela de reanudacion; aun asi el `core` oficial sigue corriendo solo `BREAKOUT` porque la muestra util de `PULLBACK` sigue siendo demasiado chica para promoverlo.
- El `core` ya usa `max_notional_pct = 0.80` para `BTCUSDT` y `ETHUSDT`.
- La baseline oficial actual del `core` esta en [baseline_summary.json](/D:/binance_futures_bot/outputs/backtests/baseline_summary.json): `63 trades`, `+524.7745 USDT`, con `backtest_risk_bucket=strong` (`risk_pct base = 0.0085`), `ETHUSDT max_notional_pct = 0.90`, override research `ETHUSDT risk_pct = 0.0100`, `score_thresholds.min_trade = 75` y `strategy.dynamic_risk_by_score.preserve_symbol_base_risk = true`.
- La comparacion economicamente valida del score dinamico ya no es contra la baseline vieja pre-slippage. En el engine actual, la politica corregida de score mejora al fixed-risk actual, pero el capital sigue subutilizado en terminos temporales.
- `XRPUSDT` quedo separado como laboratorio en [config/research.xrp_long.yaml](/D:/binance_futures_bot/config/research.xrp_long.yaml).
- `ETHUSDT` tiene ahora un laboratorio separado para `BREAKOUT + PULLBACK` en [config/research.eth_pullback.yaml](/D:/binance_futures_bot/config/research.eth_pullback.yaml); sigue siendo research, no baseline oficial.

## Recomendacion de uso
1. Abrir el repo en CODEX.
2. Hacer que CODEX lea primero `AGENTS.md`.
3. Pedirle que resuma arquitectura segun [01_SYSTEM_OVERVIEW.md](/D:/binance_futures_bot/docs/01_SYSTEM_OVERVIEW.md).
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

## Live seguro v0.1
`live` ya tiene runtime seguro para reconciliacion minima de cuenta, con ejecucion real bloqueada por defecto.

```bash
# modo seguro (no envia ordenes)
python run_live.py --once

# con config dedicada
set BOT_CONFIG_PATH=config/live.safe.yaml
python run_live.py
```

Variables relevantes:
- `LIVE_ENABLED` -> si no se define o es `false`, bloquea ejecucion de ordenes.
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` -> requeridas para reconciliacion live.

## Render
El repo ya puede ser consumido por Render via [render.yaml](/D:/binance_futures_bot/render.yaml). Lo pendiente no es el remoto, sino aplicar y validar el worker en un entorno real.

## Estado de esta documentacion
La documentacion de `docs/` fue sincronizada con el estado actual del repo. El siguiente trabajo ya no es documentar mas, sino cerrar deuda operativa antes de live.
