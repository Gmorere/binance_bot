# 08 - Changelog and Decisions

## Decisiones de arquitectura que deben mantenerse
1. Separar senal, order plan, ejecucion y metricas.
2. Mantener calculo explicito de fees.
3. Mantener soporte para parciales TP1 y TP2.
4. Guardar outputs de backtest para auditoria.
5. No mezclar market data de runtime con account state sin una capa explicita.
6. No volver a introducir rutas absolutas de entorno local como fuente de verdad.
7. Para cloud, tratar el bot como `worker`, no como `web service`, hasta que realmente exponga HTTP util.

## Decisiones auditadas sobre el estado actual
1. El runtime operativo hoy sigue siendo `backtest` y `paper`, no Binance live.
2. `TradeCandidate` es la fuente unica del setup operable.
3. La documentacion debe describir comportamiento implementado y separar con claridad roadmap de runtime real.
4. Antes de tocar ordenes reales, el repo necesita market data mas robusto, reconciliacion y baseline reproducible.
5. El loop operativo debe depender de un contrato de market data, no del mecanismo concreto de refresh.
6. La base cloud debe seguir siendo portable aunque el destino elegido hoy sea Render.
7. El deploy cloud concreto elegido hoy es Render worker con disco persistente.

## Registro de cambios
### 2026-04-13
- Cambio: `paper_engine` deja de hardcodear ventana de consolidación para breakout (`min_candles`/`max_candles`) y pasa a leerla desde `filters` con soporte `by_symbol`; se aplicó tuning en [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml).
- Motivo: el diagnóstico en logs seguía mostrando `BREAKOUT=No se detectó consolidación válida` incluso después de ajustar otros parámetros, porque la ventana estaba fija en código (`6-12`) y no seguía config.
- Impacto esperado: habilitar tuning real de estructura de consolidación en paper sin tocar lógica de riesgo/sizing.
- Validacion realizada: test nuevo en [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py) verificando paso de `min_candles/max_candles` por símbolo.
- Riesgo residual: abrir demasiado la ventana puede aumentar ruido y falsos breakouts; requiere seguimiento con `opened` y calidad de cierres.

### 2026-04-13
- Cambio: tuning de detección estructural en [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml) tras diagnóstico de `no_candidate`: `max_consolidation_range_atr_multiple` sube (global `1.4`, BTC `1.5`, ETH `1.8`) y se agrega bloque `pullback` más permisivo (lookback/retrace/impulse).
- Motivo: los logs mostraron bloqueo explícito en etapa de setup (`BREAKOUT=No se detectó consolidación válida` y `PULLBACK=No se detecto estructura de pullback valida`).
- Impacto esperado: aumentar candidatos evaluables por ciclo sin tocar por ahora límites de riesgo/sizing/capital.
- Validacion realizada: cambio acotado de configuración operativa paper con diagnóstico basado en logs.
- Riesgo residual: al relajar estructura puede entrar ruido; hay que monitorear si suben `opened` pero empeora la calidad de cierres (`STOP` / neto por trade).

### 2026-04-13
- Cambio: habilitado `PULLBACK` solo para `ETHUSDT` en [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml) dentro de `strategy.allowed_setups_by_symbol`.
- Motivo: con `BTC/ETH` ambos en `no_candidate`, la frecuencia real quedo por debajo del minimo util para validar mejoras economicas.
- Impacto esperado: aumentar flujo de candidatos en paper sin alterar `BTCUSDT` ni los limites de riesgo/sizing ya vigentes.
- Validacion realizada: ajuste de config cloud reversible y acotado al entorno paper.
- Riesgo residual: mas frecuencia puede traer setups de menor calidad; se debe monitorear `decisions`, `opened`, cierres por `STOP` y neto por trade.

### 2026-04-13
- Cambio: tuning operativo de paper en [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml) para aumentar frecuencia de candidatos: `score_thresholds.min_trade` baja de `75` a `70` y `filters.max_trigger_candle_atr_multiple` sube de `1.6` a `1.8`.
- Motivo: logs reales del worker mostraron `decisions={'no_candidate': 2}` de forma sostenida en BTC/ETH.
- Impacto esperado: convertir parte del `no_candidate` en candidatos evaluables sin tocar todavia limites de capital, leverage ni riesgo agregado.
- Validacion realizada: ajuste acotado de config deployable en paper cloud, sin cambios de código.
- Riesgo residual: puede subir frecuencia a costa de calidad de setup; requiere monitorear `opened`, `strategy_policy`, `dynamic_risk`, `sizing` y resultado neto por trade.

### 2026-04-13
- Cambio: hardening de `PollingMarketDataService` para errores de refresh REST (`418` y afines): ahora loguea `data_refresh_error`, mantiene snapshot cacheado/local y aplica `data_refresh_error_backoff` en vez de caerse.
- Motivo: en Render el worker podia quedar en crash-loop por respuestas `418` de Binance Futures aun cuando ya habia dataset local util.
- Impacto esperado: continuidad operativa del paper worker con degradacion controlada (datos stale temporales) en vez de interrupcion total.
- Validacion realizada: tests nuevos en [test_market_data_runtime.py](/D:/binance_futures_bot/tests/test_market_data_runtime.py) para `continue on refresh error` y `error backoff`, mas defaults de config en [test_binance_client.py](/D:/binance_futures_bot/tests/test_binance_client.py).
- Riesgo residual: si el bloqueo de Binance persiste por mucho tiempo, el worker sigue vivo pero opera con datos sin actualizar hasta que se recupere el feed.

