"""
Marketing Agent — CLI interactivo para generacion y envio de emails de outreach.

Orquesta los servicios de LLM, templates, validacion, Excel y email.
Todo el UI esta en espanol. Los prompts al LLM van en ingles.
"""

import json
import re
import time

from config.settings import load_settings, Settings
from services.llm_service import LLMService
from services.template_service import TemplateService
from services.excel_service import ExcelService
from services.email_service import EmailService
from services.validator import validate_content, format_failures
from services.logger import log_event
from prompts.prompt_builder import build_prompt


# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────

session = {
    "generated_ai": 0,
    "generated_template": 0,
    "approved": 0,
    "rejected": 0,
    "regenerated": 0,
    "skipped_duplicate": 0,
    "skipped_error": 0,
    "sent": 0,
    "failed_send": 0,
    "rejection_reasons": [],
    "lead_results": [],
}


# ─────────────────────────────────────────────
# CORE: Call LLM for Tier 3 content generation
# ─────────────────────────────────────────────

def call_llm(
    lead: dict,
    llm: LLMService,
    settings: Settings,
    feedback: str = None,
) -> dict | None:
    """Build prompt, call LLM, parse JSON. Retry once on failure."""
    system_prompt, user_prompt = build_prompt(lead, settings)

    if feedback:
        user_prompt += (
            "\n\n# FEEDBACK FROM REVIEWER\n"
            "The previous version was rejected. Here is the feedback:\n"
            f"{feedback}\n\n"
            "Rewrite the output incorporating this feedback. "
            "Return only the JSON."
        )

    max_retries = 1
    for attempt in range(1 + max_retries):
        try:
            if attempt > 0:
                print(f"  Reintentando... (intento {attempt + 1})")
                time.sleep(2)

            raw_text = llm.chat(system_prompt, user_prompt, max_tokens=1024)

            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            result = json.loads(cleaned)

            required_keys = {"email_subject", "email_body"}
            missing = required_keys - result.keys()
            if missing:
                raise ValueError(f"Faltan claves en la respuesta del LLM: {missing}")

            return result

        except Exception as e:
            last_error = e
            continue

    print(f"  Fallo despues de {1 + max_retries} intentos: {last_error}")
    return None


# ─────────────────────────────────────────────
# CORE: Generate + Validate loop (Tier 3 only)
# ─────────────────────────────────────────────

def generate_with_validation(
    lead: dict,
    llm: LLMService,
    settings: Settings,
    feedback: str = None,
) -> tuple[dict | None, int, list[str]]:
    """Generate content and validate against rules. Auto-regenerate on failure.
    Returns (content, attempts_used, last_failures)."""
    last_failures = []

    for attempt in range(1, settings.max_validation_retries + 1):
        content = call_llm(lead, llm, settings, feedback=feedback)
        if content is None:
            return None, attempt, ["llm_generation_failed"]

        failures = validate_content(content, settings)

        if not failures:
            if attempt > 1:
                print(f"  Validacion paso en el intento {attempt}.")
            return content, attempt, []

        last_failures = failures

        if attempt < settings.max_validation_retries:
            print(f"  Validacion fallo (intento {attempt}/{settings.max_validation_retries}):")
            for f in failures:
                print(f"    - {f}")
            print("  Regenerando automaticamente...")
            feedback = (
                "The previous output failed quality validation. Fix these issues:\n"
                + "\n".join(f"- {f}" for f in failures)
                + "\n\nRewrite the output fixing ALL issues. Return only the JSON."
            )
        else:
            print(f"  Validacion fallo despues de {settings.max_validation_retries} intentos:")
            for f in failures:
                print(f"    - {f}")

    return content, settings.max_validation_retries, last_failures


# ─────────────────────────────────────────────
# CORE: Route by tier
# ─────────────────────────────────────────────

