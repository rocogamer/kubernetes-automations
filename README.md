# Kubernetes Automations

Herramienta de automatizacion para la instalacion y configuracion de clusters Kubernetes en distribuciones Debian (Debian, Ubuntu...).

## Uso

```bash
# Ejecutar como root
sudo bash start.sh
```

O manualmente:

```bash
pip3 install -r requirements.txt
sudo python3 main.py
```

## Configuracion

Toda la configuracion se realiza mediante el archivo `config.ini`. Consulta el archivo para ver todas las opciones disponibles.

## Caracteristicas

- [X] Configurar Firewall:
  - [X] IPTables (con soporte para guardar reglas y script externo)
  - [X] Firewalld (con soporte de zonas)
  - [X] UFW
- [X] Instalacion de Masters y Workers via kubeadm
- [X] Soporte HA (High Availability):
  - [X] KeepAlived para Virtual IP
  - [X] HAProxy como load balancer del API Server
- [X] Configuracion del sistema de backups:
  - [X] Backups local de etcd con systemd timer
  - [X] Script de restauracion automatico
  - [ ] Backups en remoto con tecnologia S3
  - [ ] Backups en remoto con tecnologia NFS
  - [ ] Backups en remoto con tecnologia CIFS
  - [ ] Backups en remoto con tecnologia FTP
  - [ ] Backups en remoto con tecnologia RSYNC
- [X] Instalacion de redes:
  - [X] Calico (con calicoctl)
  - [X] Flannel (con CNI plugins)
- [X] Instalacion de componentes de storage:
  - [X] Longhorn
  - [X] Rook-Ceph
  - [X] FlexVolume CIFS
- [X] Instalacion de componentes de ingress:
  - [X] NGINX Ingress Controller (community)
  - [X] NGINX Ingress by Kubernetes
  - [X] Traefik Ingress
  - [X] HAProxy Ingress
- [X] Instalacion de componentes para LoadBalancer services:
  - [X] MetalLB
- [X] Instalacion de componentes de metricas para HPA:
  - [X] Kubernetes Metrics Server
- [X] Instalacion de agentes de monitorizacion:
  - [X] Grafana + Prometheus (kube-prometheus-stack)
  - [X] Checkmk agent (DaemonSet)
- [X] Instalacion de agentes de seguridad:
  - [X] Falco (DaemonSet)
- [X] Instalacion de agentes de OPA:
  - [X] Gatekeeper
- [ ] Instalacion de componentes via remota usando SSH

## Estructura del proyecto

```
.
├── config.ini                  # Configuracion principal
├── main.py                     # Punto de entrada - orquestador
├── start.sh                    # Script de inicio rapido
├── requirements.txt            # Dependencias Python
├── models/
│   └── node.py                 # Modelo de nodo (master/worker)
└── modules/
    ├── node_installation.py    # Instalacion base del nodo k8s
    ├── node_firewall.py        # Configuracion de firewalls
    ├── node_ha.py              # HA con KeepAlived + HAProxy
    ├── k8s_network.py          # Plugins de red (Calico/Flannel)
    ├── k8s_storage.py          # Storage (Longhorn/Rook/CIFS)
    ├── k8s_ingress.py          # Ingress controllers
    ├── k8s_loadbalancer.py     # MetalLB
    ├── k8s_metrics.py          # Metrics Server
    ├── k8s_monitoring.py       # Grafana + Prometheus / Checkmk
    ├── k8s_security.py         # Falco
    └── k8s_opa.py              # OPA Gatekeeper
```

## Fases de instalacion

1. **Pre-instalacion**: Modulos del kernel, containerd, repositorios APT
2. **Firewall**: Configuracion de puertos necesarios
3. **HA** (opcional): KeepAlived + HAProxy
4. **Instalacion K8s**: kubeadm, kubelet, kubectl + init/join del cluster
5. **Red**: Plugin de red (Calico o Flannel)
6. **Storage**: Longhorn, Rook-Ceph, FlexVolume CIFS
7. **LoadBalancer**: MetalLB
8. **Ingress**: NGINX, Traefik, HAProxy
9. **Metricas**: Metrics Server para HPA
10. **Monitorizacion**: Grafana + Prometheus, Checkmk
11. **Seguridad**: Falco
12. **OPA**: Gatekeeper