### 2026-04-13
- Cambio: `paper_engine` ahora clasifica el resultado por simbolo en cada ciclo (`opened`, `no_candidate`, `strategy_policy`, `dynamic_risk`, `portfolio_limits`, `sizing`, etc.) y `paper_runtime` lo expone en logs como `decisions={...}`.
- Motivo: el worker en Render podia quedar "vivo pero sin trades" sin explicar causa raiz operativa; faltaba observabilidad directa para separar ausencia de setup vs bloqueos de politica/riesgo/sizing.
- Impacto esperado: diagnostico mas rapido de frecuencia real y uso de capital, con evidencia accionable para tuning de estrategia y limites.
- Validacion realizada: tests actualizados en [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py) y [test_paper_runtime.py](/D:/binance_futures_bot/tests/test_paper_runtime.py), incluyendo casos `opened`, `strategy_policy` y `no_candidate`.
- Riesgo residual: esto mejora observabilidad, pero no implementa alertas proactivas ni reconciliacion live.

### 2026-04-02
- Cambio: cambio de region por default del worker Render de `oregon` a `frankfurt` en [render.yaml](/D:/binance_futures_bot/render.yaml).
- Motivo: el deploy ya buildaba y arrancaba, pero el runtime en `Oregon, USA` recibia `451` desde `https://fapi.binance.com/fapi/v1/klines`; el problema ya no era el bot sino el egress de una region US contra Binance Futures.
- Impacto esperado: evitar el bloqueo geografico/regulatorio en paper mode con market data real de Binance Futures.
- Validacion realizada: log real del worker en Render mostrando `451 Client Error` contra `/fapi/v1/klines` despues de deploy correcto en `Oregon`.
- Riesgo residual: Render no permite cambiar la region de un servicio existente; para aplicar este fix hay que crear un worker nuevo en `Frankfurt` o recrear el actual.

### 2026-04-02
- Cambio: ajuste del contenedor cloud a `python:3.12-slim` y restauracion del disco persistente en [render.yaml](/D:/binance_futures_bot/render.yaml) despues de aislar la causa real del deploy fallido.
- Motivo: el fallo en Render no venia del disco sino del build Docker; `pandas==2.2.3` sobre `python:3.14-slim` estaba cayendo a build desde fuente en vez de wheel precompilada.
- Impacto esperado: builds mas estables y rapidos en Render sin perder persistencia operativa del worker.
- Validacion realizada: inspeccion del log real del build fallido en Render, que mostro descarga de `pandas-2.2.3.tar.gz` y arranque de `Installing build dependencies` en vez de wheel binaria.
- Riesgo residual: falta volver a disparar el deploy en Render para confirmar build y arranque end-to-end del worker.

### 2026-04-02
- Cambio: `paper_engine` ahora puede consumir `strategy.dynamic_risk_by_score` con la misma policy base del backtest, incluyendo bloqueo por score bajo y preservacion del `risk_pct` base por simbolo como piso.
- Motivo: seguia existiendo una brecha innecesaria entre research y runtime paper; el score ya decidia economia en backtest pero paper seguia operando con bucket fijo aunque la estrategia y el gating ya estuvieran alineados.
- Impacto esperado: menor divergencia entre backtest y paper en apertura/sizing del `core`, con trazabilidad del `risk_bucket` resuelto dentro de la posicion paper y logs de skip por score cuando corresponde.
- Validacion realizada: integracion en [paper_engine.py](/D:/binance_futures_bot/src/live/paper_engine.py), helper comun en [runtime_policy.py](/D:/binance_futures_bot/src/strategy/runtime_policy.py), ajuste de [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml) y dos tests nuevos en [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py); suite completa con `74 tests` OK.
- Riesgo residual: live sigue sin consumir score; paper continua entrando al `close` de la vela de senal y sigue sin reconciliacion con exchange real.

### 2026-04-02
- Cambio: correccion de la politica de `dynamic_risk_by_score` en backtest para preservar el `risk_pct` base por simbolo como piso y subir `score_thresholds.min_trade` a `75`.
- Motivo: la primera integracion del score reducia demasiado el sizing medio y empeoraba la economia del `core`; ademas, la comparacion contra la baseline vieja estaba contaminada por cambios posteriores de slippage y modelado.
- Impacto esperado: el score deja de degradar el tuning ya validado por simbolo y pasa a funcionar principalmente como gating economico, manteniendo trazabilidad del bucket y del setup.
- Validacion realizada: smoke real por `BTCUSDT` y `ETHUSDT`, reconstruccion de baseline consolidada en [baseline_summary.json](/D:/binance_futures_bot/outputs/backtests/baseline_summary.json), diagnostico actualizado en [baseline_diagnostic.md](/D:/binance_futures_bot/outputs/backtests/baseline_diagnostic.md) y suite completa con `72 tests` OK.
- Riesgo residual: paper/live todavia no consumen esta politica; en `ETHUSDT` todos los trades siguen preservando el riesgo base, asi que el score hoy aporta mas como filtro que como verdadero reescalado de exposicion.

