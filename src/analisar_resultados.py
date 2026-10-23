"""Consolida os resultados dos experimentos do Locust."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import fmean


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR.parent / "results"
RUNS_FILE = RESULTS_DIR / "execucoes.csv"
LOCUST_DIR = RESULTS_DIR / "raw" / "locust"
MONITORAMENTO_DIR = RESULTS_DIR / "raw" / "monitoramento"
TABLES_DIR = RESULTS_DIR / "tabelas"
CHARTS_DIR = RESULTS_DIR / "graficos"
METRICS = ("media_ms", "p95_ms", "vazao_req_s", "requisicoes", "falhas", "falhas_pct")
AQUECIMENTO_SEGUNDOS = 60


def number(value: str) -> float:
    return float((value or "0").replace(",", "."))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def mean_rows(rows: list[dict], fields: tuple[str, ...]) -> dict:
    return {field: fmean(float(row[field]) for row in rows) for field in fields}


def stats_rows(run: dict[str, str]) -> list[dict]:
    path = LOCUST_DIR / f"{run['csv_prefix']}_stats.csv"
    rows = []
    for source in read_csv(path):
        requests = number(source["Request Count"])
        failures = number(source["Failure Count"])
        rows.append({
            "perfil": run["perfil"], "cenario": run["cenario"], "usuarios": int(run["usuarios"]),
            "repeticao": int(run["repeticao"]), "operacao": source["Name"].strip(),
            "media_ms": number(source["Average Response Time"]), "p95_ms": number(source["95%"]),
            "vazao_req_s": number(source["Requests/s"]), "requisicoes": requests,
            "falhas": failures, "falhas_pct": failures * 100 / requests if requests else 0,
        })
    return rows


def cpu_rows(run: dict[str, str]) -> list[dict]:
    path = MONITORAMENTO_DIR / f"{run['csv_prefix']}_cpu.csv"
    inicio_medicao = datetime.fromisoformat(run["inicio"]) + timedelta(seconds=AQUECIMENTO_SEGUNDOS)
    fim_medicao = datetime.fromisoformat(run["fim"])
    values: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in read_csv(path):
        timestamp = datetime.fromisoformat(row["timestamp"])
        if inicio_medicao <= timestamp <= fim_medicao:
            values[row["container"]].append((number(row["cpu_percent"]), number(row["memory_percent"])))
    return [
        {"perfil": run["perfil"], "cenario": run["cenario"], "usuarios": int(run["usuarios"]),
         "repeticao": int(run["repeticao"]), "servico": service,
         "cpu_pct": fmean(cpu for cpu, _ in samples),
         "memoria_pct": fmean(memory for _, memory in samples)}
        for service, samples in values.items() if samples
    ]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f"{value:.2f}" if isinstance(value, float) else value for key, value in row.items()})


def summarize(stats: list[dict], cpu: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    scenario_groups: dict[tuple, list[dict]] = defaultdict(list)
    operation_groups: dict[tuple, list[dict]] = defaultdict(list)
    cpu_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in stats:
        key = (row["perfil"], row["cenario"], row["usuarios"])
        if row["operacao"] == "Aggregated":
            scenario_groups[key].append(row)
        else:
            operation_groups[key + (row["operacao"],)].append(row)
    for row in cpu:
        cpu_groups[(row["perfil"], row["cenario"], row["usuarios"], row["servico"])].append(row)
    scenarios = [
        {"perfil": key[0], "cenario": key[1], "usuarios": key[2], "repeticoes": len(rows), **mean_rows(rows, METRICS)}
        for key, rows in sorted(scenario_groups.items())
    ]
    operations = [
        {"perfil": key[0], "cenario": key[1], "usuarios": key[2], "operacao": key[3], "repeticoes": len(rows), **mean_rows(rows, METRICS)}
        for key, rows in sorted(operation_groups.items())
    ]
    cpus = [
        {"perfil": key[0], "cenario": key[1], "usuarios": key[2], "servico": key[3], "repeticoes": len(rows),
         "cpu_pct": fmean(row["cpu_pct"] for row in rows),
         "memoria_pct": fmean(row["memoria_pct"] for row in rows)}
        for key, rows in sorted(cpu_groups.items())
    ]
    return scenarios, operations, cpus


def chart_data(plt, rows: list[dict], metric: str, title: str, ylabel: str, filename: str) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    for profile in ("leitura", "escrita"):
        items = sorted((row for row in rows if row["perfil"] == profile), key=lambda row: row["usuarios"])
        if items:
            axis.plot([row["usuarios"] for row in items], [row[metric] for row in items], marker="o", label=profile.title())
    axis.set(title=title, xlabel="Usuários", ylabel=ylabel)
    axis.grid(alpha=.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(CHARTS_DIR / filename, dpi=160)
    plt.close(figure)


def create_charts(scenarios: list[dict], cpus: list[dict]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não está instalado; tabelas foram geradas sem gráficos.")
        return
    chart_data(plt, scenarios, "media_ms", "Tempo médio de resposta", "ms", "tempo_medio.png")
    chart_data(plt, scenarios, "p95_ms", "P95 de resposta", "ms", "p95.png")
    chart_data(plt, scenarios, "vazao_req_s", "Vazão", "requisições/s", "vazao.png")
    chart_data(plt, scenarios, "falhas_pct", "Taxa de falhas", "%", "taxa_falhas.png")
    for service in sorted({row["servico"] for row in cpus}):
        chart_data(plt, [row for row in cpus if row["servico"] == service], "memoria_pct", f"Memória média: {service}", "%", f"memoria_{service}.png")
        chart_data(plt, [row for row in cpus if row["servico"] == service], "cpu_pct", f"CPU média: {service}", "%", f"cpu_{service}.png")


def write_analysis(scenarios: list[dict], operations: list[dict], cpus: list[dict]) -> None:
    highest_failure = max(scenarios, key=lambda row: row["falhas_pct"])
    highest_throughput = max(scenarios, key=lambda row: row["vazao_req_s"])
    slowest_operation = max(operations, key=lambda row: row["media_ms"])
    lines = [
        "# Análise dos resultados", "",
        "As tabelas apresentam a média das repetições concluídas por perfil e cenário.", "",
        "## Respostas às questões", "",
        f"1. O efeito da quantidade de usuários está detalhado em `tabelas/cenarios.csv` e `graficos/tempo_medio.png`.",
        f"2. A maior vazão observada foi no perfil **{highest_throughput['perfil']}**, cenário **{highest_throughput['cenario']}** ({highest_throughput['vazao_req_s']:.2f} requisições/s).",
        f"3. A maior média por operação foi **{slowest_operation['operacao']}** no perfil **{slowest_operation['perfil']}**, cenário **{slowest_operation['cenario']}** ({slowest_operation['media_ms']:.2f} ms).",
        "4. A variação da CPU por serviço está em `tabelas/cpu.csv` e nos gráficos `cpu_*.png`.",
        f"5. A maior taxa de falhas ocorreu no perfil **{highest_failure['perfil']}**, cenário **{highest_failure['cenario']}** ({highest_failure['falhas_pct']:.2f}%).",
    ]
    (RESULTS_DIR / "analise_resultados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not RUNS_FILE.exists():
        raise SystemExit(f"Não encontrei {RUNS_FILE}")
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    runs = [row for row in read_csv(RUNS_FILE) if row["status"] == "CONCLUIDA"]
    if not runs:
        raise SystemExit("Não há execuções concluídas para analisar.")
    stats = [item for run in runs for item in stats_rows(run)]
    cpu = [item for run in runs for item in cpu_rows(run)]
    scenarios, operations, cpus = summarize(stats, cpu)
    write_csv(TABLES_DIR / "cenarios.csv", scenarios)
    write_csv(TABLES_DIR / "operacoes.csv", operations)
    write_csv(TABLES_DIR / "cpu.csv", cpus)
    create_charts(scenarios, cpus)
    write_analysis(scenarios, operations, cpus)
    print(f"Tabelas, gráficos e análise gerados em {RESULTS_DIR}")


if __name__ == "__main__":
    main()
