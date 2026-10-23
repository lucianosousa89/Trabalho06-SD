# Trabalho Prático 06 — Avaliação de Desempenho com Locust

Este repositório avalia o Spring PetClinic Microservices com dois perfis de carga, três cenários de usuários e métricas de latência, vazão, falhas e CPU.

## Ambiente

- Windows, Docker Desktop e Docker Compose;
- Python 3.13, Locust e Matplotlib;
- Spring PetClinic Microservices executado via Docker Compose;
- aplicação e gerador de carga na mesma máquina.

Registre antes da entrega as versões do Docker Desktop, Docker Compose, Python, Locust e a memória/CPUs disponibilizadas ao Docker.

## Perfis de carga

| Operação | Leitura | Escrita |
|---|---:|---:|
| GET `/api/customer/owners?lastName=` | 45% | 20% |
| GET `/api/customer/owners/{id}` | 35% | 20% |
| GET `/api/vet/vets` | 15% | 20% |
| POST `/api/customer/owners` | 5% | 40% |

Cada usuário aguarda aleatoriamente de 1 a 3 segundos após uma tarefa. O parâmetro evita que um mesmo usuário envie requisições sem intervalo e representa uma interação mais realista.

## Cenários

| Cenário | Usuários | Aquecimento | Medição | Repetições |
|---|---:|---:|---:|---:|
| A — Leve | 30 | 1 min | 6 min | 10 |
| B — Moderado | 80 | 1 min | 6 min | 10 |
| C — Elevado | 150 | 1 min | 6 min | 10 |

O aquecimento é descartado pelo `locustfile.py`. Entre execuções, o executor recria os contêineres necessários para que cada repetição comece no mesmo estado. Não ocorre reinicialização durante a medição.

## Execução

Instale as dependências:

```powershell
py -m pip install locust matplotlib
```

O modo configurado no repositório é `rapido`: executa o cenário C com os mesmos 150 usuários, 1 minuto de aquecimento e 6 minutos de medição da bateria final, mas somente uma repetição por perfil. Para a bateria final, altere `MODO_EXECUCAO` para `completo` (60 execuções) no início do arquivo.

Execute a bateria:

```powershell
py .\src\executar_testes.py
```

Depois de finalizar, gere tabelas, gráficos e análise:

```powershell
py .\src\analisar_resultados.py
```