### 2026-03-30
- Cambio: sincronizacion inicial de documentacion con la implementacion real auditada.
- Motivo: la documentacion describia un sistema mas completo que el runtime efectivo.
- Impacto esperado: menos ambiguedad antes de refactors de riesgo y estrategia.
- Validacion realizada: contraste manual doc vs codigo y smoke run parcial con `.venv`.
- Riesgo residual: la estrategia seguia siendo provisional y el motor de riesgo aun no estaba integrado de punta a punta.

### 2026-03-30
- Cambio: `TradeCandidate` paso a ser la fuente unica del setup operable para backtest y paper runtime.
- Motivo: evitar duplicacion entre research y automatizacion futura en Binance.
- Impacto esperado: menor divergencia entre backtest y runtime automatizado.
- Validacion realizada: suite de tests ampliada con scanner y path de signal builder.
- Riesgo residual: todavia no existe lifecycle real de ordenes ni reconciliacion con exchange.

### 2026-03-30
- Cambio: implementacion de paper mode local con estado persistente, sizing real y gestion de parciales y stop sobre vela cerrada.
- Motivo: crear una fase intermedia entre backtest y Binance live real.
- Impacto esperado: validar contratos operativos antes de conectar ordenes reales.
- Validacion realizada: tests de apertura y gestion TP1 y TP2 en `paper_engine` y loop continuo en `paper_runtime`.
- Riesgo residual: sigue faltando account sync, websocket y lifecycle live.

### 2026-03-30
- Cambio: refresh incremental de klines `15m` desde Binance REST antes de cada snapshot de paper mode, con merge por timestamp y descarte de vela abierta.
- Motivo: eliminar la dependencia de recarga manual de CSV para el runtime continuo.
- Impacto esperado: paper mode mas cercano a una operacion automatizada sin mezclar todavia market data con ordenes reales.
- Validacion realizada: tests unitarios del updater, tests del runtime de market data y suite completa de `unittest`.
- Riesgo residual: sigue siendo polling REST, no websocket; `1h/4h` siguen fuera del runtime porque contexto y score todavia no gobiernan aperturas reales.

### 2026-03-30
- Cambio: introduccion de `PollingMarketDataService` como contrato explicito entre el loop operativo y la adquisicion de market data.
- Motivo: evitar que `paper_runtime` dependa de funciones mixtas que cargan datos y refrescan CSV a la vez.
- Impacto esperado: facilitar el reemplazo futuro de REST polling por websocket sin reescribir el loop de paper.
- Validacion realizada: tests del servicio con `poll()` y tests del loop usando un servicio fake.
- Riesgo residual: el contrato ya esta desacoplado, pero la implementacion concreta sigue siendo REST sobre CSV persistido.

### 2026-03-30
- Cambio: el servicio de polling ahora agenda el siguiente refresh segun cierre teorico de vela mas una gracia configurable y devuelve cache si el refresh aun no corresponde.
- Motivo: evitar llamadas REST redundantes entre cierres de vela y acercar el runtime a un comportamiento mas disciplinado.
- Impacto esperado: menos polling inutil y trazabilidad explicita via logs `data_refresh_skip` y `data_refresh_schedule`.
- Validacion realizada: tests unitarios que verifican skip antes del siguiente close y refresh al vencer la ventana.
- Riesgo residual: sigue siendo una heuristica temporal; no reemplaza confirmacion por websocket ni sincronizacion con reloj del exchange.

### 2026-03-30
- Cambio: `paper_runtime` ahora duerme segun `next_poll_after_ms` reportado por el servicio de market data en vez de depender siempre de `poll_interval_seconds`.
- Motivo: evitar que el loop itere a ciegas cuando el servicio ya conoce el proximo momento util de wake-up.
- Impacto esperado: menos ciclos inutiles y un runtime mas alineado con cierres de vela.
- Validacion realizada: tests del scheduler, tests del loop con servicio fake y suite completa de `unittest`.
- Riesgo residual: si el servicio agenda tarde por datos viejos o `clock skew`, el loop tambien va a dormir tarde.

### 2026-03-30
- Cambio: base cloud portable con config por entorno, entrypoints sin rutas Windows y contenedor Docker.
- Motivo: dejar de depender del filesystem local para ejecutar backtest, paper mode y bootstrap de datos.
- Impacto esperado: despliegue reproducible en VPS o plataforma cloud sin reescribir paths a mano.
- Validacion realizada: tests de `config_loader`, suite completa de `unittest` y smoke de carga de `config/base.yaml` con resolucion de paths.
- Riesgo residual: sigue faltando un despliegue cloud concreto con observabilidad, volumen persistente administrado y validacion operativa.

### 2026-03-30
- Cambio: se agrego Blueprint de Render y config especifica `render.paper.yaml` para desplegar un worker Docker con disco persistente.
- Motivo: concretar un primer destino cloud operativo sin mezclar todavia live trading ni servicios HTTP inventados.
- Impacto esperado: camino claro para levantar paper mode 24/7 en Render.
- Validacion realizada: smoke de parseo de [render.yaml](/D:/binance_futures_bot/render.yaml), smoke de carga de [config/render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml) y suite completa de `unittest`.
- Riesgo residual: el blueprint esta preparado, pero el servicio todavia necesita validacion operativa real en Render.

