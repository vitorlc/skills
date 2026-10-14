#!/usr/bin/env python3
"""Print the same validated portfolio totals and categories used by the report."""
import argparse
import json
import sys
from pathlib import Path
from report_model import (aggregate, build_allocation_analysis, category_totals, coverage, format_currency,
                          format_percentage, investments_list, migrate_legacy, money_or_unknown,
                          percent_or_unknown)
from generate_report import load_targets


def summary_data(investments, targets=None):
    """Structured form of the summary, for agents that should not parse Markdown."""
    rows = investments_list(investments)
    totals = aggregate(rows)
    by_type = category_totals(rows)
    analysis = build_allocation_analysis(by_type, targets or {}, totals["current"])
    return {"totals": totals, "coverage": coverage(rows), "by_type": by_type, "analysis": analysis}


def summary(investments, targets=None):
    data = summary_data(investments, targets)
    totals, cov, by_type = data["totals"], data["coverage"], data["by_type"]
    rate = percent_or_unknown(totals["return_rate"])
    lines = ["## Resumo de Investimentos", "", "| Métrica | Valor |", "|---|---|",
             f"| Total Investido | {money_or_unknown(totals['invested'])} |",
             f"| Valor Atual | {format_currency(totals['current'])} |",
             f"| Rendimento Total | {money_or_unknown(totals['return_amount'])} ({rate}) |",
             f"| Número de Ativos | {totals['count']} |"]
    if totals["invested"] is None and cov["known_count"]:
        lines.append(f"| Rendimento parcial | {format_currency(cov['return_amount'])} ({percent_or_unknown(cov['return_rate'])}) "
                     f"sobre {format_currency(cov['invested'])}, em {cov['known_count']} de {cov['count']} ativos "
                     f"({cov['value_pct']:.0f}% do valor) |")
    lines += ["", "### Por Tipo de Ativo", "", "| Tipo | Valor Atual | % da Carteira |", "|---|---|---|"]
    for label, value in sorted(by_type.items()):
        pct = value / totals["current"] * 100 if totals["current"] else 0
        lines.append(f"| {label} | {money_or_unknown(value)} | {format_percentage(pct)} |")
    analysis = data["analysis"]
    if analysis:
        lines.extend(["", "### Análise de Alocação", "", "| Categoria | Meta | Atual | Desvio |", "|---|---|---|---|"])
        for row in analysis["rows"]:
            label = row['category'].replace('|', '\\|').replace('\n', ' ')
            lines.append(f"| {label} | {row['target_pct']}% | {row['actual_pct']}% | {row['deviation']:+.1f}% |")
        lines.extend(["", *analysis["recommendations"]])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("investments")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of Markdown")
    args = parser.parse_args()
    try:
        migrate_legacy()
        payload = json.loads(Path(args.investments).read_text())
        if args.json:
            print(json.dumps(summary_data(payload, load_targets()), ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print(summary(payload, load_targets()))
    except (ValueError, OSError) as exc:
        print(f"Summary failed: {exc}", file=sys.stderr)
        sys.exit(1)
