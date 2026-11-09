"""python -m imoveis_pg analyze INPUT --output OUTPUT | collect FONTE --output CSV."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

import pandas as pd

from .data import DataContractError, load_listings, normalize_text
from .quality import audit_listings
from .coleta import SOURCES
from .coleta.contrato import write_contract_csv
from .coleta.http import USER_AGENT, ColetaError, PoliteClient


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Qualidade e EDA de anúncios imobiliários.")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="Importar CSV e gerar relatórios.")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--output", required=True, type=Path)
    analyze.add_argument("--sep", default=";")
    analyze.add_argument("--decimal", choices=[",", "."], default=",")
    collect = sub.add_parser("collect", help="Coletar anúncios públicos de uma imobiliária.")
    collect.add_argument("source", choices=sorted(SOURCES))
    collect.add_argument("--output", required=True, type=Path, help="CSV novo no contrato de dados.")
    collect.add_argument("--cache-dir", type=Path, help="Páginas brutas (padrão: data/raw/FONTE).")
    collect.add_argument("--delay", type=float, default=3.0, help="Segundos entre requisições (mín. 1).")
    collect.add_argument("--max-pages", type=int)
    collect.add_argument("--offline", action="store_true", help="Usar apenas o cache, sem rede.")
    args = parser.parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    created = False
    try:
        if args.output.exists():
            raise DataContractError("A pasta de saída já existe; escolha uma pasta nova.")
        imported = load_listings(args.input, sep=args.sep, decimal=args.decimal)
        quality = audit_listings(imported.rows)
        args.output.mkdir(parents=True, exist_ok=False)
        created = True
        # Import graphics only after validating input.
        from .eda import analyze_listings
        synthetic_input = bool(imported.rows.get("sintetico", pd.Series(dtype=str)).map(
            normalize_text).isin(["sim", "true", "1"]).any())
        eda = analyze_listings(quality.snapshot, args.output / "eda", synthetic_input=synthetic_input)
        quality.observations.to_csv(args.output / "observations.csv", index=False)
        quality.snapshot.to_csv(args.output / "snapshot.csv", index=False)
        pd.concat([imported.issues, quality.issues], ignore_index=True).to_csv(args.output / "issues.csv", index=False)
        quality.summary["valores_invalidos_importacao"] = len(imported.issues)
        quality.summary["registros_rejeitados_estruturalmente"] = 0
        (args.output / "quality.json").write_text(
            json.dumps(quality.summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        manifest = {
            "source_sha256": imported.source_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parameters": {"sep": args.sep, "decimal": args.decimal},
            "versions": {"python": platform.python_version(), **{name: version(name) for name in ["imoveis-pg", "pandas", "numpy", "matplotlib"]}},
            "dados_sinteticos": eda["dados_sinteticos"], "eda": eda,
            "eda_directory": "eda", "status": "complete",
        }
        # Completion manifest is written last; partial outputs never look complete.
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        if created:
            print("Saída incompleta, sem manifesto de conclusão; use uma nova pasta ao tentar novamente.", file=sys.stderr)
        return 2
    print(f"Relatórios gerados em {args.output.resolve()}")
    if manifest["dados_sinteticos"]:
        print("DADOS SINTÉTICOS: resultados demonstrativos, sem validade de mercado.")
    return 0


def _collect(args) -> int:
    if args.delay < 1:
        print("Erro: use --delay de pelo menos 1 segundo.", file=sys.stderr)
        return 2
    if args.output.exists():
        print("Erro: o CSV de saída já existe; escolha outro nome.", file=sys.stderr)
        return 2
    module = SOURCES[args.source]
    cache_dir = args.cache_dir or Path("data/raw") / args.source
    client = PoliteClient(cache_dir=cache_dir, delay=args.delay, offline=args.offline)
    try:
        result = module.collect(client, max_pages=args.max_pages)
    except ColetaError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    if not result.records:
        print("Erro: nenhum anúncio coletado.", file=sys.stderr)
        return 2
    write_contract_csv(result.records, args.output)
    manifest = {
        "fonte": module.FONTE, "url_base": module.BASE_URL, "coletor": args.source,
        "gerado_em": datetime.now(timezone.utc).isoformat(), "user_agent": USER_AGENT,
        "intervalo_s": args.delay, "paginas": result.pages, "max_paginas": args.max_pages,
        "total_declarado_pelo_site": result.declared_total, "anuncios": len(result.records),
        "descartados": result.skipped, "requisicoes": client.requests_made,
        "paginas_do_cache": client.cache_hits, "cache": str(cache_dir),
        "privacidade": "Dados de corretores, descrições, fotos e contatos não são copiados.",
    }
    manifest_path = args.output.with_name(args.output.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(result.records)} anúncios gravados em {args.output} "
          f"({client.requests_made} requisições, {client.cache_hits} páginas do cache).")
    if result.declared_total is not None and args.max_pages is None and \
            len(result.records) + sum(result.skipped.values()) != result.declared_total:
        print(f"Aviso: o site declarou {result.declared_total} anúncios; confira o manifesto.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