### 2026-04-01
- Cambio: actualizacion integral de `docs/03` a `docs/10` para reflejar el estado ya implementado del repo y eliminar bloqueos documentales ya resueltos.
- Motivo: varios documentos seguian describiendo el repo como si fuera solo backtest, como si no existiera paper runtime o como si aun faltara un repo remoto.
- Impacto esperado: `docs/` vuelve a ser fuente de verdad util para seguir desarrollando sin falsas premisas.
- Validacion realizada: contraste cruzado entre docs, entrypoints, config, tests existentes y artefactos de cloud.
- Riesgo residual: la documentacion ya quedo alineada con el estado actual, pero el estado actual sigue teniendo deuda tecnica importante antes de live.

### 2026-04-01
- Cambio: backtest alineado con paper en bucket de riesgo configurable y `sizing_engine`.
- Motivo: el backtest seguia usando `risk_pct=0.01` fijo y sizing provisional, lo que hacia inconsistentes las conclusiones frente a paper mode.
- Impacto esperado: menor divergencia economica entre research y runtime, con `max_notional_pct` aplicado tambien en backtest.
- Validacion realizada: suite completa de `unittest` con `28 tests` OK y tests nuevos de cap de notional en `signal_builder`.
- Riesgo residual: backtest y paper todavia difieren en el precio de entrada y en los limites agregados de portafolio.

### 2026-04-01
- Cambio: agregados artefactos de baseline reproducible por corrida en backtest.
- Motivo: los outputs por simbolo no alcanzaban para comparar versiones ni fijar una corrida multi-simbolo de forma auditada.
- Impacto esperado: cada corrida ahora deja `config_snapshot.json`, `baseline_summary.json` y `baseline_symbols.csv` ademas de los archivos por simbolo.
- Validacion realizada: suite completa de `unittest` con `31 tests` OK y tests nuevos en `test_backtest_baseline_artifacts.py`.
- Riesgo residual: la capacidad ya existe, pero todavia faltaba ejecutar y fijar una baseline multi-simbolo real con estos artefactos.

### 2026-04-01
- Cambio: `run_backtest.py` ahora soporta subsets por `--symbols` y se agrego [rebuild_backtest_baseline.py](/D:/binance_futures_bot/scripts/rebuild_backtest_baseline.py) para reconstruir baseline consolidada desde outputs existentes.
- Motivo: la corrida completa de los 5 simbolos excede el tiempo practico de este entorno y una corrida monolitica no era una base operativa confiable.
- Impacto esperado: completar corridas largas por tramos sin perder la baseline consolidada final.
- Validacion realizada: suite completa de `unittest` con `33 tests` OK, corrida real de `BNBUSDT`, corrida real de `XRPUSDT` y reconstruccion real de baseline multi-simbolo.
- Riesgo residual: la baseline ya quedo fijada, pero el sistema sigue siendo perdedor y todavia no existe una corrida de portfolio con limites agregados reales.

### 2026-04-01
- Cambio: activacion de `strategy.backtest_policy` para research v2 con gating de contexto `4h/1h`, exclusion de `BNBUSDT` y restricciones por lado por simbolo.
- Motivo: la baseline v1 mostraba que el problema dominante era de seleccion de contexto y direccion, no de falta de infraestructura ni de mas indicadores.
- Impacto esperado: reducir `STOP_LOSS` recurrentes, bajar cantidad de trades malos y volver la baseline al menos cercana a neutra antes de tocar paper/live.
- Validacion realizada: suite completa de `unittest` con `43 tests` OK, corrida real parcial de la v2, reconstruccion real de baseline consolidada y regeneracion de diagnostico en [baseline_diagnostic.md](/D:/binance_futures_bot/outputs/backtests/baseline_diagnostic.md).
- Riesgo residual: la mejora existe, pero sigue siendo fragil; `SOLUSDT` y `XRPUSDT` permanecen negativos y paper/live todavia no heredan este gating.

### 2026-04-01
- Cambio: separacion formal entre `core` y `experimental` en research.
- Motivo: mezclar `BTC/ETH` con `XRP/SOL/BNB` seguia contaminando la lectura del edge y la prioridad correcta era consolidar un nucleo defendible.
- Impacto esperado: `config/base.yaml` queda como `core v3` (`BTCUSDT` y `ETHUSDT`, `SHORT` only) y [config/research.xrp_long.yaml](/D:/binance_futures_bot/config/research.xrp_long.yaml) deja `XRPUSDT` como laboratorio separado `LONG` only.
- Validacion realizada: corrida real del `core v3` con `44 trades` y `+211.2778 USDT`; corrida real de `XRP` laboratorio con `31 trades` y `+48.6424 USDT`; diagnostico separado en [outputs/xrp_lab/backtests/baseline_diagnostic.md](/D:/binance_futures_bot/outputs/xrp_lab/backtests/baseline_diagnostic.md).
- Riesgo residual: `XRP` sigue sin una explicacion estructural robusta; por ahora es un experimento positivo, no parte del core.