def generate_content_for_lead(
    lead: dict,
    llm: LLMService,
    templates: TemplateService,
    settings: Settings,
) -> tuple[dict | None, int, list[str], str]:
    """Route to template or AI generation based on tier.
    Returns (content, attempts, failures, method) where method is 'template' or 'ai'."""
    tier = str(lead.get("tier", "3")).strip()

    if tier in ("1", "2"):
        try:
            content = templates.render(int(tier), lead)
            return content, 1, [], "template"
        except (FileNotFoundError, ValueError, KeyError) as e:
            print(f"  Error en template Tier {tier}: {e}")
            return None, 1, [str(e)], "template"

    # Tier 3 — AI generation with validation
    content, attempts, failures = generate_with_validation(lead, llm, settings)
    return content, attempts, failures, "ai"


# ─────────────────────────────────────────────
# LLM: Lead prioritization
# ─────────────────────────────────────────────

def prioritize_leads(leads: list[dict], llm: LLMService) -> list[dict]:
    """Send all leads to the LLM and let it decide the best processing order."""
    if len(leads) <= 1:
        return leads

    print("\n  El agente esta analizando los leads y decidiendo el orden de prioridad...")

    leads_summary = []
    for lead in leads:
        leads_summary.append({
            "id": lead.get("id", ""),
            "contact_name": lead.get("contact_name", ""),
            "title_contact": lead.get("title_contact", ""),
            "company_name": lead.get("company_name", ""),
            "serie": lead.get("serie", ""),
            "industry": lead.get("industry", ""),
            "size": lead.get("size", ""),
            "tier": lead.get("tier", ""),
            "icp_rank": lead.get("icp_rank", ""),
            "hiring_profile_1": lead.get("hiring_profile_1", ""),
            "hiring_profile_2": lead.get("hiring_profile_2", ""),
        })

    system = (
        "You are a sales strategist. "
        "Your job is to analyze a batch of leads and decide the optimal "
        "order to contact them for maximum conversion."
    )

    user = (
        "Here are the leads:\n"
        f"{json.dumps(leads_summary, indent=2)}\n\n"
        "Rank them from highest to lowest priority. Consider:\n"
        "- Tier and ICP Rank (3/1 = highest priority)\n"
        "- Company stage (growth-stage companies are most likely to convert)\n"
        "- Title seniority (decision makers can respond faster)\n"
        "- Hiring profiles (alignment with available services)\n\n"
        "Return a JSON object with exactly this format:\n"
        '{"ranked_ids": ["id1", "id2", ...], '
        '"reasoning": "one short paragraph explaining your ranking"}\n\n'
        "Return only the JSON. No markdown. No explanation outside the JSON."
    )

    try:
        raw = llm.chat(system, user, max_tokens=1024)

        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        result = json.loads(cleaned)

        ranked_ids = result.get("ranked_ids", [])
        reasoning = result.get("reasoning", "")

        print(f"\n  Razonamiento del agente: {reasoning}\n")

        id_to_lead = {str(l.get("id", "")): l for l in leads}
        ordered = []
        for rid in ranked_ids:
            if str(rid) in id_to_lead:
                ordered.append(id_to_lead[str(rid)])

        ordered_ids = {str(l.get("id", "")) for l in ordered}
        for lead in leads:
            if str(lead.get("id", "")) not in ordered_ids:
                ordered.append(lead)

        return ordered

    except Exception as e:
        print(f"  Analisis de prioridad fallo: {e}. Usando orden por defecto.")
        return leads


# ─────────────────────────────────────────────
# Feedback loop on rejection (Tier 3 only)
# ─────────────────────────────────────────────

def handle_rejection(
    lead: dict,
    llm: LLMService,
    settings: Settings,
) -> tuple[str, dict | None]:
    """Ask user for feedback, regenerate Tier 3 content with that feedback."""
    print("\n  Por que rechazas este contenido? (ayuda al agente a mejorar)")
    print("  Ejemplos: 'muy formal', 'mencionar su industria',")
    print("            'email mas corto', 'tono incorrecto'")
    feedback = input("  Feedback (o Enter para omitir): ").strip()

    if not feedback:
        return feedback, None

    session["rejection_reasons"].append(feedback)

    print("  Regenerando con tu feedback...")
    new_content = call_llm(lead, llm, settings, feedback=feedback)

    if new_content:
        session["regenerated"] += 1
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=lead.get("tier", ""),
            icp_rank=str(lead.get("icp_rank", "")),
            word_count_email=len(new_content.get("email_body", "").split()),
            action="regenerated",
            regenerated="yes",
            feedback=feedback,
        )
        print(f"\n  NUEVO ASUNTO:  {new_content['email_subject']}")
        print(f"\n  NUEVO EMAIL:\n  {new_content['email_body']}")

    return feedback, new_content


