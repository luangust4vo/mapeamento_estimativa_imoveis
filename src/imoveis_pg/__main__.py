"""python -m imoveis_pg analyze | collect | merge (use --help em cada comando)."""
import argparse
import hashlib
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd

from .data import DataContractError, load_listings, normalize_text
from .quality import audit_listings
from .coleta import SOURCES
from .coleta.contrato import merge_contract_csvs, write_contract_csv
from .coleta.http import USER_AGENT, ColetaError, PoliteClient
from .geo.bairros import BAIRROS_PATH, BAIRROS_URL, BairroResolver, assign_bairros, load_bairros
from .geo.cnefe import CNEFE_PATH, CNEFE_URL, CnefeGeocoder, geocode_records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Qualidade e EDA de anúncios imobiliários.")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="Importar CSV e gerar relatórios.")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--output", required=True, type=Path)
    analyze.add_argument("--sep", default=";")
    analyze.add_argument("--decimal", choices=[",", "."], default=",")
    analyze.add_argument("--bairros", type=Path,
                         help=f"GeoPackage de bairros do IBGE para unificar bairros (ex.: {BAIRROS_PATH}).")
    collect = sub.add_parser("collect", help="Coletar anúncios públicos de uma imobiliária.")
    collect.add_argument("source", choices=sorted(SOURCES))
    collect.add_argument("--output", required=True, type=Path, help="CSV novo no contrato de dados.")
    collect.add_argument("--cache-dir", type=Path, help="Páginas brutas (padrão: data/raw/FONTE).")
    collect.add_argument("--delay", type=float, default=3.0, help="Segundos entre requisições (mín. 1).")
    collect.add_argument("--max-pages", type=int)
    collect.add_argument("--offline", action="store_true", help="Usar apenas o cache, sem rede.")
    collect.add_argument("--cnefe", type=Path, default=CNEFE_PATH,
                         help="Zip do CNEFE 2022 de Ponta Grossa para geocodificar (baixado se ausente).")
    collect.add_argument("--bairros", type=Path, default=BAIRROS_PATH,
                         help="GeoPackage de bairros do IBGE para conferir a geocodificação (baixado se ausente).")
    merge = sub.add_parser("merge", help="Unir CSVs de coletores em uma única base.")
    merge.add_argument("inputs", nargs="+", type=Path)
    merge.add_argument("--output", required=True, type=Path)
    classify = sub.add_parser("classify", help="Comparar classificadores de faixa de aluguel.")
    classify.add_argument("input", type=Path, help="Base unificada no contrato de dados.")
    classify.add_argument("--output", required=True, type=Path)
    classify.add_argument("--bairros", type=Path, default=BAIRROS_PATH)
    classify.add_argument("--faixas", type=int, default=3, help="Número de faixas por quantis (2 a 5).")
    classify.add_argument("--seed", type=int, default=42)
    classify.add_argument("--repeticoes", type=int, default=0,
                          help="Repetir o experimento com N sementes (0..N-1) para medir estabilidade.")
    cluster = sub.add_parser("cluster", help="Agrupar perfis de casas e concentrações espaciais.")
    cluster.add_argument("input", type=Path, help="Base unificada no contrato de dados.")
    cluster.add_argument("--output", required=True, type=Path)
    cluster.add_argument("--bairros", type=Path, default=BAIRROS_PATH)
    cluster.add_argument("--eps-m", type=float, default=600, help="Raio do DBSCAN geográfico, em metros.")
    cluster.add_argument("--min-samples", type=int, default=6, help="Mínimo de anúncios por concentração.")
    cluster.add_argument("--seed", type=int, default=42)
    build = sub.add_parser("build-app", help="Treinar o modelo final e gerar os artefatos do app.")
    build.add_argument("input", type=Path, help="Base unificada no contrato de dados.")
    build.add_argument("--output", required=True, type=Path, help="Pasta nova de artefatos (ex.: data/app/2026-11-09).")
    build.add_argument("--bairros", type=Path, default=BAIRROS_PATH)
    build.add_argument("--seed", type=int, default=42)
    app = sub.add_parser("app", help="Abrir o app Streamlit (mapa, filtros e simulador).")
    app.add_argument("--artefatos", required=True, type=Path, help="Pasta gerada por build-app.")
    app.add_argument("--port", type=int, default=8501)
    export = sub.add_parser("export-base", help="Gerar a base processada pública (sem endereço).")
    export.add_argument("input", type=Path, help="Base unificada no contrato de dados.")
    export.add_argument("--output", required=True, type=Path, help="CSV novo (ex.: data/processado/base_AAAA-MM-DD.csv).")
    export.add_argument("--bairros", type=Path, default=BAIRROS_PATH)
    regress = sub.add_parser("regress", help="Comparar regressores do aluguel em reais.")
    regress.add_argument("input", type=Path, help="Base unificada no contrato de dados.")
    regress.add_argument("--output", required=True, type=Path)
    regress.add_argument("--bairros", type=Path, default=BAIRROS_PATH)
    regress.add_argument("--seed", type=int, default=42)
    regress.add_argument("--repeticoes", type=int, default=0,
                         help="Repetir o experimento com N sementes (0..N-1) para medir estabilidade.")
    demo = sub.add_parser("demo", help="Preparar o que faltar (coleta, base, modelos) e abrir o app.")
    demo.add_argument("--dados", type=Path, default=Path("data"), help="Pasta de dados (padrão: data).")
    demo.add_argument("--atualizar", action="store_true",
                      help="Coletar anúncios novos hoje em vez de reaproveitar a base mais recente.")
    demo.add_argument("--port", type=int, default=8501)
    args = parser.parse_args(argv)
    if args.command == "demo":
        from .demo import run as run_demo
        return run_demo(args.dados, refresh=args.atualizar, port=args.port)
    if args.command == "regress":
        return _regress(args)
    if args.command == "export-base":
        return _export_base(args)
    if args.command == "build-app":
        return _build_app(args)
    if args.command == "app":
        return _run_app(args)
    if args.command == "cluster":
        return _cluster(args)
    if args.command == "classify":
        return _classify(args)
    if args.command == "collect":
        return _collect(args)
    if args.command == "merge":
        try:
            if args.output.exists():
                raise ValueError("o CSV de saída já existe; escolha outro nome.")
            total = merge_contract_csvs(args.inputs, args.output)
        except (OSError, ValueError) as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 2
        print(f"{total} anúncios de {len(args.inputs)} arquivos gravados em {args.output}")
        return 0
    created = False
    try:
        if args.output.exists():
            raise DataContractError("A pasta de saída já existe; escolha uma pasta nova.")
        imported = load_listings(args.input, sep=args.sep, decimal=args.decimal)
        rows, bairro_issues, bairros_info = imported.rows, imported.issues.iloc[0:0], None
        if args.bairros:
            if not args.bairros.exists():
                raise DataContractError(f"Arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
            rows, bairro_issues = assign_bairros(rows, BairroResolver(load_bairros(args.bairros)))
            bairros_info = {"arquivo": str(args.bairros), "sha256": _sha256(args.bairros),
                            "metodos": rows.bairro_metodo.value_counts().to_dict(),
                            "conflitos": int(rows.bairro_conflito.sum())}
        quality = audit_listings(rows)
        args.output.mkdir(parents=True, exist_ok=False)
        created = True
        # Import graphics only after validating input.
        from .eda import analyze_listings
        synthetic_input = bool(imported.rows.get("sintetico", pd.Series(dtype=str)).map(
            normalize_text).isin(["sim", "true", "1"]).any())
        eda = analyze_listings(quality.snapshot, args.output / "eda", synthetic_input=synthetic_input)
        quality.observations.to_csv(args.output / "observations.csv", index=False)
        quality.snapshot.to_csv(args.output / "snapshot.csv", index=False)
        pd.concat([imported.issues, bairro_issues, quality.issues], ignore_index=True).to_csv(args.output / "issues.csv", index=False)
        quality.summary["valores_invalidos_importacao"] = len(imported.issues)
        quality.summary["registros_rejeitados_estruturalmente"] = 0
        (args.output / "quality.json").write_text(
            json.dumps(quality.summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        manifest = {
            "source_sha256": imported.source_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parameters": {"sep": args.sep, "decimal": args.decimal},
            "bairros_oficiais": bairros_info,
            "versions": {"python": platform.python_version(), **{name: version(name) for name in ["imoveis-pg", "pandas", "numpy", "matplotlib", "geopandas"]}},
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _regress(args) -> int:
    from .modelagem.dataset import build_dataset, prepare_snapshot
    from .modelagem.regressao import regression_stability, run_regression
    from .modelagem.relatorio_regressao import MODEL_LABELS, write_regression_report

    try:
        if args.output.exists():
            raise ValueError("a pasta de saída já existe; escolha uma pasta nova.")
        if not args.bairros.exists():
            raise ValueError(f"arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
        data = build_dataset(prepare_snapshot(args.input, args.bairros))
        if len(data.X) < 30:
            raise ValueError(f"apenas {len(data.X)} casas elegíveis; insuficiente para treino e teste.")
        experiment = run_regression(data, seed=args.seed)
        dev_rent = data.y.loc[experiment.dev_index]
        bands = [float(q) for q in dev_rent.quantile([1 / 3, 2 / 3])]
        runs = regression_stability(data, seeds=range(args.repeticoes)) if args.repeticoes > 0 else None
        write_regression_report(experiment, data, args.output, band_limits=bands, stability_runs=runs,
                                manifest_extra={
            "entrada": str(args.input), "entrada_sha256": _sha256(args.input),
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "versoes": {"python": platform.python_version(),
                        **{n: version(n) for n in ["imoveis-pg", "scikit-learn", "pandas", "numpy"]}}})
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print(f"{len(data.X)} casas; treino {len(experiment.dev_index)}, teste {len(experiment.test_index)}. "
          "MAE em R$ (CV média ± desvio | teste) e MAPE no teste:")
    for row in experiment.metrics_table().itertuples():
        mark = "  <- selecionado" if row.selecionado else ""
        print(f"  {MODEL_LABELS.get(row.modelo, row.modelo):30s} {row.cv_mae_media:8.0f} ± {row.cv_mae_desvio:6.0f} | "
              f"{row.teste_mae:9.0f}  MAPE {row.teste_mape:.0%}{mark}")
    low, high = (np.exp(v) for v in experiment.interval_log)
    print(f"Intervalo de 80%: previsão × {low:.2f} a × {high:.2f}; cobertura no teste {experiment.interval_coverage:.0%}")
    print(f"Relatórios em {args.output.resolve()}")
    return 0


def _export_base(args) -> int:
    from .exportacao import COORDINATE_DECIMALS, public_table
    from .modelagem.dataset import prepare_snapshot

    try:
        if args.output.exists():
            raise ValueError("o CSV de saída já existe; escolha outro nome.")
        if not args.bairros.exists():
            raise ValueError(f"arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
        table = public_table(prepare_snapshot(args.input, args.bairros))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.output, index=False, encoding="utf-8")
        manifest = {"entrada_sha256": _sha256(args.input), "saida_sha256": _sha256(args.output),
                    "gerado_em": datetime.now(timezone.utc).isoformat(), "linhas": len(table),
                    "colunas": list(table.columns), "casas_elegiveis": int(table.elegivel_preliminar.sum()),
                    "coordenadas": f"arredondadas a {COORDINATE_DECIMALS} casas decimais (~100 m)",
                    "removido": "endereço, logradouro, número, CEP, valores originais e qualquer dado pessoal",
                    "formato": "CSV UTF-8, separador vírgula, decimal ponto"}
        args.output.with_name(args.output.stem + ".manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print(f"{len(table)} anúncios ({manifest['casas_elegiveis']} casas elegíveis) gravados em {args.output}")
    return 0


def _build_app(args) -> int:
    from .app.artefatos import build_artifacts

    try:
        if not args.bairros.exists():
            raise ValueError(f"arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
        meta = build_artifacts(args.input, args.bairros, args.output, seed=args.seed)
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    cv = meta["validacao_cruzada"]["balanced_accuracy"]
    reg = meta["regressao"]
    err, base = reg["validacao_fora_da_amostra"], reg["referencia_mediana_bairro"]
    print(f"Classificador {meta['modelo']} reajustado em {meta['n_casas_modelo']} casas; balanced accuracy na CV "
          f"{cv['media']:.3f} ± {cv['desvio']:.3f}.")
    print(f"Regressor {reg['modelo']}: MAE fora da amostra R$ {err['mae']:.0f} ({err['mape']:.0%}) contra "
          f"R$ {base['mae']:.0f} ({base['mape']:.0%}) da mediana do bairro; valor em reais "
          f"{'exibido' if reg['mostrar_valor'] else 'oculto'} no app.")
    print(f"Artefatos em {args.output.resolve()}")
    return 0


def _run_app(args) -> int:
    import subprocess

    if not (args.artefatos / "modelos.joblib").exists():
        print(f"Erro: {args.artefatos} não contém artefatos; rode build-app antes.", file=sys.stderr)
        return 2
    script = Path(__file__).parent / "app" / "streamlit_app.py"
    print(f"Abrindo o app em http://localhost:{args.port} (Ctrl+C para encerrar)")
    # headless: não pergunta e-mail nem abre navegador; estatísticas de uso desativadas.
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(args.port),
                            "--server.headless", "true", "--browser.gatherUsageStats", "false",
                            "--", "--artefatos", str(args.artefatos.resolve())])


def _cluster(args) -> int:
    from .modelagem.agrupamento import cluster_profiles, cluster_space
    from .modelagem.dataset import build_dataset, prepare_snapshot
    from .modelagem.relatorio_agrupamento import ALGORITHM_LABELS, write_cluster_report

    try:
        if args.output.exists():
            raise ValueError("a pasta de saída já existe; escolha uma pasta nova.")
        if not args.bairros.exists():
            raise ValueError(f"arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
        data = build_dataset(prepare_snapshot(args.input, args.bairros))
        if len(data.X) < 30:
            raise ValueError(f"apenas {len(data.X)} casas elegíveis; insuficiente para agrupar.")
        profiles = cluster_profiles(data, seed=args.seed)
        spatial = cluster_space(data, eps_m=args.eps_m, min_samples=args.min_samples)
        manifest = write_cluster_report(profiles, spatial, data, args.output, bairros=load_bairros(args.bairros),
                                        manifest_extra={
            "entrada": str(args.input), "entrada_sha256": _sha256(args.input), "semente": args.seed,
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "versoes": {"python": platform.python_version(),
                        **{n: version(n) for n in ["imoveis-pg", "scikit-learn", "pandas", "numpy"]}}})
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print(f"Perfis ({len(profiles.table)} casas com área, quartos e banheiros):")
    for name, chosen in profiles.chosen.items():
        config = f"k={int(chosen['k'])}" if "k" in chosen else f"eps={chosen['eps']:.1f}, min_samples={int(chosen['min_samples'])}"
        print(f"  {ALGORITHM_LABELS[name]:20s} {config:24s} silhueta {chosen['silhueta']:.3f}  "
              f"estabilidade {chosen['estabilidade']:.3f}  ruído {chosen['ruido']:.0%}")
    regioes = manifest["regioes"]
    print(f"Concentrações espaciais: {regioes['n_concentracoes']} (raio {args.eps_m:.0f} m, "
          f"≥ {args.min_samples} anúncios), {regioes['ruido']:.0%} dispersos, "
          f"ARI com bairros {regioes['ari_concentracao_x_bairro']:.2f}")
    print(f"Relatórios em {args.output.resolve()}")
    return 0


def _classify(args) -> int:
    from .modelagem.classificacao import run_experiment, stability
    from .modelagem.dataset import build_dataset, prepare_snapshot
    from .modelagem.relatorio import MODEL_LABELS, write_report

    try:
        if args.output.exists():
            raise ValueError("a pasta de saída já existe; escolha uma pasta nova.")
        if not args.bairros.exists():
            raise ValueError(f"arquivo de bairros não encontrado: {args.bairros} (fonte: {BAIRROS_URL})")
        data = build_dataset(prepare_snapshot(args.input, args.bairros))
        if len(data.X) < 30:
            raise ValueError(f"apenas {len(data.X)} casas elegíveis; insuficiente para treino e teste.")
        experiment = run_experiment(data, n_bands=args.faixas, seed=args.seed)
        runs = stability(data, n_bands=args.faixas, seeds=range(args.repeticoes)) if args.repeticoes > 0 else None
        write_report(experiment, data, args.output, stability_runs=runs, manifest_extra={
            "entrada": str(args.input), "entrada_sha256": _sha256(args.input),
            "bairros_sha256": _sha256(args.bairros), "gerado_em": datetime.now(timezone.utc).isoformat(),
            "versoes": {"python": platform.python_version(),
                        **{n: version(n) for n in ["imoveis-pg", "scikit-learn", "pandas", "numpy"]}}})
    except (DataContractError, OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    table = experiment.metrics_table()
    print(f"{len(data.X)} casas; {args.faixas} faixas; treino {len(experiment.dev_index)}, "
          f"teste {len(experiment.test_index)}. Balanced accuracy (CV média ± desvio | teste):")
    for row in table.itertuples():
        mark = "  <- selecionado" if row.selecionado else ""
        print(f"  {MODEL_LABELS.get(row.modelo, row.modelo):28s} {row.cv_balanced_accuracy_media:.3f} ± "
              f"{row.cv_balanced_accuracy_desvio:.3f} | {row.teste_balanced_accuracy:.3f}{mark}")
    print(f"Relatórios em {args.output.resolve()}")
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
    geocoding = None
    if any(not (r.get("latitude") and r.get("longitude")) for r in result.records):
        try:
            cnefe = client.download(CNEFE_URL, args.cnefe)
            bairros = client.download(BAIRROS_URL, args.bairros)
        except ColetaError as exc:
            print(f"Erro ao obter CNEFE ou bairros do IBGE para geocodificar: {exc}", file=sys.stderr)
            return 2
        resolver = BairroResolver(load_bairros(bairros))
        geocoding = {"fonte": "IBGE CNEFE 2022", "arquivo": str(cnefe), "sha256": _sha256(cnefe),
                     "bairros": {"arquivo": str(bairros), "sha256": _sha256(bairros)},
                     "metodos": geocode_records(result.records, CnefeGeocoder.from_zip(cnefe), resolver)}
    write_contract_csv(result.records, args.output)
    manifest = {
        "fonte": module.FONTE, "url_base": module.BASE_URL, "coletor": args.source,
        "gerado_em": datetime.now(timezone.utc).isoformat(), "user_agent": USER_AGENT,
        "intervalo_s": args.delay, "paginas": result.pages, "max_paginas": args.max_pages,
        "total_declarado_pelo_site": result.declared_total, "anuncios": len(result.records),
        "descartados": result.skipped, "requisicoes": client.requests_made,
        "paginas_do_cache": client.cache_hits, "cache": str(cache_dir),
        "geocodificacao": geocoding,
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
