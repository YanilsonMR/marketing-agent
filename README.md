# Marketing Agent

Agente de marketing B2B que genera, valida y gestiona emails de outreach de forma autonoma. El agente analiza leads, genera contenido personalizado con IA, aplica validaciones de calidad y auto-aprueba el contenido que pasa todas las reglas. El humano solo interviene cuando el agente no puede resolver un problema de validacion despues de multiples intentos.

## Como funciona

El agente clasifica cada lead en uno de tres niveles (tiers) segun su actividad de contratacion:

| Tier | Situacion | Metodo |
|------|-----------|--------|
| 1 | No esta contratando | Template estatico (nurturing) |
| 2 | Crecimiento reciente | Template estatico (relacional) |
| 3 | Contratando activamente | Generacion con IA (personalizado) |

### Flujo del Tier 3 (IA)

```
Lead → Prompt Builder → LLM → Validador → Pasa? → Auto-aprueba
                                   ↓ No
                          Feedback de errores → LLM (regenera)
                                   ↓ Falla 3 veces
                          Escala al humano (pendiente de revision)
```

El agente:
1. Construye un prompt personalizado con los datos del lead (industria, cargo, perfiles de contratacion, ICP rank)
2. Llama al LLM via OpenRouter
3. Valida el contenido contra 9 reglas de calidad
4. Si falla, regenera automaticamente incorporando los errores como feedback
5. Si pasa todas las validaciones, aprueba el contenido sin intervencion humana
6. Si falla despues de 3 intentos, lo marca como pendiente para revision manual

### Reglas de validacion

- Conteo de palabras (minimo 80, maximo 150)
- Longitud del asunto (maximo 8 palabras)
- Sin signos de exclamacion
- Sin emojis
- Sin "P.S." / "P.D."
- Sin frases corporativas genericas (lista de frases prohibidas)
- Sin titulos profesionales en el cuerpo del email (CEO, Director, VP, etc.)
- Firma del remitente presente
- Sin placeholders o variables sin resolver

## Modos de operacion

### 1. CLI interactivo (`main.py`)

Menu con opciones para generar contenido uno por uno, revisar, aprobar y enviar.

```bash
python main.py
```

### 2. Autopilot (`autopilot.py`)

Procesa todos los leads de forma autonoma sin intervencion humana. Auto-aprueba contenido valido, marca como pendiente lo que falla.

```bash
python autopilot.py                 # Procesar todos los leads
python autopilot.py --tier 3        # Solo Tier 3
python autopilot.py --icp 1         # Solo ICP Rank 1
python autopilot.py --dry-run       # Simular sin escribir al Excel
```

### 3. API + Dashboard web (`api.py`)

Backend FastAPI con dashboard HTML. Incluye streaming SSE para progreso del autopilot en tiempo real.

```bash
python api.py
# Abrir http://localhost:8000
```

**Endpoints principales:**

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/api/leads` | Listar leads con filtros |
| GET | `/api/stats` | Estadisticas del dashboard |
| GET | `/api/outputs` | Contenido generado |
| GET | `/api/pending` | Pendientes de aprobacion |
| POST | `/api/generate` | Generar contenido para un lead |
| POST | `/api/regenerate` | Regenerar con feedback |
| POST | `/api/approve` | Aprobar o rechazar contenido |
| POST | `/api/send` | Enviar email individual |
| POST | `/api/send-batch` | Enviar todos los aprobados |
| GET | `/api/autopilot/stream` | Autopilot con progreso SSE |

## Instalacion

### Requisitos

- Python 3.11+
- Una API key de [OpenRouter](https://openrouter.ai/)
- (Opcional) Una cuenta de Gmail con [App Password](https://support.google.com/accounts/answer/185833) para envio de emails

### Setup

1. Clonar el repositorio:

```bash
git clone <url-del-repo>
cd marketing-agent
```

2. Crear un entorno virtual e instalar dependencias:

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

3. Configurar variables de entorno:

```bash
cp .env.example .env
```

Editar `.env` con tus credenciales:

```env
OPENROUTER_API_KEY=sk-or-v1-tu-key-aqui
OPENROUTER_MODEL=qwen/qwen3-30b-a3b
SENDER_NAME=Tu Nombre
SENDER_TITLE=Tu Cargo
COMPANY_NAME=Tu Empresa
COMPANY_DESCRIPTION=Descripcion de tu empresa...
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