# ─────────────────────────────────────────────
# Intelligent session summary
# ─────────────────────────────────────────────

def intelligent_summary(llm: LLMService):
    """Have the LLM analyze the session and give recommendations."""
    total_actions = sum([
        session["generated_ai"], session["generated_template"],
        session["approved"], session["rejected"],
        session["sent"], session["skipped_error"],
    ])

    if total_actions == 0:
        print("\nNo se realizaron acciones en esta sesion. Hasta la proxima.")
        return

    print("\n" + "=" * 50)
    print("  RESUMEN DE SESION")
    print("=" * 50)
    print(f"  Generados (AI):       {session['generated_ai']}")
    print(f"  Generados (template): {session['generated_template']}")
    print(f"  Regenerados:          {session['regenerated']}")
    print(f"  Aprobados:            {session['approved']}")
    print(f"  Rechazados:           {session['rejected']}")
    print(f"  Omitidos (dup):       {session['skipped_duplicate']}")
    print(f"  Omitidos (error):     {session['skipped_error']}")
    print(f"  Emails enviados:      {session['sent']}")
    print(f"  Emails fallidos:      {session['failed_send']}")

    print("\n  El agente esta analizando tu sesion...\n")

    session_data = {
        "stats": {k: v for k, v in session.items()
                  if k not in ("rejection_reasons", "lead_results")},
        "rejection_reasons": session["rejection_reasons"],
        "leads_processed": [
            {"name": r["name"], "company": r["company"],
             "tier": r["tier"], "result": r["result"]}
            for r in session["lead_results"]
        ],
    }

    system = (
        "You are an outreach operations analyst. "
        "Analyze this email outreach session and give actionable recommendations."
    )

    user = (
        f"Session data:\n{json.dumps(session_data, indent=2)}\n\n"
        "Give a short analysis (max 150 words) covering:\n"
        "1. What went well\n"
        "2. What patterns you see in rejections (if any)\n"
        "3. One concrete recommendation for the next session\n\n"
        "Be direct. No fluff. Write as bullet points."
    )

    try:
        analysis = llm.chat(system, user, max_tokens=512)
        print("  -- Analisis del Agente --")
        print(f"  {analysis}")

    except Exception as e:
        print(f"  (No se pudo generar el analisis: {e})")

    print("=" * 50)
    print("  Hasta la proxima.")


# ─────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────

def display_content(content: dict):
    """Print generated email content."""
    print(f"\n  ASUNTO:  {content['email_subject']}")
    print(f"\n  EMAIL:\n  {content['email_body']}")


def show_menu():
    """Display the main agent menu."""
    print("\n" + "=" * 50)
    print("  Que deseas hacer?")
    print("=" * 50)
    print("  1 — Generar contenido (manual, uno por uno)")
    print("  2 — Piloto automatico (generar todo, revisar al final)")
    print("  3 — Revisar aprobaciones pendientes")
    print("  4 — Enviar correos aprobados")
    print("  5 — Panel de control / Estadisticas")
    print("  6 — Salir")
    print("=" * 50)


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────

def get_filtered_new_leads(excel: ExcelService) -> list[dict] | None:
    """Ask user for filter, return new leads (no duplicates)."""
    print("\nFiltrar leads por:")
    print("  T = Tier (1 / 2 / 3)")
    print("  R = ICP Rank (1 / 2 / 3)")
    print("  A = Todos los leads")
    filter_type = input("Elige tipo de filtro (T/R/A): ").strip().upper()

    if filter_type == "T":
        filter_value = input("Ingresa tier (1/2/3): ").strip()
        if filter_value not in ("1", "2", "3"):
            print("Tier invalido. Usa 1, 2 o 3.")
            return None
        leads = excel.read_leads(tier=filter_value)
    elif filter_type == "R":
        filter_value = input("Ingresa ICP rank (1/2/3): ").strip()
        if filter_value not in ("1", "2", "3"):
            print("ICP Rank invalido. Usa 1, 2 o 3.")
            return None
        leads = excel.read_leads(icp_rank=filter_value)
    elif filter_type == "A":
        leads = excel.read_leads()
    else:
        print("Filtro invalido.")
        return None

    if not leads:
        print("No se encontraron leads con ese filtro.")
        return None

    existing_ids = excel.get_output_ids()
    new_leads = []
    duplicates = 0

    for lead in leads:
        if str(lead.get("id", "")) in existing_ids:
            duplicates += 1
            session["skipped_duplicate"] += 1
        else:
            new_leads.append(lead)

    if duplicates > 0:
        print(f"\n{duplicates} lead(s) ya tienen contenido generado. Omitidos.")

    if not new_leads:
        print("Todos los leads con ese filtro ya tienen contenido. Nada que generar.")
        return None

    return new_leads