### 2026-04-01
- Cambio: promocion al `core` del filtro `max_trigger_candle_atr_multiple = 1.6` y ampliacion de artefactos con metricas de uso de capital.
- Motivo: una grilla chica de experimentos mostro que endurecer la vela gatillo mejoraba el edge en `BTC/ETH`, mientras endurecer volumen a `1.2` empeoraba demasiado la frecuencia.
- Impacto esperado: baseline oficial del `core` mas rentable y con mejor `profit factor`, pero con visibilidad explicita sobre la subutilizacion extrema del capital.
- Validacion realizada: suite completa de `unittest` con `44 tests` OK, rerun real de `BTCUSDT` y `ETHUSDT`, reconstruccion real de baseline y regeneracion de diagnostico.
- Riesgo residual: la nueva baseline sube a `+286.9219 USDT`, pero `aggregate_capital_idle_share_proxy` sigue en `99.92%`; el siguiente problema ya no es solo edge, sino frecuencia/utilizacion de capital.

### 2026-04-01
- Cambio: soporte de `filters.by_symbol` en backtest research y promocion de `ETHUSDT` a una config mas flexible (`range=1.4`) manteniendo `BTCUSDT` en `range=1.2`.
- Motivo: los experimentos mostraron que relajar el rango destruye `BTC`, pero mejora `ETH`; seguir forzando un unico set global ya no era la abstraccion correcta.
- Impacto esperado: mas frecuencia util en `ETH` sin degradar el edge de `BTC`, con el mismo bucket de riesgo y sin tocar el % de capital.
- Validacion realizada: suite completa de `unittest` con `47 tests` OK, baseline oficial reconstruida a `77 trades` y `+414.0505 USDT`, diagnostico regenerado en [baseline_diagnostic.md](/D:/binance_futures_bot/outputs/backtests/baseline_diagnostic.md).
- Riesgo residual: el `core` mejora otra vez, pero `aggregate_capital_idle_share_proxy` sigue en `99.85%`; el problema de utilizacion de capital sigue abierto.

### 2026-04-01
- Cambio: soporte de `trade_management.by_symbol` y promocion de `ETHUSDT` a `max_bars_in_trade = 32` manteniendo `BTCUSDT` en `24`.
- Motivo: en `ETH` los `TIMEOUT` eran positivos y estaban clavados en `24` barras; extender la ventana mejoro `PnL`, `profit factor`, `expectancy` y uso temporal de capital sin tocar riesgo.
- Impacto esperado: capturar mejor continuidad en `ETH` sin aumentar exposicion por trade ni degradar el `core` de `BTC`.
- Validacion realizada: suite completa de `unittest` con `49 tests` OK, laboratorio `ETH` con `24/32/36` barras y baseline oficial reconstruida a `76 trades` y `+480.8169 USDT`.
- Riesgo residual: mejora el `core`, pero la utilizacion agregada de capital sigue siendo muy baja y el cambio todavia no se refleja en paper/live.

### 2026-04-02
- Cambio: promocion de `BTCUSDT` a `max_bars_in_trade = 16` dentro de `trade_management.by_symbol`.
- Motivo: a diferencia de `ETH`, en `BTC` los `TIMEOUT` largos no aportaban; el laboratorio mostro que acortar la ventana a `16` barras mejoraba `PnL`, `profit factor` y `expectancy`, mientras `12` barras destruia el edge.
- Impacto esperado: limpiar salidas lentas en `BTC` sin tocar riesgo, leverage ni porcentaje de capital.
- Validacion realizada: baseline oficial reconstruida a `76 trades` y `+489.4235 USDT`, diagnostico regenerado, y suite completa de `unittest` con `49 tests` OK.
- Riesgo residual: mejora incremental real, pero la utilizacion agregada de capital sigue alrededor de `0.15%` de margen ponderado en el tiempo; la siguiente fase ya tiene que ir a deployment del capital.

### 2026-04-02
- Cambio: promocion de `max_notional_pct = 0.80` para `BTCUSDT` y `ETHUSDT` dentro del `core`.
- Motivo: el laboratorio de capital mostro que subir solo `risk_pct` no movia casi nada porque el sistema ya estaba topado por cap de notional; la palanca correcta era liberar exposicion por simbolo.
- Impacto esperado: mayor PnL y mayor uso de capital sin tocar `risk_pct`, `max_open_positions` ni `leverage`.
- Validacion realizada: variante `notional_0p80_all` en [capital_results.json](/D:/binance_futures_bot/outputs/capital_lab_v2/capital_results.json), baseline oficial reconstruida a `76 trades` y `+614.2689 USDT`, suite completa de `unittest` con `49 tests` OK.
- Riesgo residual: la mejora es real, pero `aggregate_time_weighted_margin_usage_pct_proxy` sigue siendo de apenas `0.18%`; el siguiente cuello ya no es solo cap de notional, sino frecuencia/simultaneidad/exposicion total.

### 2026-04-02
- Cambio: promocion de `runtime.backtest_risk_bucket = strong` para el `core`, equivalente a `risk_pct = 0.0085`, manteniendo `paper_risk_bucket = normal`.
- Motivo: una vez liberado `max_notional_pct = 0.80`, subir el bucket de riesgo por fin empezo a mover `PnL` real.
- Impacto esperado: mas retorno en research sin tocar todavia `leverage`, `max_open_positions` ni el bucket operativo de paper.
- Validacion realizada: laboratorio [risk_results.json](/D:/binance_futures_bot/outputs/capital_lab_v3/risk_results.json), baseline oficial reconstruida a `76 trades` y `+669.9935 USDT`, diagnostico regenerado en [baseline_diagnostic.md](/D:/binance_futures_bot/outputs/backtests/baseline_diagnostic.md).
- Riesgo residual: el margen ponderado en el tiempo sigue en torno a `0.20%`; la mejora economica es real, pero el capital sigue muy subutilizado y esto no justifica tocar leverage todavia.

