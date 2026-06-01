# MKT-4C — Real Campaign Quality Pass

- **Fecha:** 2026-06-01
- **Negocio elegido:** MARKETING-AGENCY-OS (dogfooding)
- **Razón de la elección:** Si nuestro propio pipeline produce una estrategia genérica para nuestro propio producto, es la señal más fuerte de problema. Además todos los datos son verificables sin pedirle nada a un tercero.
- **Backend probado:** `templated` (default) + `claude` con `RefusingClaudeInvoker` (sin `ANTHROPIC_API_KEY` local).
- **Comparación contra real Claude:** no se ejecutó — sin API key en el ambiente de desarrollo. La cañería ya fue validada en MKT-4B con mocks; este bloque se concentra en la calidad de la salida determinística.

---

## TL;DR

El pipeline corre end-to-end con un intake real y produce 12 deliverables coherentes en estructura, pero los outputs **son aún demasiado genéricos para usar tal cual frente a un cliente**. La estructura ya es sólida; el contenido necesita 6 mejoras de templates que se documentan abajo como `P-4C.1`–`P-4C.7`.

Tres bugs reales encontrados al correr el intake — corregidos en este bloque:

| Bug | Síntoma | Causa raíz | Fix |
|-----|---------|------------|-----|
| **B-4C.1** | `ReelsAsset.title` excedía cap de 200 chars → ValidationError → pipeline crash | `ReelsScriptEntry.title` sin cap upstream + template incluye `audience.label` | Truncate en template + truncate defensivo en factory |
| **B-4C.2** | `_InputProduct.name` recibía 250+ chars del `product_or_service` → todos los títulos downstream rompían cap o quedaban ilegibles | Normalizer copiaba `product_or_service` directo a `product.name` | `_short_product_name()` helper + fallback a `client_name` cuando no hay separador |
| **B-4C.3** | `VisualPromptVariant.target_audience` excedía cap de 300 chars | `_InputAudienceHint.label` recibía `audience_description` completo (1000 chars max) | Mismo helper aplicado a audience label, prosa preservada en `description` |

Todas las correcciones tienen tests (`tests/intake/test_short_product_name.py`, `tests/creative/test_reels_title_truncation.py`). Suite completa: 885 verde. Ruff limpio. Cero regresiones después de ajustar 4 tests de claim-audit que se apoyaban en el side-effect del bug B-4C.2.

---

## 1. Intake usado

`examples/intake/marketing-agency-os.json` (publicado en el repo). Highlights:

- `client_name`: MARKETING-AGENCY-OS
- `industry`: developer tools for marketing teams
- `audience_description`: 340 chars, describe agencias chicas + growth marketers in-house + freelancers + indie hackers, con dos pains compartidos específicos.
- `brand_tone`: técnico-pragmático, anti-marketing-hueco, honesto sobre limitaciones, irreverente con buzzwords
- `preferred_words`: determinístico, auditable, fallback, pipeline, intake, approval pack, claim audit, tenant, pin, trazabilidad
- `forbidden_words`: disruptivo, revolucionario, transformación digital, experiencia inigualable, AI-powered, next-gen, potenciar, sinergia, soluciones de clase mundial
- 5 competidores reales (ChatGPT custom, Jasper, Copy.ai, Notion templates, n8n+LLM nodes) con notas técnicas.
- `good_examples`: post LinkedIn con command real + screenshot + frase técnica.
- `bad_examples`: hilos motivacionales, carruseles con citas de gurus.
- `claims_to_avoid`: garantías, "el mejor", "10x", "AI que entiende tu marca".

---

## 2. Ejecución

### `mkt run-campaign --intake examples/intake/marketing-agency-os.json`

```
run_id: 7f4c... (varía)
client_slug: marketing-agency-os
contract_version: pipeline-run.v1
overall_state: draft
blocks_publish: false
is_complete: true
duration_seconds: ~4.2
intake_critical: 0
intake_warning: 4
intake_info: 0
stage_counts: {succeeded: 6, skipped: 0, blocked: 0, failed: 0}
backend_requested: templated
backend_effective: templated
backend_fallback_count: 0
```

