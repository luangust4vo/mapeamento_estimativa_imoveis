"""python -m imoveis_pg analyze INPUT --output OUTPUT."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

import pandas as pd

from .data import DataContractError, load_listings
from .quality import audit_listings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Qualidade e EDA de anúncios imobiliários.")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="Importar CSV e gerar relatórios.")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--output", required=True, type=Path)
    analyze.add_argument("--sep", default=";")
    analyze.add_argument("--decimal", choices=[",", "."], default=",")
    args = parser.parse_args(argv)
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
        eda = analyze_listings(quality.snapshot, args.output / "eda")
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


if __name__ == "__main__":
    raise SystemExit(main())
