# End-to-end test: anchor use case

**Branch**: `phase-2a-anchor-use-case`
**Date**: 2026-04-29
**Purpose**: Validate the full investigation loop against real pulse and
release-agent MCP servers before merging Phase 2a to main.

---

## Pre-flight verification required

**Stop here before running any commands.** This document has partial
visibility into pulse and release-agent's internals — it infers from
`atlas-docs` and the MCP specs, not from reading those repos. Two things
require confirmation in the actual repositories before the e2e test makes
sense.

### A. MCP server status

War-room's MCP specs were written for pulse and release-agent to implement.
`atlas-docs` describes the MCP interface as "planned from day one" (pulse) and
"future" (release-agent) as of their last update. Before proceeding, verify
in each repo:

**Pulse** — check that an MCP endpoint exists and responds:
```bash
# Replace 8001 with the actual port pulse uses
curl -s http://localhost:8001/mcp/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool
```
Expected: a list containing `check_metric`, `get_recent_anomalies`, `trigger_scan`.

**Release-agent** — same check:
```bash
# Replace 8002 with the actual port release-agent uses
curl -s http://localhost:8002/mcp/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool
```
Expected: a list containing `get_releases`, `get_release`, `explain_release`.

If either server does not have these tools, the e2e test cannot run. The
relevant team needs to implement the MCP surface first per the specs in
`docs/specs-for-external-sessions/`.

### B. Data availability

**Pulse data** (`data/funnels/*.csv`):
Pulse reads metric data from local CSVs synced daily from a BI-maintained
Google Sheet (pulse ADR-008). If the sync has never run on this machine,
these CSVs do not exist and `check_metric` / `get_recent_anomalies` will
return empty or stale data. Verify:
```bash
ls -la ../pulse/data/funnels/
# Expected: mx_android.csv, mx_ios.csv, co_android.csv, co_ios.csv
# Expected: files dated today or yesterday
```
If files are absent or stale, run pulse's sync script before starting the
test (see Section 2 below).

**Release-agent reports** (`REPORTS_DIR/gotrendier/android/`):
Release-agent stores release reports as JSON files. The android repo has
been tracked in production via the Slack `PUBLICADA` listener — these reports
should exist. Verify:
```bash
ls ../release-agent/reports/gotrendier/android/ | head -5
# Expected: one or more .json files
```
If empty: the android reports have not been written locally. The degraded-case
test (REPO_NOT_FOUND path) will still pass, but the full correlative case
requires existing reports.

---

## 1. Prerequisits per servei

### Pulse

**Repo assumit**: `../pulse/` (germà de `../war-room/`)

**Env vars requerits** per arrencar el servidor MCP (no el scheduler ni Slack):
```
ANTHROPIC_API_KEY=sk-ant-...     # requerit si el servidor crida Claude per interpretació
```
**Opcionals** (no requerits per al test MCP):
```
SLACK_BOT_TOKEN=...              # só per enviar alertes; no necessari per al test e2e
SLACK_CHANNEL=...                # ídem
```
**Dades que han d'existir** al sistema de fitxers de pulse:
- `data/funnels/mx_android.csv`
- `data/funnels/mx_ios.csv`
- `data/funnels/co_android.csv`
- `data/funnels/co_ios.csv`
- `knowledge/` — base de coneixement de pulse (benchmarks, funnel model)

**Port esperat**: a confirmar al repo de pulse. Port de referència en aquest
document: `8001`. Si és diferent, ajusta les comandes de les seccions
2, 3 i 4.

**MCP path esperat**: `/mcp/mcp` — l'app FastAPI dels serveis és muntada a `/mcp` i
el handler MCP dins d'ella també a `/mcp`, resultant en el path doble.

---

### Release-agent

**Repo assumit**: `../release-agent/` (germà de `../war-room/`)