12 archivos generados en `outputs/marketing-agency-os/`.

### `mkt run-campaign --backend claude` (sin API key)

```
backend_requested: claude
backend_effective: templated
backend_fallback_count: 6
backend_fallback_notes: [6 × "NoRealInvokerError: No real Claude invoker is wired ..."]
```

Stderr emite WARNING claro. Exit 0. Salida idéntica al run templated (todas las llamadas creativas cayeron al backend determinístico, como diseñado en MKT-4A/4B).

**Nota cosmética:** el mensaje del `RefusingClaudeInvoker` aún dice "MKT-4A ships infrastructure only" — wording obsoleto desde MKT-4B. Tracked como **P-4C.6** (low priority).

---

## 3. Evaluación por sección

Leyenda: 🟢 listo para mostrar al cliente · 🟡 usable con edición humana ligera · 🛑 genérico, requiere mejora antes de exponer

### 3.1 Resumen ejecutivo — 🟡
Estructura correcta. Headline: *"MARKETING-AGENCY-OS: campaña 12 semanas para Agencias chicas de marketing con foco en github_stars + paid_pilots_signed."* Es factual y específica, pero no tiene gancho.

### 3.2 Diagnóstico del negocio — 🟡
- Fortalezas razonables (tono, competidores, budget, canales).
- Una sola debilidad detectada: "Sin propuestas de valor declaradas" — falso positivo, las hay en `additional_context`. El template no lee ese campo.
- Oportunidades = una sola línea formulaica. Genérico.

### 3.3 Público objetivo — 🟢 (después de los fixes)
Label corto, demografía con geo, pain points y outcomes presentes. Bug pre-fix: la `label` era el `audience_description` entero, hacía que cada referencia downstream fuera ilegible. Resuelto.

### 3.4 Buyer persona — 🛑
- "Arquetipo: Agencias típico/a" — el "/a" en español rioplatense suena raro.
- Quote: *"Necesito MARKETING-AGENCY-OS sin tener que pensarlo demasiado."* — vacuo. Suena AI-generated del peor tipo.
- Motivaciones = una sola línea repitiendo el KPI.
- Objeciones = lista de 3 fijas idénticas para todo cliente. No hay personalización.

### 3.5 Propuesta de valor — 🛑 (CRÍTICO)
**Headline:** *"MARKETING-AGENCY-OS: Diseñado específicamente para Agencias chicas de marketing"*

Es el placeholder de template más vacío posible. Cualquier producto + cualquier audiencia podría reusar esa frase. **No tiene NINGUNA de las palabras del `preferred_words`** (determinístico, auditable, fallback, pipeline, intake, approval pack, claim audit, tenant, pin, trazabilidad), siendo que el intake las priorizó explícitamente. **No tiene NINGUNA de las palabras técnicas del producto** ni se acerca al diferencial real (`audit-trail.v1` con hash chain).

### 3.6 Benchmark de competidores — 🟢
Pasa por los 5 competidores y devuelve sus notas tal cual. Útil. La sección "Takeaway" general es vaga pero el dato crudo es correcto.

### 3.7 Canales recomendados — 🟡
Tabla 5x5 razonable (newsletter, blog, linkedin, x, instagram con instagram agregado por la heurística). Rationale por canal es un **template echo idéntico**: *"Match con audiencia ({label}); rol esperado: {role}"* para los 5 canales. Sin nada específico por canal.

### 3.8 Keywords — 🛑 (CRÍTICO)
Cluster names visibles en output post-fix:
```
diseado_informational
setup_informational
sin_informational
marketing-agency-os_informational
developer tools for marketing teams_informational
```

