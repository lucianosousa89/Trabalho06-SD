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
CPU_SERVICES = ("customers-service", "vets-service")
SCENARIO_TICKS = ((30, "A — 30"), (80, "B — 80"), (150, "C — 150"))
PROFILE_COLORS = {"leitura": "#0072B2", "escrita": "#D55E00"}
ANNOTATION_OVERLAP_FILES = {
    "p95.png",
    "requisicoes.png",
    "taxa_falhas.png",
    "tempo_medio.png",
    "vazao.png",
}
OPERATION_LABELS = {
    "/api/customer/owners": "GET /owners",
    "/api/customer/owners [POST]": "POST /owners",
    "/api/customer/owners/[id]": "GET /owners/{id}",
    "/api/vet/vets": "GET /vets",
}
OPERATION_ORDER = tuple(OPERATION_LABELS)
EXPECTED_RUNS = {
    (profile, scenario, users, repetition)
    for profile in ("leitura", "escrita")
    for scenario, users in (("A", 30), ("B", 80), ("C", 150))
    for repetition in range(1, 11)
}


def number(value: str) -> float:
    return float((value or "0").replace(",", "."))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def validate_runs(runs: list[dict[str, str]]) -> None:
    """Require the complete experiment matrix and the raw inputs it needs."""
    keys = [
        (run["perfil"], run["cenario"], int(run["usuarios"]), int(run["repeticao"]))
        for run in runs
    ]
    duplicated = {key for key in keys if keys.count(key) > 1}
    missing = EXPECTED_RUNS - set(keys)
    unexpected = set(keys) - EXPECTED_RUNS
    if duplicated or missing or unexpected:
        details = []
        if duplicated:
            details.append(f"repetições duplicadas: {sorted(duplicated)}")
        if missing:
            details.append(f"repetições ausentes: {sorted(missing)}")
        if unexpected:
            details.append(f"repetições inesperadas: {sorted(unexpected)}")
        raise SystemExit("Bateria incompleta ou inconsistente; " + "; ".join(details))
    absent = []
    for run in runs:
        prefix = run["csv_prefix"]
        for path in (
            LOCUST_DIR / f"{prefix}_stats.csv",
            MONITORAMENTO_DIR / f"{prefix}_cpu.csv",
        ):
            if not path.exists():
                absent.append(str(path))
    if absent:
        raise SystemExit("Arquivos brutos ausentes:\n" + "\n".join(absent))


def aggregate_metric_rows(rows: list[dict]) -> dict:
    """Aggregate repetitions without turning totals into averages."""
    total_requests = sum(row["requisicoes"] for row in rows)
    total_failures = sum(row["falhas"] for row in rows)
    weighted_average = (
        sum(row["media_ms"] * row["requisicoes"] for row in rows) / total_requests
        if total_requests else 0
    )
    return {
        "media_ms": weighted_average,
        "p95_ms": fmean(row["p95_ms"] for row in rows),
        "vazao_req_s": fmean(row["vazao_req_s"] for row in rows),
        "requisicoes": total_requests,
        "falhas": total_failures,
        "falhas_pct": total_failures * 100 / total_requests if total_requests else 0,
    }


