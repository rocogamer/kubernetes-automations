# Kubernetes Automations

Herramienta de automatizacion para la instalacion y configuracion de clusters Kubernetes en distribuciones Debian (Debian, Ubuntu...).

Soporta dos modos de ejecucion:
- **Modo local**: Instala K8s directamente en la maquina donde se ejecuta
- **Modo Proxmox**: Crea VMs automaticamente en Proxmox VE e instala K8s en cada una via SSH

## Uso

### Modo local (por defecto)

```bash
# Ejecutar como root
sudo bash start.sh
```

O manualmente:

```bash
pip3 install -r requirements.txt
sudo python3 main.py
```

### Modo Proxmox (creacion automatica de VMs)

1. Edita `config.ini` y configura:
   - `proxmox_provision = true` en `[global]`
   - La seccion `[proxmox]` con los datos de tu servidor Proxmox
   - Las secciones `[proxmox_vm_master_1]`, `[proxmox_vm_worker_1]`, etc. con las VMs a crear

2. Asegurate de tener una clave SSH configurada:
   ```bash
   ssh-keygen -t rsa -b 4096  # Si no tienes una
   ```

3. Ejecuta:
   ```bash
   sudo bash start.sh
   ```

El flujo automatico es:
1. Conecta al API de Proxmox VE
2. Crea las VMs (clonando template o desde ISO)
3. Configura cloud-init (IP, SSH, DNS)
4. Arranca las VMs y espera a que esten listas
5. Se conecta por SSH a cada nodo y ejecuta la instalacion de K8s
6. Primero instala el master, obtiene el join token, y luego instala los workers

### Ejemplo de configuracion Proxmox

```ini
[global]
proxmox_provision = true

[proxmox]
host = 192.168.1.100
port = 8006
user = root@pam
password = mi_password_seguro
verify_ssl = false
node = pve
template_id = 9000
storage = local-lvm
bridge = vmbr0
ssh_public_key_file = ~/.ssh/id_rsa.pub
ssh_private_key_file = ~/.ssh/id_rsa
ssh_user = root
gateway = 192.168.1.1
cidr = 24
dns_servers = 8.8.8.8 8.8.4.4

[proxmox_vm_master_1]
name = k8s-master-1
vmid = 200
ip = 192.168.1.50
cores = 4
memory = 8192
disk = 50

[proxmox_vm_worker_1]
name = k8s-worker-1
vmid = 201
ip = 192.168.1.51
cores = 4
memory = 8192
disk = 50

[proxmox_vm_worker_2]
name = k8s-worker-2
vmid = 202
ip = 192.168.1.52
cores = 4
memory = 8192
disk = 50
```

## Configuracion

Toda la configuracion se realiza mediante el archivo `config.ini`. Consulta el archivo para ver todas las opciones disponibles.

## Caracteristicas

- [X] Provisionamiento automatico en Proxmox VE:
  - [X] Creacion de VMs por clonacion de template
  - [X] Creacion de VMs desde ISO
  - [X] Configuracion via cloud-init (IP estatica, SSH, DNS)
  - [X] Autenticacion por password o API token
  - [X] Destruccion de VMs para limpieza
- [X] Ejecucion remota via SSH (para multi-nodo)
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

## Estructura del proyecto

```
.
├── config.ini                      # Configuracion principal
├── main.py                         # Punto de entrada - orquestador
├── start.sh                        # Script de inicio rapido
├── requirements.txt                # Dependencias Python
├── models/
│   └── node.py                     # Modelo de nodo (local/SSH remoto)
└── modules/
    ├── proxmox_provisioner.py      # Provisionamiento de VMs en Proxmox
    ├── node_installation.py        # Instalacion base del nodo k8s
    ├── node_firewall.py            # Configuracion de firewalls
    ├── node_ha.py                  # HA con KeepAlived + HAProxy
    ├── k8s_network.py              # Plugins de red (Calico/Flannel)
    ├── k8s_storage.py              # Storage (Longhorn/Rook/CIFS)
    ├── k8s_ingress.py              # Ingress controllers
    ├── k8s_loadbalancer.py         # MetalLB
    ├── k8s_metrics.py              # Metrics Server
    ├── k8s_monitoring.py           # Grafana + Prometheus / Checkmk
    ├── k8s_security.py             # Falco
    └── k8s_opa.py                  # OPA Gatekeeper
```

## Fases de instalacion

### Modo Proxmox
0. **Provisionamiento**: Creacion y arranque de VMs en Proxmox VE
1-12. Se ejecutan las mismas fases que el modo local, pero via SSH en cada nodo

### Modo local / por nodo
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

## Requisitos de Proxmox

- Proxmox VE 7.x o 8.x
- Una plantilla de VM con cloud-init (recomendado: Debian 12 cloud image)
- Acceso al API de Proxmox (puerto 8006)
- Clave SSH configurada para acceso root a las VMs

### Crear plantilla cloud-init en Proxmox

```bash
# Descargar imagen cloud de Debian 12
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

# Crear VM template
qm create 9000 --name debian12-cloud --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 9000 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 9000 --scsihw virtio-scsi-single --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide0 local-lvm:cloudinit
qm set 9000 --boot order=scsi0
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm template 9000
```