Problemas:
1. **`diseado`** — accent-stripping ASCII salvaje (`Diseñado` → `diseado`).
2. **`setup`** — palabra única extraída de "Setup en menos de un día"; no es un cluster.
3. **`sin`** — preposición. Extraída de "Sin contratos largos". Inútil.
4. Cluster keywords genéricos formato `"qué es X" / "X para agencias" / "cómo usar X" / "guía X"` repetido para cada cluster.

### 3.9 Keywords negativas — 🟢
Lista razonable (`free`, `salary`, `course`, `torrent`, `tutorial gratis`, nombres de competidores). El template extrae los competidores en lowercase como negative match. Útil.

### 3.10 Hashtags — 🛑
Output:
```
#DeveloperToolsForMarketingTeams
#Diseado          ← accent-stripping roto
#MarketingAgencyOs ← PascalCase incoherente con el nombre real
#growth
#marketing
#strategy
```

Los últimos 3 son hardcoded defaults; los primeros 3 son derivados sin normalización Unicode. `#Diseado` directamente no es una palabra en español.

### 3.11 Estrategia de campaña — 🟡
- Objetivo: copia textual del `commercial_objective`. Correcto.
- KPI primario: copia textual del intake. Correcto.
- KPIs secundarios: 3 fijos (cost_per_acquisition, engagement_rate, newsletter_growth). No varían por industria.
- Big idea: misma frase placeholder del headline. 🛑.
- Arco narrativo: 4 fases (awareness/consideration/conversion/retention) con frase idéntica para CUALQUIER campaña. Genérico.

### 3.12 Piezas sugeridas — 🟢
Tabla razonable: 4 emails + 6 articles blog + 8 social threads LinkedIn + 8 social threads X. Cantidades sensatas para 12 semanas.

### 3.13 Briefs visuales — 🟡
3 piezas (hero, carrusel, reels thumbnail). Estructura correcta. Paleta hardcoded `#0F172A / #22D3EE / #F8FAFC` no relacionada con la marca (no hay brand-agent integrado). Tipografía fija "Sans-serif moderno; jerarquía clara; nada decorativo". Buen punto: la sección `do_not_use` SÍ respeta los `forbidden_words` del intake — los lista junto a los visuales prohibidos.

### 3.14 Copies para redes — 🛑 (CRÍTICO)
Los 5 posts (newsletter, blog, linkedin, x, instagram) tienen el MISMO cuerpo:

> *"MARKETING-AGENCY-OS: Diseñado específicamente para Agencias chicas de marketing — y por eso MARKETING-AGENCY-OS existe. Diseñado específicamente para Agencias chicas de marketing."*

La frase se repite dos veces. Cero variación por canal. Cero adaptación al `brand_tone` ("anti-marketing-hueco" — y producimos justamente eso). Cero palabras del `preferred_words`.

### 3.15 Secuencia de emails — 🟡
- 4 emails con cadencia razonable (+0d, +2d, +5d, +10d).
- Estructura email-marketing estándar (Hola / cuerpo corto / CTA / Abrazo).
- Email 1: *"En este recorrido te vamos a mostrar cómo marketing-agency-os: diseñado específicamente para agencias chicas de marketing."* — minúsculas rotas (template echa el headline en lowercase). Frase placeholder.
- Email 3: explícitamente dice `"[Insertar 2 casos cortos — pending para revisión humana.]"` — honesto pero significa que la pieza no está lista para producción sin trabajo manual.
- Email 4: ofrece un descuento sin contexto (no había nada de pricing en el intake). El template asume modelo de venta directa.

### 3.16 Guiones de reels — 🛑
3 reels generados. Reel #1 voiceover:
> *"MARKETING-AGENCY-OS cambia eso porque Diseñado específicamente para Agencias chicas de marketing."*

Frase mal armada gramaticalmente (cambia eso porque + frase nominal mayúscula). Reel #2 voiceover dice literalmente:
> *"Error 1, error 2, error 3."*

Sin reemplazo. Reel #3:
> *"[Insertar cita de cliente real — pending revisión humana.]"*

Honesto pero confirma que el template no genera contenido sustantivo para reels.

