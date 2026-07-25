# meshmonitor

Система мониторинга сетевой связности локальной сети

## Описание

Распределенная система с гибридной схемой:
1. **push** агенты на python проверяют состояние сети и отправляют json на центральный коллектов
2. **pull** grafana получает данные из БД коллектора и prometheus

## Архитектура

```mermaid
flowchart TD
    subgraph Target_Infra ["Инфраструктура"]
        style Target_Infra fill:#f9f9f9,stroke:#666,stroke-width:1px
        Router1["Router 1<br/><b>L3:</b> ICMP Ping | <b>L7:</b> Web UI"]
        Router2["Router 2<br/><b>L3:</b> ICMP Ping | <b>L7:</b> Web UI"]
        External_DNS["External<br/><b>L3:</b> 8.8.8.8 | <b>L7:</b> DNS mos.ru"]
    end

    subgraph Probes ["Python-зонды"]
        style Probes fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
        Agent_Win["Agent"]
        Agent_Mac["macOS Agent"]
        Agent_Linux["Linux Node Agent"]
    end

    subgraph Cluster ["k3s Cluster"]
        style Cluster fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px

        subgraph Ingress_Layer ["L7-периметр"]
            Nginx_Ingress["Nginx Service / Ingress<br/><i>NodePort: 30080</i><br/>(White-list filtering: 192.168.1.0/24)"]
        end

        subgraph App_Layer ["Слой приложений и БД"]
            Go_Collector["Go Collector API Pod<br/><br/>Goroutines / Conn Pool"]
            Postgres_DB[("PostgreSQL DB Pod<br/>")]
        end

        subgraph Observability_Layer ["Observability"]
            Prometheus["Prometheus TSDB Pod<br/><i>ClusterIP: 9090</i>"]
            Grafana["Grafana Dashboard Pod<br/><i>NodePort: 32000</i>"]
        end
    end

    subgraph Automation ["IaC"]
        style Automation fill:#fff3e0,stroke:#f57c00,stroke-width:1px
        Ansible["Ansible Control Node"]
    end

    Probes -->|L3 / L4 / L7 checks| Target_Infra
    
    Probes -->|HTTP POST JSON<br/>/api/v1/telemetry| Nginx_Ingress
    Nginx_Ingress -->|Reverse Proxy<br/>+ X-Real-IP headers| Go_Collector

    Go_Collector -->|Async INSERT| Postgres_DB
    
    Prometheus -->|Pull /metrics every 5s<br/>CoreDNS FQDN| Go_Collector
    Grafana -->|PromQL queries| Prometheus

    Ansible -.->|deploy-agent.yaml| Probes
    User((Admin)) ==>|HTTP Web UI :32000| Grafana
```

### Покрытие слоев

| Слой OSI | Объекты проверки | Инструмент зондирования | Описание / Назначение |
| :--- | :--- | :--- | :--- |
| **L3 Network** | Роутеры, external WAN (8.8.8.8) | System `ping` (ICMP) | Анализ латентности, потерь пакетов и коллизий |
| **L4 Transport** | k3s NodePort (30080), SSH (22), Postgres (5432) | Non-blocking TCP Sockets | Контроль доступности транспортных портов и служб |
| **L7 Application** | Web UI роутеров, DNS resolution | `http.client` & `socket` | Замер времени отклика веб-демонов и скорости работы DNS |

### Стек

* **Backend**: Сборщик метрик на Go
* **Containerization**: Multi-stage `Dockerfile` на базе `alpine`
* **Orchestration**: Кластер k3s. Все компоненты системы упакованы в Helm-чарт
* **Observability**: `prometheus/client_golang`. Grafana (State Timeline, Bar Gauges, Row Isolation)
* **Synthetic Probe Agent**: Python скрипт на стандартной библиотеке (`socket`, `urllib`, `subprocess`) 
* **IaC**: Ansible

## Быстрый старт

### Prerequisites

k3s (minikube/kind), helm, docker, python3

### 1. Кластер k3s

```bash
docker build -t collector:latest -f deploy/docker/Dockerfile .
sudo k3s ctr images import --namespace k8s.io collector.tar
helm install mesh-monitor ./deploy/helm/mesh-monitor
```

### 2. Локальный агент 

```bash
python3 scripts/agent.py
```

## Дашборд Grafana

Дашборд структурирован по секциям:
1. **Global Health**: Задержка до роутеров и Интернета и матрица доступности для обнаружения аварий
2. **Infrastructure**: Статус портов кластера, скорость DNS и доступность HTTP интерфейсов роутеров

## STAR

WIP
