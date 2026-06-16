"""
Autopilot — Procesa TODOS los leads sin intervencion humana.

Uso:
    python autopilot.py                 # Procesa todos los leads
    python autopilot.py --tier 3        # Solo Tier 3
    python autopilot.py --icp 1         # Solo ICP Rank 1
    python autopilot.py --dry-run       # Simula sin escribir al Excel

NO envia emails en ningun caso.
"""

import argparse
import sys

from config.settings import load_settings
from services.llm_service import LLMService
from services.template_service import TemplateService
from services.excel_service import ExcelService
from services.validator import validate_content
from services.logger import log_event
from main import generate_content_for_lead


def run_autopilot(
    tier: str | None = None,
    icp_rank: str | None = None,
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """Run autopilot and return summary dict.

    Shared by the CLI script and the API endpoint.
    on_progress(current, total, lead_name, status) is called after each lead.
    """
    # ── Setup ──
    settings = load_settings()
    llm = LLMService(settings)
    templates = TemplateService(settings)
    excel = ExcelService(settings)

    # ── Read & filter leads ──
    leads = excel.read_leads(tier=tier, icp_rank=icp_rank)

    if not leads:
        print("  No se encontraron leads con esos filtros.")
        return {"processed": 0, "approved": 0, "pending": 0, "errors": 0, "skipped": 0}

    existing_ids = excel.get_output_ids()
    new_leads = [l for l in leads if str(l.get("id", "")) not in existing_ids]
    skipped = len(leads) - len(new_leads)

    if not new_leads:
        print("  Todos los leads ya tienen contenido generado.")
        return {"processed": 0, "approved": 0, "pending": 0, "errors": 0, "skipped": skipped}

    mode_label = "DRY-RUN" if dry_run else "AUTOPILOT"
    print(f"\n{'=' * 60}")
    print(f"  {mode_label} — {len(new_leads)} leads a procesar")
    if skipped:
        print(f"  ({skipped} omitidos por duplicado)")
    print(f"{'=' * 60}\n")

    # ── Process ──
    approved = 0
    pending_count = 0
    errors = 0
    results = []

    total = len(new_leads)

    for i, lead in enumerate(new_leads, 1):
        lead_tier = str(lead.get("tier", "3")).strip()
        method_label = "IA" if lead_tier == "3" else f"Template T{lead_tier}"
        lead_name = f"{lead['contact_name']} | {lead['company_name']}"

        print(f"  [{i}/{total}] {lead_name} ({method_label})...", end=" ")

        if on_progress:
            on_progress(i, total, lead_name, "generating")

        content, attempts, failures, method = generate_content_for_lead(
            lead, llm, templates, settings,
        )

        if content is None:
            errors += 1
            log_event(
                lead_id=str(lead.get("id", "")),
                contact_name=lead.get("contact_name", ""),
                company=lead.get("company_name", ""),
                tier=lead_tier,
                icp_rank=str(lead.get("icp_rank", "")),
                action="error",
                attempts=attempts,
            )
            results.append({
                "lead_id": str(lead.get("id", "")),
                "contact_name": lead.get("contact_name", ""),
                "company": lead.get("company_name", ""),
                "tier": lead_tier,
                "status": "error",
            })
            print("FALLO")
            if on_progress:
                on_progress(i, total, lead_name, "error")
            continue

        # ── Auto-approval logic ──
        validation_passed = not failures

        if lead_tier in ("1", "2"):
            # Templates are always valid → auto-approve
            auto_approved = True
        else:
            # Tier 3: approve if validation passed, pending if not
            auto_approved = validation_passed

        word_count = len(content.get("email_body", "").split())

        # ── Log generation ──
        log_event(
            lead_id=str(lead.get("id", "")),
            contact_name=lead.get("contact_name", ""),
            company=lead.get("company_name", ""),
            tier=lead_tier,
            icp_rank=str(lead.get("icp_rank", "")),
            word_count_email=word_count,
            action="generated",
            validation_passed="yes" if validation_passed else "no",
            validation_failures=", ".join(failures),
            attempts=attempts,
        )

        if not dry_run:
            # Write to Excel (defaults to Approved = "pending")
            excel.write_output(lead, content)

            if auto_approved:
                # Promote to "yes" — only for valid content
                excel.update_approval(str(lead["id"]), approved=True)
            # If not auto_approved, leave as "pending" for human review

            # Log approval/pending
            log_event(
                lead_id=str(lead.get("id", "")),
                contact_name=lead.get("contact_name", ""),
                company=lead.get("company_name", ""),
                tier=lead_tier,
                icp_rank=str(lead.get("icp_rank", "")),
                action="approved" if auto_approved else "pending",
                validation_passed="yes" if validation_passed else "no",
            )

        if auto_approved:
            approved += 1
            status = "approved"
        else:
            pending_count += 1
            status = "pending"

        status_label = "OK" if auto_approved else "PENDING (validacion fallo)"
        if failures:
            status_label += f" [{len(failures)} advertencia(s)]"
        print(status_label)

        if on_progress:
            on_progress(i, total, lead_name, status)

        results.append({
            "lead_id": str(lead.get("id", "")),
            "contact_name": lead.get("contact_name", ""),
            "company": lead.get("company_name", ""),
            "tier": lead_tier,
            "method": method,
            "status": status,
            "word_count": word_count,
            "attempts": attempts,
            "failures": failures,
        })

    # ── Summary ──
    summary = {
        "processed": len(new_leads),
        "approved": approved,
        "pending": pending_count,
        "errors": errors,
        "skipped": skipped,
        "dry_run": dry_run,
        "results": results,
    }

    print(f"\n{'=' * 60}")
    print(f"  RESUMEN {'(DRY-RUN) ' if dry_run else ''}")
    print(f"{'=' * 60}")
    print(f"  Total procesados:  {len(new_leads)}")
    print(f"  Auto-aprobados:    {approved}")
    print(f"  Pendientes:        {pending_count}")
    print(f"  Errores:           {errors}")
    print(f"  Omitidos (dup):    {skipped}")
    if dry_run:
        print(f"\n  (Modo DRY-RUN: no se escribio al Excel)")
    print(f"  Emails enviados:   0 (autopilot no envia emails)")
    print(f"{'=' * 60}\n")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Autopilot — Procesa leads sin intervencion humana",
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3"],
        help="Solo procesar leads de este tier",
    )
    parser.add_argument(
        "--icp",
        choices=["1", "2", "3"],
        help="Solo procesar leads de este ICP Rank",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin escribir al Excel",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Marketing Agent — Modo Autopilot")
    print("=" * 60)

    try:
        run_autopilot(tier=args.tier, icp_rank=args.icp, dry_run=args.dry_run)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