def stats_rows(run: dict[str, str]) -> list[dict]:
    path = LOCUST_DIR / f"{run['csv_prefix']}_stats.csv"
    rows = []
    for source in read_csv(path):
        requests = int(number(source["Request Count"]))
        failures = int(number(source["Failure Count"]))
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
        if row["container"] not in CPU_SERVICES:
            continue
        timestamp = datetime.fromisoformat(row["timestamp"])
        if inicio_medicao <= timestamp <= fim_medicao:
            values[row["container"]].append((number(row["cpu_percent"]), number(row["memory_percent"])))
    result = [
        {"perfil": run["perfil"], "cenario": run["cenario"], "usuarios": int(run["usuarios"]),
         "repeticao": int(run["repeticao"]), "servico": service,
         "cpu_pct": fmean(cpu for cpu, _ in samples),
         "memoria_pct": fmean(memory for _, memory in samples)}
        for service, samples in values.items() if samples
    ]
    if {row["servico"] for row in result} != set(CPU_SERVICES):
        raise SystemExit(
            f"Execução {run['csv_prefix']} não possui CPU dos serviços exigidos: "
            f"{', '.join(CPU_SERVICES)}."
        )
    return result


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
        {"perfil": key[0], "cenario": key[1], "usuarios": key[2],
         "repeticoes": len(rows), **aggregate_metric_rows(rows)}
        for key, rows in sorted(scenario_groups.items())
    ]
    operations = [
        {"perfil": key[0], "cenario": key[1], "usuarios": key[2], "operacao": key[3],
         "repeticoes": len(rows), **aggregate_metric_rows(rows)}
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
    """Cria um gráfico comparativo dos três cenários para os dois perfis."""
    figure, axis = plt.subplots(figsize=(9, 5.5))
    scenario_a_values = {
        row["perfil"]: row[metric]
        for row in rows
        if row["usuarios"] == 30
    }
    for profile in ("leitura", "escrita"):
        items = sorted((row for row in rows if row["perfil"] == profile), key=lambda row: row["usuarios"])
        if items:
            users = [row["usuarios"] for row in items]
            values = [row[metric] for row in items]
            axis.plot(
                users, values, marker="o", markersize=7, linewidth=2.4,
                color=PROFILE_COLORS[profile], label=profile.title(),
            )
            for user, value in zip(users, values):
                # No cenário A desses gráficos, os valores dos perfis são muito
                # próximos. O maior fica acima e o menor abaixo para não sobrepô-los.
                label_offset = (0, 8)
                if filename in ANNOTATION_OVERLAP_FILES and user == 30:
                    if value < max(scenario_a_values.values()):
                        label_offset = (0, -14)
                axis.annotate(
                    f"{value:.1f}", (user, value), textcoords="offset points",
                    xytext=label_offset, ha="center", fontsize=8,
                    color=PROFILE_COLORS[profile],
                )
    axis.set(title=title, xlabel="Cenário (usuários)", ylabel=ylabel)
    axis.set_xticks([users for users, _ in SCENARIO_TICKS], [label for _, label in SCENARIO_TICKS])
    axis.set_xlim(24, 156)
    axis.grid(axis="y", alpha=.3)
    axis.legend(title="Perfil", frameon=True)
    figure.tight_layout()
    figure.savefig(CHARTS_DIR / filename, dpi=160)
    plt.close(figure)


def operation_chart(plt, operations: list[dict], profile: str) -> None:
    """Mostra cada endpoint em um painel para não ocultar operações rápidas."""
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    profile_rows = [row for row in operations if row["perfil"] == profile]
    for axis, operation in zip(axes.flat, OPERATION_ORDER):
        items = sorted(
            (row for row in profile_rows if row["operacao"] == operation),
            key=lambda row: row["usuarios"],
        )
        if items:
            users = [row["usuarios"] for row in items]
            values = [row["media_ms"] for row in items]
            axis.plot(users, values, marker="o", markersize=6, linewidth=2.2, color=PROFILE_COLORS[profile])
            for user, value in zip(users, values):
                axis.annotate(
                    f"{value:.1f}", (user, value), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=8,
                )
        axis.set_title(OPERATION_LABELS[operation], fontsize=11, fontweight="bold")
        axis.set_ylabel("Tempo médio (ms)")
        axis.set_xticks([users for users, _ in SCENARIO_TICKS], [label for _, label in SCENARIO_TICKS])
        axis.set_xlim(24, 156)
        axis.grid(axis="y", alpha=.3)
    figure.suptitle(f"Tempo médio por operação — perfil {profile}", fontsize=14, fontweight="bold")
    figure.tight_layout(rect=(0, 0, 1, .95))
    figure.savefig(CHARTS_DIR / f"operacoes_tempo_medio_{profile}.png", dpi=160)
    plt.close(figure)


def markdown_table(rows: list[dict], columns: tuple[tuple[str, str], ...]) -> str:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        values = []
        for field, _ in columns:
            value = row[field]
            if isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join((header, separator, *body))


def write_analysis(scenarios: list[dict], operations: list[dict], cpus: list[dict]) -> None:
    """Write an academic, reproducible interpretation of the experiment."""
    scenario_index = {(row["perfil"], row["cenario"]): row for row in scenarios}
    cpu_index = {(row["perfil"], row["cenario"], row["servico"]): row for row in cpus}
    operation_index = {
        (row["perfil"], row["cenario"], row["operacao"]): row for row in operations
    }

    load_comparisons = []
    for profile in ("leitura", "escrita"):
        low = scenario_index[(profile, "A")]
        high = scenario_index[(profile, "C")]
        average_change = (
            (high["media_ms"] - low["media_ms"]) * 100 / low["media_ms"]
            if low["media_ms"] else 0
        )
        p95_change = (
            (high["p95_ms"] - low["p95_ms"]) * 100 / low["p95_ms"]
            if low["p95_ms"] else 0
        )
        load_comparisons.append(
            f"- **{profile.capitalize()}**: o tempo médio aumentou de "
            f"{low['media_ms']:.2f} ms para {high['media_ms']:.2f} ms "
            f"(+{average_change:.2f}%), enquanto o P95 passou de "
            f"{low['p95_ms']:.2f} ms para {high['p95_ms']:.2f} ms "
            f"(+{p95_change:.2f}%)."
        )

    degradations = []
    for profile in ("leitura", "escrita"):
        operation_names = {
            row["operacao"] for row in operations if row["perfil"] == profile
        }
        for operation in operation_names:
            low = operation_index.get((profile, "A", operation))
            high = operation_index.get((profile, "C", operation))
            if low and high:
                absolute = high["media_ms"] - low["media_ms"]
                relative = absolute * 100 / low["media_ms"] if low["media_ms"] else 0
                degradations.append((absolute, relative, profile, operation, low, high))
    degradations.sort(reverse=True)
    greatest_degradation = degradations[0]
    slowest_operation = max(operations, key=lambda row: row["media_ms"])
    highest_failure = max(scenarios, key=lambda row: row["falhas_pct"])
    highest_cpu = max(cpus, key=lambda row: row["cpu_pct"])

    throughput_by_profile = {
        profile: fmean(row["vazao_req_s"] for row in scenarios if row["perfil"] == profile)
        for profile in ("leitura", "escrita")
    }
    highest_throughput_profile = max(throughput_by_profile, key=throughput_by_profile.get)
    throughput_change = []
    for profile in ("leitura", "escrita"):
        low = scenario_index[(profile, "A")]
        high = scenario_index[(profile, "C")]
        change = (
            (high["vazao_req_s"] - low["vazao_req_s"]) * 100 / low["vazao_req_s"]
            if low["vazao_req_s"] else 0
        )
        throughput_change.append(
            f"- **{profile.capitalize()}**: {low['vazao_req_s']:.2f} para "
            f"{high['vazao_req_s']:.2f} requisições/s ({change:+.2f}%)."
        )

    cpu_comparisons = []
    for service in CPU_SERVICES:
        for profile in ("leitura", "escrita"):
            low = cpu_index[(profile, "A", service)]
            high = cpu_index[(profile, "C", service)]
            cpu_comparisons.append(
                f"- **{service} — {profile}**: {low['cpu_pct']:.2f}% no cenário A "
                f"e {high['cpu_pct']:.2f}% no cenário C."
            )

    scenario_columns = (
        ("perfil", "Perfil"),
        ("cenario", "Cenário"),
        ("usuarios", "Usuários"),
        ("media_ms", "Média (ms)"),
        ("p95_ms", "P95 (ms)"),
        ("vazao_req_s", "Vazão (req/s)"),
        ("requisicoes", "Requisições"),
        ("falhas", "Falhas"),
        ("falhas_pct", "Falhas (%)"),
    )
    cpu_columns = (
        ("perfil", "Perfil"),
        ("cenario", "Cenário"),
        ("usuarios", "Usuários"),
        ("servico", "Serviço"),
        ("cpu_pct", "CPU (%)"),
        ("memoria_pct", "Memória (%)"),
    )
    operation_columns = (
        ("perfil", "Perfil"),
        ("cenario", "Cenário"),
        ("usuarios", "Usuários"),
        ("operacao", "Operação"),
        ("media_ms", "Média (ms)"),
        ("p95_ms", "P95 (ms)"),
        ("falhas_pct", "Falhas (%)"),
    )

    report = [
        "# Análise dos resultados",
        "",
        "## 1. Objetivo e delineamento experimental",
        "",
        "Este estudo avalia o comportamento do sistema de microsserviços "
        "Spring PetClinic sob diferentes níveis de concorrência. Foram comparados "
        "os perfis de carga **leitura** e **escrita** em três cenários: A (30 usuários), "
        "B (80 usuários) e C (150 usuários), com dez repetições por combinação.",
        "Cada repetição teve 60 segundos de aquecimento, seguidos do período de medição. "
        "A utilização de CPU foi analisada exclusivamente para `customers-service` e "
        "`vets-service`.",
        "",
        "## 2. Procedimento de análise",
        "",
        "Os arquivos CSV produzidos pelo Locust foram consolidados por perfil e cenário. "
        "A latência média foi ponderada pelo número de requisições; P95 e vazão foram "
        "calculados como a média dos valores reportados nas repetições. Requisições e "
        "falhas foram somadas, e a taxa de falhas foi recalculada sobre esses totais. "
        "Para CPU, foram utilizadas as amostras coletadas após o aquecimento.",
        "Essa estratégia evita que repetições com volumes distintos tenham o mesmo peso "
        "na média de latência e preserva a interpretação dos totais de requisições.",
        "",
        "## 3. Resultados consolidados",
        "",
        markdown_table(scenarios, scenario_columns),
        "",
        "A tabela evidencia que o aumento da concorrência produz efeitos distintos "
        "nos dois perfis. O perfil de escrita apresenta maior sensibilidade à carga, "
        "especialmente no cenário C, no qual a latência de cauda e a taxa de falhas "
        "crescem de forma acentuada.",
        "",
        "### 3.1 Comparação por operação",
        "",
        markdown_table(operations, operation_columns),
        "",
        f"A maior latência média foi observada na operação "
        f"`{slowest_operation['operacao']}`, no perfil {slowest_operation['perfil']} "
        f"e cenário {slowest_operation['cenario']}, com "
        f"{slowest_operation['media_ms']:.2f} ms. A maior degradação entre os cenários "
        f"A e C ocorreu em `{greatest_degradation[3]}` no perfil "
        f"{greatest_degradation[2]}: de {greatest_degradation[4]['media_ms']:.2f} ms "
        f"para {greatest_degradation[5]['media_ms']:.2f} ms, aumento absoluto de "
        f"{greatest_degradation[0]:.2f} ms ({greatest_degradation[1]:.2f}%).",
        "",
        "### 3.2 Utilização dos serviços",
        "",
        markdown_table(cpus, cpu_columns),
        "",
        f"A maior utilização média de CPU foi registrada no "
        f"`{highest_cpu['servico']}`, no perfil {highest_cpu['perfil']} e cenário "
        f"{highest_cpu['cenario']}, atingindo {highest_cpu['cpu_pct']:.2f}%. "
        "A comparação entre os cenários extremos é apresentada abaixo:",
        *cpu_comparisons,
        "",
        "## 4. Discussão das questões de pesquisa",
        "",
        "### 4.1 Efeito do aumento de usuários sobre o tempo de resposta",
        "",
        *load_comparisons,
        "O crescimento simultâneo da média e do P95 indica não apenas aumento do "
        "tempo típico, mas também maior variabilidade e degradação da cauda da "
        "distribuição de latências. Esse efeito é mais pronunciado no perfil de escrita.",
        "",
        "### 4.2 Perfil com maior vazão",
        "",
        f"A maior vazão média entre os três cenários pertence ao perfil "
        f"**{highest_throughput_profile}**, com "
        f"{throughput_by_profile[highest_throughput_profile]:.2f} requisições/s. "
        "A evolução entre os cenários extremos foi:",
        *throughput_change,
        "A maior vazão observada em um cenário individual foi "
        f"{max(scenarios, key=lambda row: row['vazao_req_s'])['vazao_req_s']:.2f} "
        "requisições/s, no cenário de maior carga do perfil de leitura.",
        "",
        "### 4.3 Operações com maior degradação",
        "",
        "A degradação concentra-se nas operações de clientes, sobretudo no perfil "
        "de escrita. O resultado sugere que as operações que modificam o estado "
        "do sistema são mais suscetíveis à contenção e ao aumento do tempo de "
        "processamento sob concorrência elevada.",
        "",
        "### 4.4 Variação do consumo de CPU",
        "",
        "A CPU não cresce necessariamente de forma linear com o número de usuários. "
        "No `customers-service`, o salto entre A e C é expressivo, enquanto o "
        "`vets-service` apresenta variação menor. Essa diferença indica que os "
        "serviços possuem sensibilidades distintas ao perfil de carga e que o "
        "customers-service constitui o principal ponto de atenção no cenário C.",
        "",
        "### 4.5 Cenário com maior taxa de falhas",
        "",
        f"A maior taxa de falhas ocorreu no perfil **{highest_failure['perfil']}**, "
        f"cenário **{highest_failure['cenario']}**, com "
        f"{highest_failure['falhas_pct']:.2f}% ({highest_failure['falhas']} falhas "
        f"em {highest_failure['requisicoes']} requisições). O resultado caracteriza "
        "perda de confiabilidade sob carga elevada e deve ser analisado conjuntamente "
        "com o crescimento do P95 e da utilização de CPU.",
        "",
        "## 5. Considerações metodológicas e limitações",
        "",
        "- O P95 apresentado é a média dos P95 das repetições, e não um percentil "
        "recalculado sobre todas as amostras brutas.",
        "- A vazão representa a média dos valores reportados pelo Locust durante "
        "cada repetição.",
        "- A utilização de CPU do Docker pode ultrapassar 100% quando expressa "
        "relativamente a um único núcleo; portanto, valores superiores a 100% "
        "representam uso agregado de múltiplos núcleos.",
        "- Os resultados descrevem o ambiente experimental executado e não devem "
        "ser generalizados para infraestruturas com configuração distinta.",
        "",
        "## 6. Conclusão",
        "",
        "Os resultados demonstram que o aumento de usuários deteriora principalmente "
        "a latência de cauda e a taxa de falhas do perfil de escrita. O perfil de "
        "leitura sustenta maior vazão média, enquanto o `customers-service` concentra "
        "o maior consumo de CPU entre os dois serviços monitorados. Assim, o cenário C "
        "representa o limite de maior criticidade da bateria, devendo orientar ações "
        "de otimização, dimensionamento e investigação das operações de escrita.",
        "",
        "Os gráficos correspondentes estão disponíveis em `graficos/`, e as tabelas "
        "completas em `tabelas/`.",
    ]
    (RESULTS_DIR / "analise_resultados.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def create_charts(scenarios: list[dict], operations: list[dict], cpus: list[dict]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não está instalado; tabelas foram geradas sem gráficos.")
        return
    chart_data(plt, scenarios, "media_ms", "Tempo médio de resposta", "ms", "tempo_medio.png")
    chart_data(plt, scenarios, "p95_ms", "P95 de resposta", "ms", "p95.png")
    chart_data(plt, scenarios, "vazao_req_s", "Vazão", "requisições/s", "vazao.png")
    chart_data(plt, scenarios, "requisicoes", "Total de requisições", "requisições", "requisicoes.png")
    chart_data(plt, scenarios, "falhas_pct", "Taxa de falhas", "%", "taxa_falhas.png")
    old_operation_chart = CHARTS_DIR / "operacoes_tempo_medio.png"
    if old_operation_chart.exists():
        old_operation_chart.unlink()
    for profile in ("leitura", "escrita"):
        operation_chart(plt, operations, profile)
    for old_service in {"api-gateway", "config-server", "discovery-server"}:
        for prefix in ("cpu", "memoria"):
            old_chart = CHARTS_DIR / f"{prefix}_{old_service}.png"
            if old_chart.exists():
                old_chart.unlink()
    for service in CPU_SERVICES:
        chart_data(plt, [row for row in cpus if row["servico"] == service], "cpu_pct", f"CPU média: {service}", "%", f"cpu_{service}.png")


def main() -> None:
    if not RUNS_FILE.exists():
        raise SystemExit(f"Não encontrei {RUNS_FILE}")
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    runs = [row for row in read_csv(RUNS_FILE) if row["status"] == "CONCLUIDA"]
    if not runs:
        raise SystemExit("Não há execuções concluídas para analisar.")
    validate_runs(runs)
    stats = [item for run in runs for item in stats_rows(run)]
    cpu = [item for run in runs for item in cpu_rows(run)]
    if {row["servico"] for row in cpu} != set(CPU_SERVICES):
        raise SystemExit(
            "A análise de CPU exige exclusivamente os serviços: "
            + ", ".join(CPU_SERVICES)
        )
    scenarios, operations, cpus = summarize(stats, cpu)
    write_csv(TABLES_DIR / "cenarios.csv", scenarios)
    write_csv(TABLES_DIR / "operacoes.csv", operations)
    write_csv(TABLES_DIR / "cpu.csv", cpus)
    create_charts(scenarios, operations, cpus)
    write_analysis(scenarios, operations, cpus)
    print(f"Tabelas e gráficos gerados em {RESULTS_DIR}")


if __name__ == "__main__":
    main()
