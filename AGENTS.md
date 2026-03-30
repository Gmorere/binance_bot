# AGENTS.md

## Objetivo del repositorio
Este repositorio contiene un bot de trading con componentes de estrategia, sizing, simulación/ejecución y backtesting. El objetivo de cualquier cambio es **mejorar confiabilidad, trazabilidad y control de riesgo**, no solo aumentar cantidad de features.

## Prioridades obligatorias
1. No romper la lógica de riesgo, sizing, parciales ni stop loss.
2. No cambiar contratos de entrada/salida entre módulos sin documentarlo.
3. Toda modificación debe dejar trazabilidad clara en logs, outputs o tests.
4. Antes de optimizar, preservar reproducibilidad.
5. Si falta contexto, inspeccionar primero README, docs y código relacionado antes de editar.

## Cómo trabajar en este repo
- Empieza leyendo `README.md` y `docs/01_SYSTEM_OVERVIEW.md`.
- Si tocas estrategia o ejecución, revisa también `docs/02_TRADING_LOGIC.md`.
- Si tocas backtesting, revisa `docs/03_BACKTEST_AND_METRICS.md`.
- Si tocas configuración o variables sensibles, revisa `docs/04_SETUP_AND_ENV.md`.
- Si detectas supuestos no documentados, agrégalos al archivo correspondiente.

## Reglas de edición
- Haz cambios pequeños y reversibles.
- Mantén nombres explícitos.
- No agregues dependencias sin justificarlo.
- No dupliques lógica entre simulación, ejecución y backtest.
- Si cambias una firma pública, actualiza documentación y ejemplos.
- Si no puedes verificar algo técnicamente, dilo explícitamente en el resumen final.

## Reglas para trading/riesgo
- No relajes validaciones de riesgo por conveniencia.
- No alteres TP1/TP2, parciales, fees o cálculo de PnL sin dejar test o ejemplo reproducible.
- No mezcles datos de live y backtest sin una capa explícita de separación.
- Cualquier cambio en sizing debe explicar impacto en exposición máxima, fee drag y drawdown.

## Qué entregar al finalizar una tarea
- Resumen de qué cambió.
- Archivos modificados.
- Riesgos o puntos no verificados.
- Cómo probar el cambio.
- Si aplica, ejemplo de comando para reproducir.

## Review guidelines
- Verifica que no se haya roto la separación entre señal, plan de orden, simulación y métricas.
- Verifica que fees y PnL neto sigan consistentes.
- Verifica que el output del backtest siga siendo auditable.
- Señala cualquier lugar donde haya riesgo de sobreajuste, leakage o lookahead bias.
