Actualmente este programa esta pensado para funcionamiento en distribuciones debian (Debian, ubuntu...).

Caracteristiscas del programa:
- [ ] Instalación de los componentes via remota usando SSH
- [ ] Configurar Firewall:
  - [ ] IPTables (Indicando ruta del script.sh, ademas se aplicara automaticamente durante la ejecucción)
  - [ ] Firewalld
- [ ] Realizar instalacion usando el metodo kubeadm, con HA o sin HA.
  - [ ] Usando loadbalancer externo, creandolo con configuracion IPTables en nodo externo
  - [ ] Usando loadbalancer interno, usando KeepAlived
- [ ] Instalación de Masters y workers.
- [ ] Configuracion del sistema de backups
- [ ] Instalación de las redes, marcadas con check las compatibles actualmente:
  - [ ] Calico
  - [ ] Flannel
- [ ] Instalación de componentes de storage, marcadas con check las compatibles actualmente:
  - [ ] Longhorn
  - [ ] Rook
  - [ ] FlexVolume CIFS
- [ ] Instalación de componentes de ingress, marcadas con check las compatibles actualmente:
  - [ ] Nginx Ingress Controller
  - [ ] Nginx Ingress by kubernetes
  - [ ] Traefik Ingress
  - [ ] HAProxy Ingress
- [ ] Instalación de componentes para LoadBalancer services, marcadas con check las compatibles actualmente:
  - [ ] MetalB
- [ ] Instalación de componentes de metricas para HPA de kubernetes:
  - [ ] Kube-metrics-server
- [ ] Instalación de agentes de monitorización:
  - [ ] Grafana + Prometheus
  - [ ] Check_mk agent for kubernetes
- [ ] Instalación de agentes de seguridad:
  - [ ] Falco
- [ ] Instalación de agentes de OPA:
  - [ ] Gatekeeper