### 2026-04-02
- Cambio: promocion de `ETHUSDT max_notional_pct = 0.90`, manteniendo `BTCUSDT max_notional_pct = 0.80`.
- Motivo: `ETHUSDT` es el principal motor del `core`; el laboratorio [results.md](/D:/binance_futures_bot/outputs/eth_overweight_lab/results.md) mostro que darle mas peso a `ETH` mejora `PnL` total, mientras bajar `BTCUSDT` a `0.70` empeora el agregado.
- Impacto esperado: mas retorno y un leve aumento de utilizacion de capital sin tocar `leverage` ni bajar el peso base de `BTC`.
- Validacion realizada: baseline oficial reconstruida a `76 trades` y `+692.8689 USDT`, con `aggregate_time_weighted_margin_usage_pct_proxy` de `0.21%`.
- Riesgo residual: la mejora es chica frente al capital ocioso total y el `profit_factor` de `ETHUSDT` se erosiona apenas; sigue siendo un ajuste de asignacion, no una solucion estructural del edge.

### 2026-04-02
- Cambio: soporte explicito de `risk.backtest_by_symbol` en [run_backtest.py](/D:/binance_futures_bot/run_backtest.py) y promocion de `ETHUSDT risk_pct = 0.0100` solo para research.
- Motivo: con frecuencia baja y `ETHUSDT` como principal motor del `core`, tenia mas sentido darle mas riesgo util a `ETH` que seguir moviendo variables globales; el laboratorio [results.md](/D:/binance_futures_bot/outputs/eth_risk_lab/results.md) mostro que `0.0100` mejora el agregado sin tocar `leverage`.
- Impacto esperado: mas retorno y algo mas de uso temporal de margen, manteniendo `BTCUSDT` en el bucket base `strong = 0.0085`.
- Validacion realizada: baseline oficial reconstruida a `76 trades` y `+743.2150 USDT`, con `aggregate_time_weighted_margin_usage_pct_proxy` de `0.23%`, y suite completa de `unittest` con `51 tests` OK.
- Riesgo residual: `ETHUSDT` queda mas cerca del cap y el drawdown sube; `0.0110` se dejo afuera por ser mas agresivo de lo prudente para esta fase.

### 2026-04-02
- Cambio: implementacion de `PULLBACK` continuation en el flujo de backtest (`setup_detector`, `entry_rules`, `signal_service`, `signal_builder`) y soporte de `strategy.allowed_setups_by_symbol`.
- Motivo: hacia falta una segunda logica de entrada para `ETHUSDT` que aumentara frecuencia sin seguir aflojando filtros de breakout.
- Impacto esperado: abrir una nueva linea de research con `PULLBACK` sin contaminar el `core` oficial.
- Validacion realizada: nuevos tests de `signal_service`, `signal_builder` y `run_backtest`; laboratorio [results.md](/D:/binance_futures_bot/outputs/eth_pullback_lab/results.md) con `ETHUSDT`.
- Riesgo residual: el `PULLBACK` sumo `11` trades y `+14.72 USDT` al agregado de `ETH`, pero el setup nuevo por si solo quedo levemente negativo; no se promovio al `core`.

### 2026-04-02
- Cambio: agregado de filtro especifico `max_trigger_body_atr_multiple` para `PULLBACK`, separado del control general de rango `high-low` de la vela gatillo.
- Motivo: el laboratorio temporal mostro que el `PULLBACK` no fallaba por contexto mayor sino por reanudaciones demasiado violentas; los trades malos compartian cuerpos de vela mas extendidos que los ganadores.
- Impacto esperado: limpiar `PULLBACK` agresivos sin tocar `BREAKOUT` ni relajar el `core` oficial.
- Validacion realizada: nuevos tests de `signal_service` y `signal_builder`; analisis posthoc sobre [eth_pullback_combo_tuning_lab/results.json](/D:/binance_futures_bot/outputs/eth_pullback_combo_tuning_lab/results.json) y [eth_pullback_validation_lab/results.json](/D:/binance_futures_bot/outputs/eth_pullback_validation_lab/results.json), resumido en [posthoc_results.md](/D:/binance_futures_bot/outputs/eth_pullback_body_filter_validation_lab/posthoc_results.md).
- Riesgo residual: el filtro mejora 2025 y 2026 YTD, pero deja solo `2` trades `PULLBACK` en la muestra completa; sigue siendo research prometedor, no baseline oficial.

### 2026-04-02
- Cambio: agregado de [validate_eth_pullback_walkforward.py](/D:/binance_futures_bot/scripts/validate_eth_pullback_walkforward.py) para comparar `BREAKOUT` vs variante configurada de `ETH` por ventanas temporales con warmup controlado.
- Motivo: hacia falta una validacion reusable y auditable del laboratorio `ETH PULLBACK`; seguir evaluandolo con scripts ad hoc ya estaba generando friccion y riesgo de lecturas inconsistentes.
- Impacto esperado: medir robustez por trimestre o por mes sin tocar la baseline oficial del `core`.
- Validacion realizada: smoke real con `--freq quarterly --max-periods 1`, artefactos en [results.md](/D:/binance_futures_bot/outputs/eth_pullback_walkforward/results.md), y verificacion de carga del YAML [research.eth_pullback.yaml](/D:/binance_futures_bot/config/research.eth_pullback.yaml).
- Riesgo residual: el smoke solo cubrio `2025Q1`; la corrida completa de todas las ventanas sigue pendiente porque consume bastante tiempo en este entorno.