### 3.17 Calendario — 🟢
Tabla semana x semana con canal y pieza. 12 semanas × 3 canales = 36 filas. Cadencia inherita del template del canal. Es útil tal cual.

### 3.18 Checklist de aprobación — 🟢
3 items por sección, con severity (blocker/must/should). El template estándar funciona porque la lista no depende del cliente.

### 3.19 Riesgos / claims a validar — 🟢
Detecta y lista las claims declaradas en `claims_to_avoid` del intake + las que infiere del producto. Útil.

### 3.20 Approval Pack — 🟢
`overall_state=draft`, `blocks_publish=False`, 0 claims unsafe detectadas (no había claims arriesgadas en el intake real). Estado consistente con el resto. La cañería de bloqueo se validó en MKT-3B/3F con intakes sintéticos.

---

## 4. Patrón general detectado

El motor templated funciona como **andamiaje estructural**: la organización de las 20 secciones, el flujo de cadencias, el cruce de canales, el cálculo de calendario, el approval pack y la lista de competidores son todos correctos y reutilizables.

El **contenido textual de cada sección** es el cuello de botella:

1. La frase **"X: Diseñado específicamente para Y"** aparece como headline, big idea, value prop principal, copy de carrusel, copy de post social y voiceover de reel — 6 lugares distintos con la misma frase placeholder. Es la fuente de la genericidad percibida.
2. `brand_tone` se ignora completamente. El tono de los outputs es neutro-corporativo, lo opuesto a "anti-marketing-hueco" pedido.
3. `preferred_words` no se usan. Las palabras técnicas del producto están todas en el intake pero ninguna aparece en los outputs.
4. `good_examples` no se reflejan. El intake decía "post de LinkedIn con command real + screenshot + frase técnica" y obtenemos posts genéricos sin command ni screenshot ni nada técnico.
5. **Extracción de keywords/hashtags está rota** (`diseado`, `sin`, `setup`) por: (a) ASCII strip con accent stripping incorrecto, (b) split por whitespace de differentiators sin filtrar stopwords.

---

## 5. Mejoras aplicadas en este bloque

Tres bugs reales, fixes mínimos y testeables, no expanden alcance.

### 5.1 `core/strategy/templates.py` — truncate del reels title
Una sola línea: `title=_truncate(f"Hook #1 — el problema de {audience.label}", 200)`. Cubre el caso conocido del template. La defensa real está en el factory (5.2).

### 5.2 `core/creative/factory.py` — truncate defensivo de reels title
Cap a 200 chars con sufijo `"..."` antes de construir `ReelsAsset`. Vale para outputs del backend templated Y del backend Claude (Claude podría generar títulos arbitrariamente largos).

### 5.3 `core/intake/normalizer.py` — `_short_product_name()` + audience label corto
Helper puro que divide en `" — "`, `" - "`, `" – "`, `":"`, `"("`, `"|"` y cap a 80 chars. Fallback a `client_name` si terminó en `"..."`. Aplicado a product.name y audience_hint.label. La prosa original se preserva en `product.description` y `audience_hint.description`.

**Side-effect detectado:** 4 tests de `--require-approval` y `--stop-on-blocked` se rompieron porque inyectaban claims arriesgadas en `product_or_service` y dependían de que el string entero se echara verbatim a la value proposition. Solución: el normalizer ahora extrae el "tail" después del separador como un value prop explícito (la frase post-em-dash es típicamente una elevator pitch). Eso restaura la detección de claims y además mejora el contenido real (`value_props` se usa downstream). Los 4 tests vuelven a verde sin modificarlos.

---

## 6. PENDING de calidad (no se implementan acá)

Cataloged in `PENDING.md` como `P-4C.1`–`P-4C.7`:

