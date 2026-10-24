# Análise dos resultados

## 1. Objetivo e delineamento experimental

Este estudo avalia o comportamento do sistema de microsserviços Spring PetClinic sob diferentes níveis de concorrência. Foram comparados os perfis de carga **leitura** e **escrita** em três cenários: A (30 usuários), B (80 usuários) e C (150 usuários), com dez repetições por combinação.
Cada repetição teve 60 segundos de aquecimento, seguidos do período de medição. A utilização de CPU foi analisada exclusivamente para `customers-service` e `vets-service`.

## 2. Procedimento de análise

Os arquivos CSV produzidos pelo Locust foram consolidados por perfil e cenário. A latência média foi ponderada pelo número de requisições; P95 e vazão foram calculados como a média dos valores reportados nas repetições. Requisições e falhas foram somadas, e a taxa de falhas foi recalculada sobre esses totais. Para CPU, foram utilizadas as amostras coletadas após o aquecimento.
Essa estratégia evita que repetições com volumes distintos tenham o mesmo peso na média de latência e preserva a interpretação dos totais de requisições.

## 3. Resultados consolidados

| Perfil | Cenário | Usuários | Média (ms) | P95 (ms) | Vazão (req/s) | Requisições | Falhas | Falhas (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| escrita | A | 30 | 42.41 | 117.00 | 14.63 | 52530 | 0 | 0.00 |
| escrita | B | 80 | 585.33 | 4160.00 | 30.79 | 110388 | 16610 | 15.05 |
| escrita | C | 150 | 798.60 | 6820.00 | 53.27 | 190994 | 136377 | 71.40 |
| leitura | A | 30 | 17.89 | 50.30 | 14.82 | 53208 | 0 | 0.00 |
| leitura | B | 80 | 40.06 | 111.30 | 39.12 | 140338 | 5312 | 3.79 |
| leitura | C | 150 | 79.29 | 217.10 | 72.01 | 258454 | 141719 | 54.83 |

A tabela evidencia que o aumento da concorrência produz efeitos distintos nos dois perfis. O perfil de escrita apresenta maior sensibilidade à carga, especialmente no cenário C, no qual a latência de cauda e a taxa de falhas crescem de forma acentuada.

### 3.1 Comparação por operação

| Perfil | Cenário | Usuários | Operação | Média (ms) | P95 (ms) | Falhas (%) |
| --- | --- | --- | --- | --- | --- | --- |
| escrita | A | 30 | /api/customer/owners | 95.59 | 182.00 | 0.00 |
| escrita | A | 30 | /api/customer/owners [POST] | 47.11 | 59.80 | 0.00 |
| escrita | A | 30 | /api/customer/owners/[id] | 9.00 | 13.50 | 0.00 |
| escrita | A | 30 | /api/vet/vets | 12.48 | 20.80 | 0.00 |
| escrita | B | 80 | /api/customer/owners | 1196.48 | 7620.00 | 17.71 |
| escrita | B | 80 | /api/customer/owners [POST] | 591.10 | 4200.00 | 14.66 |
| escrita | B | 80 | /api/customer/owners/[id] | 534.65 | 4140.00 | 14.75 |
| escrita | B | 80 | /api/vet/vets | 9.67 | 15.80 | 13.45 |
| escrita | C | 150 | /api/customer/owners | 1239.93 | 9940.00 | 74.13 |
| escrita | C | 150 | /api/customer/owners [POST] | 938.39 | 8100.00 | 71.58 |
| escrita | C | 150 | /api/customer/owners/[id] | 878.08 | 7800.00 | 71.48 |
| escrita | C | 150 | /api/vet/vets | 6.83 | 16.50 | 68.28 |
| leitura | A | 30 | /api/customer/owners | 22.47 | 37.80 | 0.00 |
| leitura | A | 30 | /api/customer/owners [POST] | 54.34 | 59.80 | 0.00 |
| leitura | A | 30 | /api/customer/owners/[id] | 8.82 | 13.30 | 0.00 |
| leitura | A | 30 | /api/vet/vets | 12.98 | 21.20 | 0.00 |
| leitura | B | 80 | /api/customer/owners | 66.15 | 160.30 | 3.87 |
| leitura | B | 80 | /api/customer/owners [POST] | 54.58 | 72.90 | 3.87 |
| leitura | B | 80 | /api/customer/owners/[id] | 15.39 | 30.90 | 3.69 |
| leitura | B | 80 | /api/vet/vets | 14.85 | 35.00 | 3.71 |
| leitura | C | 150 | /api/customer/owners | 110.51 | 365.00 | 54.90 |
| leitura | C | 150 | /api/customer/owners [POST] | 114.27 | 144.10 | 54.52 |
| leitura | C | 150 | /api/customer/owners/[id] | 63.55 | 102.80 | 55.00 |
| leitura | C | 150 | /api/vet/vets | 9.82 | 23.90 | 54.34 |

A maior latência média foi observada na operação `/api/customer/owners`, no perfil escrita e cenário C, com 1239.93 ms. A maior degradação entre os cenários A e C ocorreu em `/api/customer/owners` no perfil escrita: de 95.59 ms para 1239.93 ms, aumento absoluto de 1144.34 ms (1197.17%).

### 3.2 Utilização dos serviços

| Perfil | Cenário | Usuários | Serviço | CPU (%) | Memória (%) |
| --- | --- | --- | --- | --- | --- |
| escrita | A | 30 | customers-service | 41.12 | 99.73 |
| escrita | A | 30 | vets-service | 4.93 | 93.06 |
| escrita | B | 80 | customers-service | 204.98 | 84.88 |
| escrita | B | 80 | vets-service | 5.82 | 69.04 |
| escrita | C | 150 | customers-service | 177.38 | 87.79 |
| escrita | C | 150 | vets-service | 3.93 | 68.91 |
| leitura | A | 30 | customers-service | 18.13 | 98.53 |
| leitura | A | 30 | vets-service | 4.34 | 90.05 |
| leitura | B | 80 | customers-service | 112.48 | 99.66 |
| leitura | B | 80 | vets-service | 8.59 | 94.00 |
| leitura | C | 150 | customers-service | 277.20 | 99.86 |
| leitura | C | 150 | vets-service | 7.84 | 93.79 |

A maior utilização média de CPU foi registrada no `customers-service`, no perfil leitura e cenário C, atingindo 277.20%. A comparação entre os cenários extremos é apresentada abaixo:
- **customers-service — leitura**: 18.13% no cenário A e 277.20% no cenário C.
- **customers-service — escrita**: 41.12% no cenário A e 177.38% no cenário C.
- **vets-service — leitura**: 4.34% no cenário A e 7.84% no cenário C.
- **vets-service — escrita**: 4.93% no cenário A e 3.93% no cenário C.

## 4. Discussão das questões de pesquisa

### 4.1 Efeito do aumento de usuários sobre o tempo de resposta

- **Leitura**: o tempo médio aumentou de 17.89 ms para 79.29 ms (+343.09%), enquanto o P95 passou de 50.30 ms para 217.10 ms (+331.61%).
- **Escrita**: o tempo médio aumentou de 42.41 ms para 798.60 ms (+1783.04%), enquanto o P95 passou de 117.00 ms para 6820.00 ms (+5729.06%).
O crescimento simultâneo da média e do P95 indica não apenas aumento do tempo típico, mas também maior variabilidade e degradação da cauda da distribuição de latências. Esse efeito é mais pronunciado no perfil de escrita.

### 4.2 Perfil com maior vazão

A maior vazão média entre os três cenários pertence ao perfil **leitura**, com 41.98 requisições/s. A evolução entre os cenários extremos foi:
- **Leitura**: 14.82 para 72.01 requisições/s (+385.73%).
- **Escrita**: 14.63 para 53.27 requisições/s (+264.04%).
A maior vazão observada em um cenário individual foi 72.01 requisições/s, no cenário de maior carga do perfil de leitura.

### 4.3 Operações com maior degradação

A degradação concentra-se nas operações de clientes, sobretudo no perfil de escrita. O resultado sugere que as operações que modificam o estado do sistema são mais suscetíveis à contenção e ao aumento do tempo de processamento sob concorrência elevada.

### 4.4 Variação do consumo de CPU

A CPU não cresce necessariamente de forma linear com o número de usuários. No `customers-service`, o salto entre A e C é expressivo, enquanto o `vets-service` apresenta variação menor. Essa diferença indica que os serviços possuem sensibilidades distintas ao perfil de carga e que o customers-service constitui o principal ponto de atenção no cenário C.

### 4.5 Cenário com maior taxa de falhas

A maior taxa de falhas ocorreu no perfil **escrita**, cenário **C**, com 71.40% (136377 falhas em 190994 requisições). O resultado caracteriza perda de confiabilidade sob carga elevada e deve ser analisado conjuntamente com o crescimento do P95 e da utilização de CPU.

## 5. Considerações metodológicas e limitações

- O P95 apresentado é a média dos P95 das repetições, e não um percentil recalculado sobre todas as amostras brutas.
- A vazão representa a média dos valores reportados pelo Locust durante cada repetição.
- A utilização de CPU do Docker pode ultrapassar 100% quando expressa relativamente a um único núcleo; portanto, valores superiores a 100% representam uso agregado de múltiplos núcleos.
- Os resultados descrevem o ambiente experimental executado e não devem ser generalizados para infraestruturas com configuração distinta.

## 6. Conclusão

Os resultados demonstram que o aumento de usuários deteriora principalmente a latência de cauda e a taxa de falhas do perfil de escrita. O perfil de leitura sustenta maior vazão média, enquanto o `customers-service` concentra o maior consumo de CPU entre os dois serviços monitorados. Assim, o cenário C representa o limite de maior criticidade da bateria, devendo orientar ações de otimização, dimensionamento e investigação das operações de escrita.

Os gráficos correspondentes estão disponíveis em `graficos/`, e as tabelas completas em `tabelas/`.