**Env vars requerits** per arrencar el servidor MCP (serveix reportes JSON
existents; no cal GitHub/Jira per a consultes de lectura):
```
REPORTS_DIR=./reports            # directori arrel dels reports JSON
                                 # confirmar el nom exacte de la variable al repo
```
**Opcionals** (no requerits per llegir reportes ja computats):
```
GITHUB_TOKEN=...                 # requerit per generar nous reportes, no per llegir
JIRA_API_TOKEN=...               # ídem
SLACK_BOT_TOKEN=...              # ídem
ANTHROPIC_API_KEY=...            # requerit si el servidor crida Claude en les respostes
```
**Dades que han d'existir**:
- `reports/gotrendier/android/*.json` — reportes de l'android repo
  (la integració de producció via Slack hauria d'haver-los generat)
- `reports/gotrendier/trendify-test-project/*.json` — sandbox; no s'usa per al test

**Port esperat**: a confirmar al repo. Port de referència: `8002`.

**Repositoris confirmats vs. pending**: `android` és l'únic repo activament
integrat en producció. `backend` i `notisfier` estan pendents de confirmació
del tech lead (veure Secció 5 per com habilitar el cas complet).

---

### War-room

**Env vars requerits**:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export PULSE_MCP_URL=http://localhost:8001/mcp/mcp
export RELEASE_AGENT_MCP_URL=http://localhost:8002/mcp/mcp
```
No cal cap token addicional — war-room és un client pur MCP.
Mock auth: l'header `X-User-Id` s'envia directament als tests; no requereix
configuració d'entorn.

**Port**: `8000` (per al servidor FastAPI si es vol usar la API REST).
Per al test d'integració pytest, no cal arrencar el servidor — els tests
criden l'orchestrator directament.

---

## 2. Arrencada dels serveis (tres terminals)

Obre tres terminals des del directori pare dels repos (`~/Documents/projects/`
o on estiguin).

### Terminal 1 — pulse

Primer, verifica que les CSVs existeixen i estan actualitzades:
```bash
cd pulse
ls -la data/funnels/
```
Si les CSVs no existeixen o estan desactualitzades, executa el sync script
(el nom exacte és al repo de pulse — busca `sync`, `download`, o `ingest`):
```bash
# Exemples probables — confirmar el nom real:
# python scripts/sync_data.py
# python pulse/sync/google_sheets.py
# make sync
```
Un cop les CSVs existeixin, aixeca el servidor MCP:
```bash
# Comanda exacta a confirmar al repo — patró esperat:
cd pulse
uvicorn pulse.main:app --port 8001 --reload
# o: python -m pulse.main
# o: ./scripts/serve.sh
```
Signe d'èxit: `Application startup complete` sense errors de `data/funnels/`.

### Terminal 2 — release-agent

```bash
cd release-agent
# Comanda exacta a confirmar al repo — patró esperat:
REPORTS_DIR=./reports uvicorn api.main:app --port 8002 --reload
# o: python -m api.main
# o: ./scripts/serve.sh
```
Signe d'èxit: `Application startup complete`.

### Terminal 3 — war-room (opcional per als tests pytest)

Per als tests pytest, no cal arrencar el servidor — els tests criden
l'orchestrator directament. Si vols provar la API REST manualment:
```bash
cd war-room
source .venv/bin/activate
ANTHROPIC_API_KEY=... PULSE_MCP_URL=http://localhost:8001/mcp/mcp \
  RELEASE_AGENT_MCP_URL=http://localhost:8002/mcp/mcp \
  uvicorn api.main:app --port 8000 --reload
```

---

## 3. Verificació de salut

Abans d'executar el test, confirma que els tres serveis responen.

```bash
# Pulse
curl -s http://localhost:8001/health | python3 -m json.tool
# Esperat: {"status": "ok"} o equivalent

# Release-agent
curl -s http://localhost:8002/health | python3 -m json.tool
# Esperat: {"status": "ok"} o equivalent

# War-room (si l'has aixecat)
curl -s http://localhost:8000/health
# Esperat: {"status": "ok"}
```

Si `/health` no existeix en algun servei, prova `/` o `/ping`. Si cap
endpoint respon, el servei no ha arrencat correctament — revisa els logs
de la terminal corresponent.

**Verificació addicional — eines MCP registrades:**
```bash
# Confirmar que pulse exposa les eines esperades
curl -s http://localhost:8001/mcp/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 -c "import sys,json; tools=[t['name'] for t in json.load(sys.stdin)['result']['tools']]; print(tools)"
# Esperat: ['check_metric', 'get_recent_anomalies', 'trigger_scan'] (ordre pot variar)

# Confirmar que release-agent exposa les eines esperades
curl -s http://localhost:8002/mcp/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 -c "import sys,json; tools=[t['name'] for t in json.load(sys.stdin)['result']['tools']]; print(tools)"
# Esperat: ['get_releases', 'get_release', 'explain_release'] (ordre pot variar)
```

---

## 4. Execució del test d'integració

```bash
cd war-room
source .venv/bin/activate

ANTHROPIC_API_KEY=sk-ant-... \
PULSE_MCP_URL=http://localhost:8001/mcp/mcp \
RELEASE_AGENT_MCP_URL=http://localhost:8002/mcp/mcp \
  .venv/bin/pytest tests/integration/test_anchor_use_case.py -v -s
```

El flag `-s` mostra la sortida dels `print()` als tests, incloent el text
complet de la hipòtesi formada i les iteracions consumides.

Per executar un sol test (recomanat per a la primera validació):
```bash
.venv/bin/pytest tests/integration/test_anchor_use_case.py::test_anchor_use_case_degraded -v -s
```

---

## 5. Cas degradat vs. cas complet

### Cas degradat (recomanat per a primera validació — criteri MVP)

**Condició**: pulse retorna dades reals de mètriques; release-agent retorna
`REPO_NOT_FOUND` per a tots els repositoris (cap confirmat en producció des
de la perspectiva de war-room).

**Per què és acceptable**: el cas degradat demostra el comportament honest
de war-room. La hipòtesi formada ha de:
1. Reconèixer la dada de pulse (caiguda de mètrica, plataforma afectada, onset)
2. Declarar explícitament que la correlació de releases no s'ha pogut avaluar
3. Proposar una hipòtesi qualificada (confiança `Working`) amb el gap articulat

**Criteri d'èxit del test `test_anchor_use_case_degraded`**:
- `iteration_count >= 2` (almenys source-routing + tool call + síntesi)
- `current_hypothesis is not None`
- `Confidence: Working` (o `High` si hi ha dades suficients)
- El nom de mètrica apareix en la resposta

**Com preparar-ho**: no cal fer res — REPO_NOT_FOUND és el comportament per
defecte de release-agent per als repos no confirmats (`android`, `backend`,
`notisfier`). War-room tracta aquest cas com a coverage gap (ADR-009).

---

### Cas complet (opcional — requereix confirmació manual al repo de release-agent)

**Condició**: pulse retorna dades reals + release-agent retorna candidats
reals per a almenys un repositori.

**Com preparar-ho**: el tech lead ha de confirmar un repositori a release-agent.
Busca al repo de release-agent un fitxer YAML a `knowledge/risk-maps/` (o
equivalent) per al repositori en qüestió. Canvia el camp d'estat:

```yaml
# Exemple per a android — confirmar el nom exacte del camp al repo
status: confirmed    # era: pending o provisional
```

Reinicia el servidor de release-agent perquè llegeixi el canvi.

Alternativament, si release-agent exposa un endpoint d'administració per
confirmar repos, usa'l en lloc d'editar el YAML directament.

**Criteri d'èxit**:
- `get_releases` retorna almenys un release per al repositori confirmat
- `explain_release` s'invoca per als candidats temporals
- La hipòtesi inclou correlació específica (release ID + data de deploy vs. onset)
- `Confidence: Working` o `High` (dependrà de la proximitat temporal)

**Nota**: el cas complet no és requerit per al merge de Phase 2a. El criteri
MVP és el cas degradat amb hipòtesi qualificada honest.

---

## 6. Bugs trobats durant el test

Si un test falla, segueix aquest procés:

1. No modificar tests per fer-los passar.
2. Corregir el codi a la branca `phase-2a-anchor-use-case`.
3. Documentar aquí els bugs trobats i les correccions aplicades (com a
   amendments d'aquest document, amb data).
4. Tornar a executar el test sencer després de cada correcció.
5. Quan tots els tests passen: merge a main.

Si es descobreix una desviació entre el que war-room espera de pulse o
release-agent (paràmetres, format de resposta) i el que el servei
retorna realment: documentar-la com a inconsistència potencial dels specs
i obrir una conversa de coordinació (felip.costa@gotrendier.com als equips).
No canviar els adapters per adaptar-se silenciosament a una resposta inesperada
sense documentar la discrepància primer.

---

## 7. Resposta a la pregunta substantiva sobre les dades

### Pulse (CSVs a `data/funnels/`)

**Visibilitat**: sí, però indirecta. Dels atlas-docs de pulse:
- La font és un Google Sheet de BI (4 pestanyes: mx_android, mx_ios,
  co_android, co_ios), actualitzat diàriament a les 09:00 UTC.
- Un script de sync el descarrega com a CSVs a disc local. Pulse llegeix
  fitxers locals exclusivament — cap dependència de runtime a Google.
- Si el sync falla, pulse usa els CSVs del dia anterior. Si el sync **mai
  ha corregut** en aquesta màquina, els fitxers no existeixen.

**Diagnosi**: si `ls ../pulse/data/funnels/` és buit o no existeix el
directori, caldrà executar el script de sync de pulse una vegada abans del
test. El script és a pulse — busca comandes tipus `make sync`, `python scripts/sync_data.py`,
o similar. Necessitarà credencials de Google Sheets (la clau de servei de BI).

**Alternativa sense credencials**: crear un CSV mínim de fixture per validar
que els endpoints MCP responen correctament. El contingut és simple — dates,
ratios entre 0.0 i 1.0:

```csv
date,value
2026-04-15,0.912
2026-04-16,0.908
2026-04-17,0.915
2026-04-18,0.901
2026-04-19,0.897
2026-04-20,0.891
2026-04-21,0.889
2026-04-22,0.752
2026-04-23,0.748
2026-04-24,0.751
2026-04-25,0.749
2026-04-26,0.747
2026-04-27,0.745
```

Posa copies d'aquest CSV com a `mx_android.csv`, `mx_ios.csv`, etc. a
`data/funnels/`. Els valors mostren una caiguda brusca a partir del 22 —
útil per generar una hipòtesi clara durant el test.

**Important**: no commitegis fixtures de dades al repo de pulse. Usa'ls
localment per al test i suprimeix-los després del merge.

---

### Release-agent (reports JSON a `reports/`)

**Visibilitat**: sí, però indirecta. Dels atlas-docs de release-agent:
- Reports a `REPORTS_DIR/{owner}/{name}/{id}.json`.
- Android integrat en producció via listener de Slack (`PUBLICADA`). Si
  el listener ha estat actiu, `reports/gotrendier/android/` hauria de tenir
  reports reals.
- Backend i notisfier estan pendents d'integració — seus directoris probablement
  buits o inexistents.

**Diagnosi**: executa `ls ../release-agent/reports/gotrendier/android/`.
- Si hi ha fitxers JSON: estan disponibles per al cas complet.
- Si el directori és buit o no existeix: release-agent retornarà REPO_NOT_FOUND
  per a tots els repos → comportament de cas degradat. **El test degradat
  passarà igualment** — és el comportament esperat per a Phase 2a.

No cal generar fixtures de release-agent. El cas degradat és suficient per
a la validació MVP.