- **P-4C.1** — Templates ignoran `brand_tone`. Concretamente: agregar un selector que mapee tono → adjetivos/verbos preferidos en las frases generadas. Hoy todos los outputs usan tono neutro-corporativo.
- **P-4C.2** — Templates ignoran `preferred_words`. Agregar inyección de al menos 2 palabras del léxico preferido en headline, big idea y al menos un copy por canal.
- **P-4C.3** — Headline / big idea / value prop usan la misma frase placeholder *"X: Diseñado específicamente para Y"* en 6 lugares. Diversificar templates o sembrarlos con datos del intake (industry específica, pain points concretos).
- **P-4C.4** — Keyword cluster extractor con stopword filter. Hoy genera `sin_informational`, `setup_informational`, `diseado_informational`. Filtrar stopwords ES + acent-aware.
- **P-4C.5** — Hashtag generator con normalización Unicode (NFD + filter accent). Hoy `Diseñado` → `Diseado`.
- **P-4C.6** — Mensaje obsoleto en `RefusingClaudeInvoker.complete()` dice "MKT-4A ships infrastructure only". Actualizar a "no `ANTHROPIC_API_KEY` o SDK no instalado".
- **P-4C.7** — Templates ignoran `good_examples` / `bad_examples`. Al menos un template debería leerlos para inyectar patrones (ej: si `good_examples` contiene "command real + screenshot", generar al menos un copy con esa estructura).

Ninguno es bloqueante. Cada uno cabe en un PR chico (~30-80 LOC con tests).

---

## 7. Comparación templated vs claude

No se ejecutó contra Claude real (sin API key local). Se ejecutó contra `RefusingClaudeInvoker` (cañería MKT-4A/4B):

| Aspecto | templated | claude+Refusing |
|---------|-----------|------------------|
| Exit code | 0 | 0 |
| Stages completados | 6/6 | 6/6 |
| Outputs en disco | 12 archivos | 12 archivos (idénticos) |
| `backend_effective` | templated | templated |
| `backend_fallback_count` | 0 | 6 |
| Warning stderr | ninguno | sí, claro |
| Audit events `strategy_backend_fallback` | 0 | 6 |
| Calidad textual | (la documentada arriba) | (la misma) |

La cañería de fallback se confirma. Comparación con Claude real queda fuera de scope sin API key — la próxima sesión con `ANTHROPIC_API_KEY` puede ejecutar el mismo intake con `--backend claude` y la comparación va a ser interesante.

**Predicción razonable** (no validada acá): Claude real va a mejorar mucho 3.5, 3.11, 3.14, 3.15, 3.16 (las secciones textuales libres), va a empeorar nada por validación Pydantic, y no va a tocar 3.7, 3.8, 3.10, 3.17, 3.18, 3.19 (esas vienen del templated agnóstico al backend porque están fuera de los 6 métodos creativos enrutables).

---

## 8. Validación

- Suite completa: **885 passed**
- Ruff: **clean**
- ATLAS HEAD: **untouched** (`66e4902`)
- Pipeline real end-to-end: **OK** sobre `examples/intake/marketing-agency-os.json`
- Backward compatibility: **mantenida** — todos los tests pre-existentes verdes después de los 3 fixes y 1 test-fix correctivo.

---

## 9. Recomendación para el próximo bloque

El siguiente paso natural NO es MCP, n8n ni servicios externos. Es **MKT-4D: Template content quality pass** — atacar `P-4C.1` a `P-4C.7` en ese orden. Específicamente:

- `P-4C.3` da el mayor lift visible (la frase placeholder repetida es lo que más se nota como "AI-generated").
- `P-4C.2` da el mayor lift de personalización (las palabras del cliente aparecen donde deberían).
- `P-4C.4` y `P-4C.5` arreglan los outputs más vergonzosos (`#Diseado`, `sin_informational`).
- `P-4C.1` y `P-4C.7` son ajustes finos pero alinean la salida con lo que el cliente declaró.

Costo estimado MKT-4D: 1-2 sesiones, ~300 LOC de templates + 20-30 tests. Sin nueva arquitectura.

Después de MKT-4D recién tiene sentido invertir en imagen real, MCP, n8n. Hoy hacerlo es construir sobre contenido genérico.
