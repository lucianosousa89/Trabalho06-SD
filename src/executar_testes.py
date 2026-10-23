"""Executa os experimentos de carga do PetClinic."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from urllib.error import URLError
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
LOCUSTFILE = BASE_DIR / "locustfile.py"
COMPOSE_DIR = PROJECT_DIR / "spring-petclinic-microservices"

# Opções: "rapido", "validacao" ou "completo".
MODO_EXECUCAO = "completo"
HOST = "http://localhost:8080"
SPAWN_RATE = 5
PAUSA_ENTRE_EXECUCOES_SEGUNDOS = 2
# Cada repetição inclui POSTs e pode deixar os serviços indisponíveis após uma
# carga alta. Recriar o ambiente evita que uma repetição comece com a falha da
# anterior e mantém as amostras comparáveis.
REINICIAR_AMBIENTE_ENTRE_EXECUCOES = True
TEMPO_MAX_INICIALIZACAO_SEGUNDOS = 180
INTERVALO_VERIFICACAO_SEGUNDOS = 5
SERVICOS_TESTE = ("config-server", "discovery-server", "customers-service", "vets-service", "api-gateway")

PROFILES_COMPLETOS = (("leitura", "ReadProfileUser"), ("escrita", "WriteProfileUser"))
SCENARIOS_COMPLETOS = (("A", 30), ("B", 80), ("C", 150))

if MODO_EXECUCAO == "rapido":
    RESULTS_DIR = PROJECT_DIR / "results_teste_rapido"
    # Cenário C com os mesmos parâmetros da bateria final, porém com uma
    # repetição por perfil para reduzir o tempo total de execução.
    REPETICOES, AQUECIMENTO_SEGUNDOS, DURACAO_MEDICAO_SEGUNDOS = 1, 60, 360
    PROFILES, SCENARIOS = PROFILES_COMPLETOS, (("C", 150),)
elif MODO_EXECUCAO == "validacao":
    RESULTS_DIR = PROJECT_DIR / "results_validacao"
    REPETICOES, AQUECIMENTO_SEGUNDOS, DURACAO_MEDICAO_SEGUNDOS = 1, 60, 360
    PROFILES, SCENARIOS = PROFILES_COMPLETOS, SCENARIOS_COMPLETOS
else:
    RESULTS_DIR = PROJECT_DIR / "results"
    REPETICOES, AQUECIMENTO_SEGUNDOS, DURACAO_MEDICAO_SEGUNDOS = 10, 60, 360
    PROFILES, SCENARIOS = PROFILES_COMPLETOS, SCENARIOS_COMPLETOS

RAW_DIR = RESULTS_DIR / "raw"
LOCUST_DIR = RAW_DIR / "locust"
MONITORAMENTO_DIR = RAW_DIR / "monitoramento"
LOG_DIR = RAW_DIR / "logs"
RUN_LOG = RESULTS_DIR / "execucoes.csv"
ENDPOINTS = (
    ("GET owners", "/api/customer/owners?lastName="),
    ("GET owner", "/api/customer/owners/1"),
    ("GET vets", "/api/vet/vets"),
)
CSV_FIELDS = (
    "perfil", "cenario", "usuarios", "repeticao", "inicio", "fim",
    "exit_code", "requests", "failures", "failure_rate_percent", "csv_prefix", "status",
)


def endpoints_available(show_result: bool = False) -> bool:
    for label, path in ENDPOINTS:
        try:
            with urlopen(HOST.rstrip("/") + path, timeout=10) as response:
                status = response.status
            if 200 <= status < 300:
                if show_result:
                    print(f"  OK: {label}: HTTP {status}")
            else:
                if show_result:
                    print(f"  FALHA: {label}: HTTP {status}")
                return False
        except (URLError, TimeoutError, OSError) as error:
            if show_result:
                print(f"  FALHA: {label}: {error}")
            return False
    return True


def reset_environment() -> None:
    if not COMPOSE_DIR.exists():
        raise SystemExit(f"Não encontrei o Docker Compose em {COMPOSE_DIR}")
    down_command = ["docker", "compose", "down", "--remove-orphans"]
    command = ["docker", "compose", "up", "-d", *SERVICOS_TESTE]
    print("\nRecriando os serviços para uma nova repetição...")
    try:
        result = subprocess.run(down_command, cwd=COMPOSE_DIR, check=False)
        if result.returncode != 0:
            raise SystemExit(f"Falha no Docker Compose: {' '.join(down_command)}")
        result = subprocess.run(command, cwd=COMPOSE_DIR, check=False)
    except OSError as error:
        raise SystemExit(f"Não consegui executar Docker Compose: {error}") from error
    if result.returncode != 0:
        raise SystemExit(f"Falha no Docker Compose: {' '.join(command)}")
    deadline = time.monotonic() + TEMPO_MAX_INICIALIZACAO_SEGUNDOS
    print("Aguardando os endpoints ficarem disponíveis...")
    while time.monotonic() < deadline:
        if endpoints_available():
            print("Serviços disponíveis.")
            return
        time.sleep(INTERVALO_VERIFICACAO_SEGUNDOS)
    raise SystemExit("Os serviços não ficaram disponíveis no tempo esperado.")


def init_results() -> None:
    for directory in (RESULTS_DIR, LOCUST_DIR, MONITORAMENTO_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG.exists():
        with RUN_LOG.open("w", newline="", encoding="utf-8-sig") as file:
            csv.DictWriter(file, fieldnames=CSV_FIELDS).writeheader()


def append_run(row: dict) -> None:
    with RUN_LOG.open("a", newline="", encoding="utf-8-sig") as file:
        csv.DictWriter(file, fieldnames=CSV_FIELDS).writerow(row)


def completed_run_keys() -> set[tuple[str, str, int, int]]:
    """Retorna somente execuções concluídas que ainda possuem seus artefatos."""
    if not RUN_LOG.exists():
        return set()
    completed: set[tuple[str, str, int, int]] = set()
    try:
        with RUN_LOG.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("status") != "CONCLUIDA":
                    continue
                prefix = row.get("csv_prefix", "")
                stats_path = LOCUST_DIR / f"{prefix}_stats.csv"
                cpu_path = MONITORAMENTO_DIR / f"{prefix}_cpu.csv"
                if prefix and stats_path.exists() and cpu_path.exists():
                    completed.add((row["perfil"], row["cenario"], int(row["usuarios"]), int(row["repeticao"])))
    except (OSError, ValueError, csv.Error):
        return set()
    return completed


def read_stats(path: Path) -> tuple[int, int, float]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            row = next(item for item in csv.DictReader(file) if item["Name"] == "Aggregated")
        requests, failures = int(float(row["Request Count"] or 0)), int(float(row["Failure Count"] or 0))
        return requests, failures, round(failures * 100 / requests, 2) if requests else 0.0
    except (FileNotFoundError, OSError, StopIteration, ValueError, csv.Error):
        return 0, 0, 0.0


def collect_docker_stats(output_path: Path, stop_event: Event) -> None:
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("timestamp", "container", "cpu_percent", "memory_percent"))
        while not stop_event.is_set():
            try:
                result = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{.Name}};{{.CPUPerc}};{{.MemPerc}}"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                for line in result.stdout.splitlines() if result.returncode == 0 else ():
                    name, cpu, memory = line.split(";", 2)
                    if name in SERVICOS_TESTE:
                        writer.writerow((datetime.now().isoformat(timespec="seconds"), name, cpu.rstrip("%"), memory.rstrip("%")))
                file.flush()
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            stop_event.wait(5)


def run_one(profile: str, user_class: str, scenario: str, users: int, repetition: int) -> dict:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix_name = f"{profile}_cenario{scenario}_u{users}_rep{repetition:02d}_{stamp}"
    csv_prefix = LOCUST_DIR / prefix_name
    stats_path = Path(f"{csv_prefix}_stats.csv")
    cpu_path = MONITORAMENTO_DIR / f"{prefix_name}_cpu.csv"
    stdout_path, stderr_path = LOG_DIR / f"{prefix_name}.log", LOG_DIR / f"{prefix_name}.err.log"
    command = [
        sys.executable, "-m", "locust", "-f", str(LOCUSTFILE), "--headless", "--host", HOST,
        "-u", str(users), "-r", str(SPAWN_RATE), "-t", f"{AQUECIMENTO_SEGUNDOS + DURACAO_MEDICAO_SEGUNDOS}s",
        "--csv", str(csv_prefix), user_class,
    ]
    print(f"\nPerfil: {profile} | Cenário: {scenario} | Usuários: {users} | Repetição: {repetition}/{REPETICOES}")
    started = datetime.now()
    stop_event = Event()
    collector = Thread(target=collect_docker_stats, args=(cpu_path, stop_event), daemon=True)
    collector.start()
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            process = subprocess.run(
                command, cwd=BASE_DIR, stdout=stdout, stderr=stderr, check=False,
                env={**os.environ, "AQUECIMENTO_SEGUNDOS": str(AQUECIMENTO_SEGUNDOS)},
            )
        exit_code = process.returncode
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        stop_event.set()
        collector.join(timeout=2)
    requests, failures, failure_rate = read_stats(stats_path)
    status = "CONCLUIDA" if stats_path.exists() and exit_code in (0, 1) else "ERRO_EXECUCAO"
    row = {
        "perfil": profile, "cenario": scenario, "usuarios": users, "repeticao": repetition,
        "inicio": started.isoformat(timespec="seconds"), "fim": datetime.now().isoformat(timespec="seconds"),
        "exit_code": exit_code, "requests": requests, "failures": failures,
        "failure_rate_percent": failure_rate, "csv_prefix": prefix_name, "status": status,
    }
    append_run(row)
    print(f"Resultado: {requests} requisições | {failures} falhas | {failure_rate:.2f}%")
    return row


def main() -> None:
    if not LOCUSTFILE.exists():
        raise SystemExit(f"Não encontrei {LOCUSTFILE}")
    init_results()
    version = subprocess.run([sys.executable, "-m", "locust", "--version"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise SystemExit("Locust não está instalado neste Python.")
    print(version.stdout.strip())
    planned_runs = [
        (profile, user_class, scenario, users, repetition)
        for profile, user_class in PROFILES
        for scenario, users in SCENARIOS
        for repetition in range(1, REPETICOES + 1)
    ]
    completed = completed_run_keys()
    pending_runs = [
        run for run in planned_runs
        if (run[0], run[2], run[3], run[4]) not in completed
    ]
    total = len(planned_runs)
    if completed:
        print(f"Retomando bateria: {total - len(pending_runs)} concluídas; {len(pending_runs)} pendentes.")
    if not pending_runs:
        print(f"\nBateria já concluída. Resultados em {RESULTS_DIR}")
        return
    for current, (profile, user_class, scenario, users, repetition) in enumerate(
        pending_runs, start=total - len(pending_runs) + 1,
    ):
        print(f"\nExecução {current}/{total}")
        if REINICIAR_AMBIENTE_ENTRE_EXECUCOES:
            reset_environment()
        elif not endpoints_available(show_result=True):
            raise SystemExit("Os endpoints não estão disponíveis.")
        result = run_one(profile, user_class, scenario, users, repetition)
        if result["status"] != "CONCLUIDA":
            raise SystemExit("Execução interrompida. Verifique os logs.")
        time.sleep(PAUSA_ENTRE_EXECUCOES_SEGUNDOS)
    print(f"\nBateria concluída. Resultados em {RESULTS_DIR}")


if __name__ == "__main__":
    main()