# ─────────────────────────────────────────────
# DECISION HANDLER
# ─────────────────────────────────────────────

def process_decision(
    lead: dict,
    content: dict,
    excel: ExcelService,
    email_svc: EmailService,
    llm: LLMService,
    settings: Settings,
    is_tier_3: bool,
):
    """Handle s/e/n/r decision for a lead."""
    while True:
        print("\n  Que deseas hacer con este contenido?")
        print("  s = Guardar (aprobar para envio posterior)")
        print("  e = Guardar + Enviar email ahora")
        if is_tier_3:
            print("  r = Rechazar y regenerar con feedback")
        print("  n = Rechazar y omitir")
        decision = input("  > ").strip().lower()

        if decision in ("s", "e"):
            excel.write_output(lead, content)
            excel.update_approval(lead["id"], approved=True)
            session["approved"] += 1
            session["lead_results"].append({
                "name": lead["contact_name"], "company": lead["company_name"],
                "tier": lead.get("tier", ""), "result": "approved",
            })
            log_event(
                lead_id=str(lead.get("id", "")),
                contact_name=lead.get("contact_name", ""),
                company=lead.get("company_name", ""),
                tier=lead.get("tier", ""),
                icp_rank=str(lead.get("icp_rank", "")),
                action="approved",
            )
            print("  Guardado y aprobado.")

            if decision == "e":
                lead_email = lead.get("email", "")
                if lead_email:
                    print(f"  Enviando a {lead_email}...")
                    success = email_svc.send(
                        to_email=lead_email,
                        subject=content["email_subject"],
                        body=content["email_body"],
                    )
                    if success:
                        excel.update_sent(lead["id"])
                        session["sent"] += 1
                        print("  Enviado.")
                    else:
                        session["failed_send"] += 1
                        print("  Error al enviar. Revisa las credenciales de Gmail.")
                else:
                    print("  No hay email para este lead. Solo guardado.")
            return

        elif decision == "r" and is_tier_3:
            feedback, new_content = handle_rejection(lead, llm, settings)
            if new_content:
                content.update(new_content)
                continue
            else:
                _reject_lead(lead, content, excel, feedback or "sin feedback")
                return

        elif decision == "n":
            _reject_lead(lead, content, excel, "omitido sin feedback")
            return

        else:
            print("  Opcion invalida.")


def _reject_lead(lead: dict, content: dict, excel: ExcelService, reason: str):
    """Save content as rejected."""
    excel.write_output(lead, content)
    excel.update_approval(lead["id"], approved=False)
    session["rejected"] += 1
    session["lead_results"].append({
        "name": lead["contact_name"], "company": lead["company_name"],
        "tier": lead.get("tier", ""), "result": "rejected",
    })
    log_event(
        lead_id=str(lead.get("id", "")),
        contact_name=lead.get("contact_name", ""),
        company=lead.get("company_name", ""),
        tier=lead.get("tier", ""),
        icp_rank=str(lead.get("icp_rank", "")),
        action="rejected",
        rejection_reason=reason,
    )
    print("  Guardado como rechazado.")


# ─────────────────────────────────────────────
# ACTION 1: Generate (manual, one by one)
# ─────────────────────────────────────────────