4. Crear el archivo de leads:

```bash
python create_excel.py
```

O para cargar datos de ejemplo:

```bash
python seed_leads.py
```

5. Ejecutar:

```bash
python main.py          # CLI interactivo
python autopilot.py     # Modo autonomo
python api.py           # API + Dashboard web
```

## Estructura del proyecto

```
marketing-agent/
├── main.py                  # CLI interactivo (menu, generacion manual, feedback loop)
├── autopilot.py             # Procesamiento autonomo por lotes
├── api.py                   # FastAPI backend + dashboard web
├── create_excel.py          # Script para crear el Excel de leads
├── seed_leads.py            # Script para cargar datos de ejemplo
├── requirements.txt         # Dependencias Python
├── .env.example             # Template de configuracion
│
├── config/
│   └── settings.py          # Configuracion centralizada (Pydantic BaseSettings)
│
├── services/
│   ├── llm_service.py       # Integracion con OpenRouter (OpenAI SDK)
│   ├── validator.py         # Validacion de calidad (9 reglas)
│   ├── template_service.py  # Renderizado de templates estaticos (Tier 1/2)
│   ├── excel_service.py     # Lectura/escritura del Excel de leads
│   ├── email_service.py     # Envio de emails via Gmail SMTP
│   └── logger.py            # Logging de eventos a CSV
│
├── prompts/
│   ├── context.md           # Identidad y voz del agente
│   ├── intent.md            # Template de datos del lead
│   ├── tier_3.md            # Estrategia de outreach (Tier 3)
│   └── prompt_builder.py    # Ensamblaje de prompts para el LLM
│
├── templates/
│   ├── tier_1.txt           # Template estatico: nurturing (no contratando)
│   └── tier_2.txt           # Template estatico: crecimiento reciente
│
├── frontend/
│   └── index.html           # Dashboard web (SPA)
│
└── tests/
    ├── test_validator.py
    ├── test_template_service.py
    └── test_settings.py
```

## Configuracion

Todas las variables se configuran en `.env`. Referencia completa:

| Variable | Descripcion | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | API key de OpenRouter | (requerido) |
| `OPENROUTER_MODEL` | Modelo del LLM | `anthropic/claude-sonnet-4` |
| `SENDER_NAME` | Nombre del remitente | (requerido) |
| `SENDER_TITLE` | Cargo del remitente | (requerido) |
| `COMPANY_NAME` | Nombre de la empresa | (requerido) |
| `COMPANY_DESCRIPTION` | Descripcion de la empresa | (requerido) |
| `GMAIL_USER` | Email de Gmail | (requerido) |
| `GMAIL_APP_PASSWORD` | App password de Gmail | (requerido) |
| `EXCEL_FILE` | Ruta al archivo de leads | `leads.xlsx` |
| `MAX_DAILY_SENDS` | Maximo de emails por sesion | `50` |
| `MAX_VALIDATION_RETRIES` | Intentos de regeneracion | `3` |
| `SEND_DELAY` | Segundos entre envios | `2` |
| `TIER_3_EMAIL_MIN_WORDS` | Minimo de palabras (Tier 3) | `80` |
| `TIER_3_EMAIL_MAX_WORDS` | Maximo de palabras (Tier 3) | `150` |
| `SUBJECT_MAX_WORDS` | Maximo de palabras en asunto | `8` |

## Tests

```bash
pytest tests/ -v
```

## Tecnologias

- **LLM**: OpenRouter (compatible con cualquier modelo: Claude, GPT, Qwen, Gemma, etc.)
- **Backend**: FastAPI + Uvicorn
- **Datos**: Excel (openpyxl)
- **Validacion**: Pydantic + reglas custom
- **Email**: Gmail SMTP
- **Frontend**: HTML/JS (SPA)
