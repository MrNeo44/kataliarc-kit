# Plan de implementación — KatalIArc Kit MVP 0.1

1. **Paquete y contratos** — crear `pyproject.toml`, CLI modular en `src/kataliarc/`, metamodelo declarativo y schemas JSON para validar artefactos y trazabilidad.
2. **Inicialización y plantillas** — generar `.kataliarc/`, skills Codex en `.agents/skills/` con frontmatter válido, `AGENTS.md` y artefactos iniciales sin sobrescribir contenido.
3. **Flujo secuencial** — implementar `elicit`, `prioritize`, `design`, `evaluate`, `review`, `decide`, `status` y `validate`; separar roles Pohl, Toulmin, Kazman y Walton y permitir completar los JSON manualmente.
4. **Integración Codex** — agregar adaptador intercambiable y ejecución optativa con `codex exec`, sin elevar permisos ni desactivar sandbox; mantener el flujo local utilizable sin APIs.
5. **Verificación** — añadir pruebas unitarias/de integración sin red, ejecutar pytest y comandos CLI, corregir defectos y documentar instalación/uso/supuestos en README y `DECISIONS.md`.

## Estructura prevista

`src/kataliarc/` (CLI, modelos, validación, proveedor Codex y orquestación), `metamodel/` (contrato declarativo), `schemas/` (JSON Schema), `templates/` (artefactos y skills), `tests/` (pruebas sin llamadas externas).