def action_generate(
    llm: LLMService,
    templates: TemplateService,
    excel: ExcelService,
    email_svc: EmailService,
    settings: Settings,
):
    """Generate content for leads one by one with human approval."""
    new_leads = get_filtered_new_leads(excel)
    if not new_leads:
        return

    new_leads = prioritize_leads(new_leads, llm)

    print(f"\n  Orden de procesamiento:")
    for i, lead in enumerate(new_leads, 1):
        print(f"    {i}. {lead['contact_name']} | {lead['company_name']} "
              f"| Tier {lead.get('tier', '?')}")

    print(f"\n{len(new_leads)} lead(s) a procesar.\n")

    for i, lead in enumerate(new_leads, 1):
        tier = str(lead.get("tier", "3")).strip()
        is_tier_3 = tier == "3"

        print(f"\n[{i}/{len(new_leads)}]")
        print(f"--- {lead['contact_name']} | {lead['company_name']} "
              f"| {lead['title_contact']} | Tier {tier} ---")

        if is_tier_3:
            print("  Generando contenido con IA (con validacion)...")
        else:
            print(f"  Aplicando template Tier {tier}...")

        content, attempts, failures, method = generate_content_for_lead(
            lead, llm, templates, settings,
        )

        if content is None:
            session["skipped_error"] += 1
            session["lead_results"].append({
                "name": lead["contact_name"], "company": lead["company_name"],
                "tier": tier, "result": "error",
            })
            log_event(
                lead_id=str(lead.get("id", "")),
                contact_name=lead.get("contact_name", ""),
                company=lead.get("company_name", ""),
                tier=tier,
                icp_rank=str(lead.get("icp_rank", "")),
                action="error",
                attempts=attempts,
            )
            print("  Omitido por error.")
            continue

        if method == "ai":
            session["generated_ai"] += 1
        else:
            session["generated_template"] += 1

        validation_passed = "yes" if not failures else "no"
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=tier,
            icp_rank=str(lead.get("icp_rank", "")),
            word_count_email=len(content.get("email_body", "").split()),
            action="generated",
            validation_passed=validation_passed,
            validation_failures=", ".join(failures),
            attempts=attempts,
        )

        if failures:
            print("  ADVERTENCIA: El contenido tiene problemas de validacion:")
            for f in failures:
                print(f"    - {f}")

        display_content(content)
        process_decision(lead, content, excel, email_svc, llm, settings, is_tier_3)


# ─────────────────────────────────────────────
# BATCH HELPERS
# ─────────────────────────────────────────────

def _approve_batch(items: list[tuple[dict, dict]], excel: ExcelService):
    """Approve a batch of (lead, content) pairs at once."""
    for lead, content in items:
        excel.write_output(lead, content)
        excel.update_approval(lead["id"], approved=True)
        session["approved"] += 1
        session["lead_results"].append({
            "name": lead["contact_name"], "company": lead["company_name"],
            "tier": lead.get("tier", ""), "result": "approved",
        })
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=lead.get("tier", ""),
            icp_rank=str(lead.get("icp_rank", "")),
            action="approved",
        )


def _reject_batch(items: list[tuple[dict, dict]], excel: ExcelService):
    """Reject a batch of (lead, content) pairs at once."""
    for lead, content in items:
        excel.write_output(lead, content)
        excel.update_approval(lead["id"], approved=False)
        session["rejected"] += 1
        session["lead_results"].append({
            "name": lead["contact_name"], "company": lead["company_name"],
            "tier": lead.get("tier", ""), "result": "rejected",
        })
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=lead.get("tier", ""),
            icp_rank=str(lead.get("icp_rank", "")),
            action="rejected",
            rejection_reason="lote rechazado",
        )


# ─────────────────────────────────────────────
# ACTION 2: Autopilot
# ─────────────────────────────────────────────