### 2026-04-02
- Cambio: corrida completa trimestral del walk-forward para [research.eth_pullback.yaml](/D:/binance_futures_bot/config/research.eth_pullback.yaml).
- Motivo: hacia falta cerrar la discusion con evidencia temporal completa, no con labs parciales.
- Impacto esperado: decidir si `PULLBACK` merece promotion al core o si debe seguir congelado como research.
- Validacion realizada: corrida real `--freq quarterly` completa; resultados en [results.md](/D:/binance_futures_bot/outputs/eth_pullback_walkforward/results.md) y [results.json](/D:/binance_futures_bot/outputs/eth_pullback_walkforward/results.json).
- Riesgo residual: el `PULLBACK` mejora `2025Q4` y `2026Q1`, pero no aparece en `2025Q1-Q3`; la mejora total depende de solo `2` trades trimestrales adicionales, asi que sigue sin justificar promotion al `core`.

### 2026-04-02
- Cambio: separacion explicita entre `binance.use_testnet` y `binance.use_testnet_market_data`, con paper market data en produccion por default.
- Motivo: el paper mode estaba consumiendo feed de testnet/demo y eso contaminaba cualquier comparacion con backtest research o con el mercado real.
- Impacto esperado: paper puede seguir aislado del path de ordenes reales, pero ya no depende de velas sinteticas para decidir aperturas.
- Validacion realizada: tests nuevos en [test_market_data_runtime.py](/D:/binance_futures_bot/tests/test_market_data_runtime.py) verificando que el refresh use `https://fapi.binance.com` por default incluso si `use_testnet=true`; suite completa con `60 tests` OK.
- Riesgo residual: el feed ya es de produccion, pero el runtime sigue sin websocket ni catch-up candle-by-candle despues de caidas.

### 2026-04-02
- Cambio: paper runtime ya puede cargar `1h/4h` y aplicar el mismo gating research de lado/contexto que usa backtest.
- Motivo: la comparacion entre backtest y paper estaba viciada porque paper abria trades sin la politica `4h/1h` ni las restricciones por simbolo/lado del research actual.
- Impacto esperado: paper abre el mismo universo/logica de setups que el core research cuando la config activa `strategy.backtest_policy`.
- Validacion realizada: extraccion de politica comun a [runtime_policy.py](/D:/binance_futures_bot/src/strategy/runtime_policy.py), integracion en [paper_engine.py](/D:/binance_futures_bot/src/live/paper_engine.py), carga de snapshots multi-timeframe en [market_data_runtime.py](/D:/binance_futures_bot/src/live/market_data_runtime.py), test nuevo de bloqueo por `allowed_sides` en [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py), y suite completa con `60 tests` OK.
- Riesgo residual: paper sigue sin catch-up real de velas perdidas; la paridad de entrada mejora, pero la paridad operativa completa todavia no.

### 2026-04-02
- Cambio: paper engine ahora hace replay candle-by-candle de velas pendientes para gestionar posiciones abiertas antes de evaluar nuevas aperturas.
- Motivo: si el servicio caia y volvia con varias velas acumuladas, stops y targets intermedios quedaban sin ejecutar y el paper mode dejaba de ser confiable operativamente.
- Impacto esperado: mejor recovery local despues de caidas, sin inventar entradas retroactivas ni cambiar el modelo de señal.
- Validacion realizada: test nuevo [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py) que verifica cierre correcto cuando TP1 y TP2 ocurren en velas perdidas; suite completa con `61 tests` OK.
- Riesgo residual: el replay corrige gestion de posiciones abiertas, pero la persistencia de `paper_state.json` todavia no es atomica y sigue faltando reconciliacion con exchange real.

### 2026-04-02
- Cambio: persistencia atomica de [paper_state.json](/D:/binance_futures_bot/src/live/paper_engine.py) via archivo temporal + `replace`.
- Motivo: un crash durante el write podia dejar el state corrupto y arruinar el recovery de paper aun despues de haber corregido el catch-up de velas.
- Impacto esperado: menor riesgo de corrupcion local del state y mejor continuidad operativa en Render o cualquier runtime persistente.
- Validacion realizada: test nuevo de roundtrip sin residuos temporales en [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py) y suite completa con `62 tests` OK.
- Riesgo residual: sigue faltando reconciliacion con exchange real y recovery ante respuestas ambiguas del exchange.

