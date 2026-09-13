#!/usr/bin/env python3
"""Print the same validated portfolio totals and categories used by the report."""
import argparse
import json
import sys
from pathlib import Path
from report_model import aggregate, get_type_label, investments_list
from generate_report import format_currency, format_percentage, load_targets, build_allocation_analysis


def summary(investments, targets=None):
    rows = investments_list(investments)
    totals = aggregate(rows)
    money = lambda value: format_currency(value) if value is not None else "não informado"
    rate = format_percentage(totals["return_rate"]) if totals["return_rate"] is not None else "não informado"
    lines = ["## Resumo de Investimentos", "", "| Métrica | Valor |", "|---|---|",
             f"| Total Investido | {money(totals['invested'])} |",
             f"| Valor Atual | {money(totals['current'])} |",
             f"| Rendimento Total | {money(totals['return_amount'])} ({rate}) |",
             f"| Número de Ativos | {totals['count']} |", "", "### Por Tipo de Ativo", "",
             "| Tipo | Valor Atual | % da Carteira |", "|---|---|---|"]
    by_type = {}
    for row in rows:
        label = get_type_label(row.get("type"))
        by_type[label] = by_type.get(label, 0) + row["value"]
    for label, value in sorted(by_type.items()):
        pct = value / totals["current"] * 100 if totals["current"] else 0
        lines.append(f"| {label} | {money(value)} | {format_percentage(pct)} |")
    analysis = build_allocation_analysis(by_type, targets or {}, totals["current"])
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
    args = parser.parse_args()
    try:
        print(summary(json.loads(Path(args.investments).read_text()), load_targets()))
    except (ValueError, OSError) as exc:
        print(f"Summary failed: {exc}", file=sys.stderr)
        sys.exit(1)