def action_autopilot(
    llm: LLMService,
    templates: TemplateService,
    excel: ExcelService,
    email_svc: EmailService,
    settings: Settings,
):
    """Autonomous mode: generate all content, then batch review."""
    new_leads = get_filtered_new_leads(excel)
    if not new_leads:
        return

    new_leads = prioritize_leads(new_leads, llm)

    print(f"\n  Piloto automatico: generando contenido para {len(new_leads)} leads...")
    print("  El agente trabajara de forma autonoma. La revision viene despues.\n")

    generated = []

    for i, lead in enumerate(new_leads, 1):
        tier = str(lead.get("tier", "3")).strip()
        method_label = "IA" if tier == "3" else f"Template T{tier}"
        print(f"  [{i}/{len(new_leads)}] {lead['contact_name']} "
              f"| {lead['company_name']} ({method_label})...", end=" ")

        content, attempts, failures, method = generate_content_for_lead(
            lead, llm, templates, settings,
        )

        if content is None:
            session["skipped_error"] += 1
            session["lead_results"].append({
                "name": lead["contact_name"], "company": lead["company_name"],
                "tier": tier, "result": "error",
            })
            log_event(
                lead_id=str(lead.get("id", "")),
                contact_name=lead.get("contact_name", ""),
                company=lead.get("company_name", ""),
                tier=tier,
                icp_rank=str(lead.get("icp_rank", "")),
                action="error",
                attempts=attempts,
            )
            print("FALLO")
            continue

        if method == "ai":
            session["generated_ai"] += 1
        else:
            session["generated_template"] += 1

        validation_passed = "yes" if not failures else "no"
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=tier,
            icp_rank=str(lead.get("icp_rank", "")),
            word_count_email=len(content.get("email_body", "").split()),
            action="generated",
            validation_passed=validation_passed,
            validation_failures=", ".join(failures),
            attempts=attempts,
        )
        generated.append((lead, content))
        status = "OK" if not failures else f"OK (advertencias: {len(failures)})"
        print(status)

    if not generated:
        print("\n  Todas las generaciones fallaron. Revisa tu API key.")
        return

    # ── Batch review ──
    print(f"\n{'=' * 65}")
    print(f"  Piloto automatico completo. {len(generated)} borradores listos para revision.")
    print(f"{'=' * 65}")

    # Summary table
    print(f"\n  {'#':<4} {'Contacto':<20} {'Empresa':<20} {'Tier':<5} {'Palabras':<9} {'Metodo':<10} {'Valid'}")
    print(f"  {'─'*4} {'─'*20} {'─'*20} {'─'*5} {'─'*9} {'─'*10} {'─'*8}")
    for i, (lead, content) in enumerate(generated, 1):
        wc = len(content.get("email_body", "").split())
        tier = lead.get("tier", "?")
        method_label = "IA" if str(tier) == "3" else f"Template"
        failures = validate_content(content, settings) if str(tier) == "3" else []
        valid = "PASS" if not failures else f"WARN({len(failures)})"
        print(f"  {i:<4} {lead['contact_name'][:20]:<20} {lead['company_name'][:20]:<20} {str(tier):<5} {wc:<9} {method_label:<10} {valid}")

    print(f"\n{'=' * 65}")
    print("  Como quieres revisar?")
    print("  a = Aprobar TODOS de una vez")
    print("  b = Revisar por bloques (tu eliges el tamano)")
    print("  r = Revisar uno por uno")
    print("  v = Ver todo el contenido, luego decidir")
    print(f"{'=' * 65}")
    review_mode = input("  > ").strip().lower()

    if review_mode == "a":
        _approve_batch(generated, excel)
        print(f"\n  Los {len(generated)} borradores fueron aprobados.")

    elif review_mode == "b":
        block_size = input(f"  Tamano de bloque (1-{len(generated)}): ").strip()
        if not block_size.isdigit() or int(block_size) < 1:
            block_size = 5
        else:
            block_size = min(int(block_size), len(generated))

        blocks = [generated[i:i + block_size] for i in range(0, len(generated), block_size)]

        for b_idx, block in enumerate(blocks, 1):
            block_start = (b_idx - 1) * block_size + 1
            block_end = block_start + len(block) - 1

            print(f"\n{'=' * 65}")
            print(f"  BLOQUE {b_idx}/{len(blocks)} (borradores {block_start}-{block_end})")
            print(f"{'=' * 65}")

            for i, (lead, content) in enumerate(block):
                global_idx = block_start + i
                print(f"\n  [{global_idx}/{len(generated)}] {lead['contact_name']} | {lead['company_name']}")
                display_content(content)

            print(f"\n  -- Decision del bloque {b_idx} --")
            print("  a = Aprobar este bloque")
            print("  r = Revisar este bloque uno por uno")
            print("  x = Rechazar este bloque")
            block_decision = input("  > ").strip().lower()

            if block_decision == "a":
                _approve_batch(block, excel)
                print(f"  Bloque {b_idx} aprobado ({len(block)} borradores).")
            elif block_decision == "x":
                _reject_batch(block, excel)
                print(f"  Bloque {b_idx} rechazado ({len(block)} borradores).")
            else:
                for i, (lead, content) in enumerate(block):
                    global_idx = block_start + i
                    tier = str(lead.get("tier", "3")).strip()
                    is_tier_3 = tier == "3"
                    print(f"\n[{global_idx}/{len(generated)}]")
                    print(f"--- {lead['contact_name']} | {lead['company_name']} "
                          f"| {lead['title_contact']} | Tier {tier} ---")
                    display_content(content)
                    process_decision(lead, content, excel, email_svc, llm, settings, is_tier_3)

    elif review_mode == "v":
        for i, (lead, content) in enumerate(generated, 1):
            print(f"\n  [{i}/{len(generated)}] {lead['contact_name']} | {lead['company_name']}")
            display_content(content)

        print(f"\n{'=' * 65}")
        print("  Ya viste todo el contenido. Ahora decide:")
        print("  a = Aprobar TODOS")
        print("  r = Revisar uno por uno")
        print(f"{'=' * 65}")
        final_decision = input("  > ").strip().lower()

        if final_decision == "a":
            _approve_batch(generated, excel)
            print(f"\n  Los {len(generated)} borradores fueron aprobados.")
        else:
            for i, (lead, content) in enumerate(generated, 1):
                tier = str(lead.get("tier", "3")).strip()
                is_tier_3 = tier == "3"
                print(f"\n[{i}/{len(generated)}]")
                print(f"--- {lead['contact_name']} | {lead['company_name']} "
                      f"| {lead['title_contact']} | Tier {tier} ---")
                display_content(content)
                process_decision(lead, content, excel, email_svc, llm, settings, is_tier_3)

    else:
        for i, (lead, content) in enumerate(generated, 1):
            tier = str(lead.get("tier", "3")).strip()
            is_tier_3 = tier == "3"
            print(f"\n[{i}/{len(generated)}]")
            print(f"--- {lead['contact_name']} | {lead['company_name']} "
                  f"| {lead['title_contact']} | Tier {tier} ---")
            display_content(content)
            process_decision(lead, content, excel, email_svc, llm, settings, is_tier_3)