### 2026-04-02
- Cambio: `execution.slippage` paso de ser decorativo a modelarse de forma efectiva en backtest y paper.
- Motivo: la config ya declaraba slippage por simbolo, pero el sistema solo modelaba ciertos gaps adversos de stop; eso daba una falsa sensacion de control sobre la friccion real de ejecucion.
- Impacto esperado: resultados de research y paper mas creibles, con fills de entrada/salida peores por simbolo y sin doble castigo cuando un stop ya gappea al open adverso.
- Validacion realizada: modulo nuevo [slippage.py](/D:/binance_futures_bot/src/execution/slippage.py), integracion en [execution_simulator.py](/D:/binance_futures_bot/src/execution/execution_simulator.py), [signal_builder.py](/D:/binance_futures_bot/src/backtest/signal_builder.py), [run_backtest.py](/D:/binance_futures_bot/run_backtest.py) y [paper_engine.py](/D:/binance_futures_bot/src/live/paper_engine.py); tests nuevos de slippage en [test_execution_simulator.py](/D:/binance_futures_bot/tests/test_execution_simulator.py), [test_signal_builder.py](/D:/binance_futures_bot/tests/test_signal_builder.py) y [test_paper_engine.py](/D:/binance_futures_bot/tests/test_paper_engine.py); suite completa con `66 tests` OK.
- Riesgo residual: el modelo sigue siendo simple y adverso por porcentaje fijo; no representa microestructura, profundidad ni slippage dependiente de volatilidad intrabar.

### 2026-04-02
- Cambio: unificacion del contrato `ExitReason` y eliminacion del hardcode de `stop_buffer_atr_fraction` en los entrypoints operativos.
- Motivo: habia duplicacion semantica entre [core/models.py](/D:/binance_futures_bot/src/core/models.py) y [execution_simulator.py](/D:/binance_futures_bot/src/execution/execution_simulator.py), y el buffer de ATR del stop seguia clavado en `0.10` dentro de [run_backtest.py](/D:/binance_futures_bot/run_backtest.py) y del path de paper.
- Impacto esperado: menos divergencia de contratos internos y un setup mas trazable desde config, con soporte natural a overrides por simbolo dentro de `filters.by_symbol`.
- Validacion realizada: [execution_simulator.py](/D:/binance_futures_bot/src/execution/execution_simulator.py) ahora importa `ExitReason` comun desde [core/models.py](/D:/binance_futures_bot/src/core/models.py); [run_backtest.py](/D:/binance_futures_bot/run_backtest.py) y [paper_engine.py](/D:/binance_futures_bot/src/live/paper_engine.py) resuelven `stop_buffer_atr_fraction` desde `filters`; configs actualizadas en [base.yaml](/D:/binance_futures_bot/config/base.yaml), [render.paper.yaml](/D:/binance_futures_bot/config/render.paper.yaml), [research.xrp_long.yaml](/D:/binance_futures_bot/config/research.xrp_long.yaml) y [research.eth_pullback.yaml](/D:/binance_futures_bot/config/research.eth_pullback.yaml); test nuevo en [test_backtest_runner.py](/D:/binance_futures_bot/tests/test_backtest_runner.py); suite completa con `67 tests` OK.
- Riesgo residual: el alias comun ya evita duplicacion, pero todavia no hay una capa live que consuma todos esos motivos de salida; el stop buffer sigue con default `0.10` como compatibilidad si una config vieja no lo declara.

### 2026-04-02
- Cambio: conexion real de `scoring_engine.py` y `map_score_to_risk` al backtest research.
- Motivo: el score ya existia, pero no gobernaba ninguna decision economica real; el bucket de riesgo seguia siendo esencialmente fijo aunque la infraestructura de score/risk mapping estaba lista.
- Impacto esperado: el backtest ahora puede subir, bajar o bloquear riesgo trade por trade segun la calidad del setup, dejando trazabilidad del score y del bucket resuelto en las notas del trade.
- Validacion realizada: modulo nuevo [scoring_policy.py](/D:/binance_futures_bot/src/strategy/scoring_policy.py), enriquecimiento de [TradeCandidate](/D:/binance_futures_bot/src/strategy/signal_service.py), integracion en [signal_builder.py](/D:/binance_futures_bot/src/backtest/signal_builder.py) y [run_backtest.py](/D:/binance_futures_bot/run_backtest.py), flag de config `strategy.dynamic_risk_by_score.enabled` en [base.yaml](/D:/binance_futures_bot/config/base.yaml) y configs research, tests nuevos en [test_scoring_policy.py](/D:/binance_futures_bot/tests/test_scoring_policy.py) y [test_signal_builder.py](/D:/binance_futures_bot/tests/test_signal_builder.py), suite completa con `70 tests` OK. Tambien hubo smoke real de `run_backtest.py --symbols BTCUSDT`; la integracion ya no rompe, pero la corrida completa excedio el timeout del entorno.
- Riesgo residual: el score dinamico ya gobierna backtest, pero todavia no paper/live; ademas, la muestra economica completa del `core` todavia no fue regenerada con esta nueva logica por timeout del entorno.

## Baseline auditada disponible
- simbolos: `BTCUSDT`, `ETHUSDT`
- timeframe operativo: `15m`
- periodo observado en outputs: `2025-01` a `2026-02`
- capital inicial de referencia: `10000 USDT`
- trades totales agregados: `76`
- net pnl agregado: `743.2150 USDT`
- mejor simbolo por net pnl: `ETHUSDT`
- peor simbolo por net pnl: `BTCUSDT`
- origen: [baseline_summary.json](/D:/binance_futures_bot/outputs/backtests/baseline_summary.json)
- commit hash de la baseline: no fijado todavia en los outputs

## Lectura historica que no debe perderse
- La baseline v1 amplia con `BNBUSDT` y sin gating research terminaba en `-1365.4976 USDT` con `394` trades.
- La v2 mejora materialmente, pero la mejora viene de recortar universo y contexto, no de haber demostrado edge robusto universal.
