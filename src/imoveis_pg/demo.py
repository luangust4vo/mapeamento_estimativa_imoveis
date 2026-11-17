"""Comando único: prepara o que faltar (coleta, base unificada, modelos) e abre o app.

Reaproveita o que já existe em ``data/``: com base e artefatos prontos, só abre o app.
Cada etapa é um dos comandos normais da CLI, executados em sequência.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .coleta import SOURCES

DATE = r"\d{4}-\d{2}-\d{2}"


def latest_base(data_dir: Path) -> Path | None:
    """Base unificada mais recente (data/base_AAAA-MM-DD.csv)."""
    bases = sorted(p for p in Path(data_dir).glob("base_*.csv") if re.fullmatch(f"base_{DATE}.csv", p.name))
    return bases[-1] if bases else None


def plan(data_dir: Path, *, today: date, refresh: bool = False, port: int = 8501) -> list[list[str]]:
    """Lista de comandos da CLI necessários para abrir o app, pulando o que já existe."""
    data_dir = Path(data_dir)
    today_base = data_dir / f"base_{today.isoformat()}.csv"
    # Com --atualizar, só a base de hoje serve; sem ele, a mais recente que existir.
    base = (today_base if today_base.exists() else None) if refresh else latest_base(data_dir)
    steps: list[list[str]] = []
    if base is None:
        parts = [data_dir / f"{source}_{today.isoformat()}.csv" for source in sorted(SOURCES)]
        # Fontes já coletadas hoje (ex.: execução interrompida) não são coletadas de novo.
        steps += [["collect", source, "--output", str(part)]
                  for source, part in zip(sorted(SOURCES), parts) if not part.exists()]
        base = today_base
        steps.append(["merge", *map(str, parts), "--output", str(base)])
    stamp = re.search(DATE, base.name).group(0)
    artifacts = data_dir / "app" / stamp
    if not (artifacts / "modelos.joblib").exists():
        steps.append(["build-app", str(base), "--output", str(artifacts)])
    steps.append(["app", "--artefatos", str(artifacts), "--port", str(port)])
    return steps


def describe(step: list[str]) -> str:
    return {"collect": f"Coletando anúncios de {step[1]}", "merge": "Unindo as fontes numa base única",
            "build-app": "Treinando os modelos do app (cerca de 1 minuto)",
            "app": "Abrindo o app"}.get(step[0], step[0])


def run(data_dir: Path, *, refresh: bool = False, port: int = 8501, today: date | None = None, runner=None) -> int:
    from .__main__ import main

    runner = runner or main
    steps = plan(data_dir, today=today or date.today(), refresh=refresh, port=port)
    pending = [s for s in steps if s[0] != "app"]
    if pending:
        print(f"{len(pending)} etapa(s) antes de abrir o app:")
    else:
        print("Dados e modelos já prontos; abrindo o app.")
    for number, step in enumerate(steps, start=1):
        print(f"[{number}/{len(steps)}] {describe(step)}…", flush=True)
        code = runner(step)
        if code:
            print(f"Erro na etapa '{' '.join(step)}'. Corrija o problema e rode o demo de novo: "
                  "as etapas concluídas não serão repetidas.")
            return code
    return 0