# ─────────────────────────────────────────────
# ACTION 3: Review pending
# ─────────────────────────────────────────────

def action_review_pending(excel: ExcelService):
    """Review outputs that are still pending approval."""
    pending = excel.get_pending_outputs()

    if not pending:
        print("\nNo hay aprobaciones pendientes.")
        return

    print(f"\n{len(pending)} aprobacion(es) pendiente(s):\n")

    for i, row in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}]")
        print(f"--- ID: {row['ID']} | {row['Contact Name']} ---")
        print(f"  ASUNTO:  {row['Email Subject']}")
        print(f"  EMAIL:\n  {row['Email Body']}")

        decision = input("\n  Aprobar? (s/n/omitir): ").strip().lower()

        if decision == "s":
            excel.update_approval(str(row["ID"]), approved=True)
            session["approved"] += 1
            print("  Aprobado.")
        elif decision == "n":
            excel.update_approval(str(row["ID"]), approved=False)
            session["rejected"] += 1
            print("  Rechazado.")
        else:
            print("  Omitido por ahora.")


# ─────────────────────────────────────────────
# ACTION 4: Send emails
# ─────────────────────────────────────────────

def action_send_emails(
    excel: ExcelService,
    email_svc: EmailService,
    settings: Settings,
):
    """Send emails for approved but unsent outputs."""
    unsent = excel.get_approved_unsent()

    if not unsent:
        print("\nNo hay correos aprobados pendientes de envio.")
        return

    print(f"\n{len(unsent)} correo(s) aprobado(s) listo(s) para enviar:\n")

    for row in unsent:
        print(f"  - {row['Contact Name']} ({row['ID']}): {row['Email Subject']}")

    if len(unsent) > settings.max_daily_sends:
        print(f"\n  ADVERTENCIA: {len(unsent)} correos excede el limite diario ({settings.max_daily_sends}).")
        print(f"  Solo se enviaran los primeros {settings.max_daily_sends}.")
        unsent = unsent[:settings.max_daily_sends]

    decision = input(f"\nEnviar {len(unsent)} correo(s)? (s/n): ").strip().lower()

    if decision != "s":
        print("Cancelado.")
        return

    leads = excel.read_leads()
    id_to_email = {str(l.get("id", "")): l.get("email", "") for l in leads}

    for i, row in enumerate(unsent):
        lead_email = id_to_email.get(str(row["ID"]), "")

        if not lead_email:
            print(f"  No se encontro email para ID {row['ID']}. Omitido.")
            continue

        print(f"  [{i + 1}/{len(unsent)}] Enviando a {lead_email}...")
        success = email_svc.send(
            to_email=lead_email,
            subject=str(row["Email Subject"]),
            body=str(row["Email Body"]),
        )

        if success:
            excel.update_sent(str(row["ID"]))
            session["sent"] += 1
            log_event(
                lead_id=str(row.get("ID", "")),
                contact_name=str(row.get("Contact Name", "")),
                action="sent",
            )
            print("  Enviado.")
        else:
            session["failed_send"] += 1
            log_event(
                lead_id=str(row.get("ID", "")),
                contact_name=str(row.get("Contact Name", "")),
                action="failed_send",
            )
            print("  Fallo.")

        if i < len(unsent) - 1:
            time.sleep(settings.send_delay)


# ─────────────────────────────────────────────
# ACTION 5: Dashboard
# ─────────────────────────────────────────────

def action_dashboard(excel: ExcelService):
    """Show stats from Excel + current session."""
    stats = excel.get_stats()

    print("\n" + "=" * 50)
    print("  PANEL DE CONTROL")
    print("=" * 50)

    print("\n  -- Historico (desde Excel) --")
    print(f"  Total leads:          {stats['total_leads']}")
    print(f"  Contenido generado:   {stats['total_generated']}")
    print(f"  Aprobados:            {stats['approved']}")
    print(f"  Rechazados:           {stats['rejected']}")
    print(f"  Pendientes revision:  {stats['pending']}")
    print(f"  Emails enviados:      {stats['sent']}")
    print(f"  Aprobados sin enviar: {stats['unsent']}")

    print(f"\n  -- Esta sesion --")
    print(f"  Generados (AI):       {session['generated_ai']}")
    print(f"  Generados (template): {session['generated_template']}")
    print(f"  Regenerados:          {session['regenerated']}")
    print(f"  Aprobados:            {session['approved']}")
    print(f"  Rechazados:           {session['rejected']}")
    print(f"  Omitidos (dup):       {session['skipped_duplicate']}")
    print(f"  Omitidos (error):     {session['skipped_error']}")
    print(f"  Emails enviados:      {session['sent']}")
    print(f"  Emails fallidos:      {session['failed_send']}")

    print("=" * 50)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  Marketing Agent — Generador de Emails")
    print("=" * 50)

    try:
        settings = load_settings()
    except Exception as e:
        print(f"\nError de configuracion: {e}")
        print("Revisa tu archivo .env (usa .env.example como referencia).")
        return

    print(f"\n  Modelo: {settings.openrouter_model}")
    print(f"  Remitente: {settings.sender_name} ({settings.company_name})")

    llm = LLMService(settings)
    templates = TemplateService(settings)
    excel = ExcelService(settings)
    email_svc = EmailService(settings)

    while True:
        show_menu()
        choice = input("  > ").strip()

        if choice == "1":
            action_generate(llm, templates, excel, email_svc, settings)
        elif choice == "2":
            action_autopilot(llm, templates, excel, email_svc, settings)
        elif choice == "3":
            action_review_pending(excel)
        elif choice == "4":
            action_send_emails(excel, email_svc, settings)
        elif choice == "5":
            action_dashboard(excel)
        elif choice == "6":
            intelligent_summary(llm)
            break
        else:
            print("  Opcion invalida. Usa 1-6.")


if __name__ == "__main__":
    main()
