import time
import logging

logger = logging.getLogger(__name__)


class NodeInstallation:
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise TypeError("node must be a Node object")
        if type(config).__name__ != "ConfigParser" or "k8s" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'k8s' section")

        self.node = node
        self.config = config

    def pre_install_node(self):
        logger.info("Starting pre-installation of the node")

        # Load kernel modules
        self.node.execute_command("modprobe overlay")
        self.node.execute_command("modprobe br_netfilter")
        with open("/etc/modules-load.d/containerd.conf", "w") as f:
            f.write("overlay\nbr_netfilter\n")

        # Install containerd
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y containerd")
        self.node.execute_command("mkdir -p /etc/containerd")
        self.node.execute_command("containerd config default | tee /etc/containerd/config.toml")
        self.node.execute_command(
            "sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml"
        )
        self.node.execute_command("systemctl restart containerd")
        self.node.execute_command("systemctl enable containerd")

        # Kernel parameters for Kubernetes
        with open("/etc/sysctl.d/99-kubernetes-cri.conf", "w") as f:
            f.write("net.bridge.bridge-nf-call-iptables = 1\n")
            f.write("net.ipv4.ip_forward = 1\n")
            f.write("net.bridge.bridge-nf-call-ip6tables = 1\n")
        self.node.execute_command("sysctl --system")

        # Inotify and conntrack tuning
        self.node.execute_command(
            "echo fs.inotify.max_user_instances=524288 | tee -a /etc/sysctl.conf && sysctl -p"
        )
        self.node.execute_command("sysctl -w net.netfilter.nf_conntrack_max=1000000")
        self.node.execute_command(
            "echo 'net.netfilter.nf_conntrack_max=1000000' | tee -a /etc/sysctl.conf"
        )

        # Disable swap
        self.node.execute_command("swapoff -a")
        self.node.execute_command("sed -i '/swap/ s/^/#/' /etc/fstab")

        # Install dependencies and add Kubernetes APT repository
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
        self.node.execute_command(
            "DEBIAN_FRONTEND=noninteractive apt install -y apt-transport-https ca-certificates "
            "curl software-properties-common git vim ipvsadm iptables gnupg"
        )
        self.node.execute_command("mkdir -p /etc/apt/keyrings")
        self.node.execute_command(
            "curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key "
            "| gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg"
        )
        self.node.execute_command(
            'echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] '
            'https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" '
            '| tee /etc/apt/sources.list.d/kubernetes.list'
        )
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")

        logger.info("Pre-installation completed")

    def install_node(self):
        version = self.config["k8s"]["version"]
        logger.info(f"Installing Kubernetes components version {version}")

        self.node.execute_command(
            f"DEBIAN_FRONTEND=noninteractive apt install -y "
            f"kubelet='{version}' kubeadm='{version}' kubectl='{version}'"
        )
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt-mark hold kubelet kubeadm kubectl")
        self._post_install_node()

    def _post_install_node(self):
        self.node.execute_command("kubeadm config images pull")

        if self.node.node_type == "master":
            # FIX: Calico uses 192.168.0.0/16, Flannel uses 10.244.0.0/16
            network = self.config["k8s_components"]["network"]
            if network == "calico":
                kubeadm_init = "kubeadm init --pod-network-cidr=192.168.0.0/16"
            elif network == "flannel":
                kubeadm_init = "kubeadm init --pod-network-cidr=10.244.0.0/16"
            else:
                raise ValueError(f"Unsupported network plugin: {network}")
        else:
            master_ip = self.config["k8s"]["master_ip"]
            master_port = self.config["k8s"]["master_port"]
            master_token = self.config["k8s"]["master_token"]
            master_cert = self.config["k8s"]["master_cert"]
            kubeadm_init = (
                f"kubeadm join {master_ip}:{master_port} "
                f"--token {master_token} "
                f"--discovery-token-ca-cert-hash sha256:{master_cert}"
            )

        self.node.execute_command(kubeadm_init)

        logger.info("Waiting 30 seconds for the cluster to stabilize...")
        time.sleep(30)

        if self.node.node_type == "master":
            self._configure_kubectl()
            if self.config.getboolean("k8s", "master_etcd_backup"):
                self._configure_etcd_backup()

    def _configure_kubectl(self):
        logger.info("Configuring kubectl for the current user")
        self.node.execute_command("mkdir -p $HOME/.kube")
        self.node.execute_command("cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
        self.node.execute_command("chown $(id -u):$(id -g) $HOME/.kube/config")

    def _configure_etcd_backup(self):
        logger.info("Configuring etcd backup system")
        local_dir = self.config["k8s_etc_backup"]["local_directory"]
        local_save = self.config.getboolean("k8s_etc_backup", "local_save")

        self.node.execute_command(f"mkdir -p {local_dir}")
        self.node.execute_command("mkdir -p /etc/scripts/Seguridad")
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y etcd-client")

        # Create backup script
        backup_script = '#!/bin/bash\n'
        backup_script += 'set -euo pipefail\n'
        backup_script += 'day=$(date +%Y-%m-%d)\n'
        backup_script += 'BACKUP_NAME="$day-$HOSTNAME-backup"\n'
        backup_script += 'BACKUP_TMP="/tmp/$BACKUP_NAME"\n'
        backup_script += '\n'
        backup_script += 'mkdir -p "$BACKUP_TMP"\n'
        backup_script += 'cp -r /etc/kubernetes "$BACKUP_TMP/"\n'
        backup_script += 'cp -r /var/lib/etcd "$BACKUP_TMP/"\n'
        backup_script += '\n'
        backup_script += 'export ETCDCTL_API=3\n'
        backup_script += (
            'etcdctl --endpoints=https://127.0.0.1:2379 '
            '--cacert=/etc/kubernetes/pki/etcd/ca.crt '
            '--cert=/etc/kubernetes/pki/etcd/server.crt '
            '--key=/etc/kubernetes/pki/etcd/server.key '
            'snapshot save "$BACKUP_TMP/snapshot-etcdctl.db"\n'
        )
        backup_script += '\n'
        backup_script += 'tar -zcvf "/tmp/$BACKUP_NAME.tar.gz" -C /tmp "$BACKUP_NAME"\n'
        backup_script += 'rm -rf "$BACKUP_TMP"\n'

        if local_save:
            backup_script += f'mv "/tmp/$BACKUP_NAME.tar.gz" {local_dir}/\n'
            backup_script += f'find {local_dir} -type f -name "*.tar.gz" -mtime +7 -exec rm {{}} \\;\n'

        with open("/etc/scripts/Seguridad/backup.sh", "w") as f:
            f.write(backup_script)
        self.node.execute_command("chmod +x /etc/scripts/Seguridad/backup.sh")

        # Create systemd service
        with open("/etc/systemd/system/backup.service", "w") as f:
            f.write("[Unit]\n")
            f.write("Description=Kubernetes etcd backup service\n")
            f.write("After=network.target\n\n")
            f.write("[Service]\n")
            f.write("Type=oneshot\n")
            f.write("User=root\n")
            f.write("ExecStart=/etc/scripts/Seguridad/backup.sh\n\n")
            f.write("[Install]\n")
            f.write("WantedBy=multi-user.target\n")

        # Create systemd timer
        with open("/etc/systemd/system/backup.timer", "w") as f:
            f.write("[Unit]\n")
            f.write("Description=Kubernetes etcd backup timer\n\n")
            f.write("[Timer]\n")
            f.write("OnCalendar=*-*-* 00:00:00\n")
            f.write("Persistent=true\n")
            f.write("Unit=backup.service\n\n")
            f.write("[Install]\n")
            f.write("WantedBy=timers.target\n")

        self.node.execute_command("systemctl daemon-reload")
        self.node.execute_command("systemctl enable backup.timer")
        self.node.execute_command("systemctl start backup.timer")

        # Create restore script
        restore_script = '#!/bin/bash\n'
        restore_script += 'set -euo pipefail\n'
        restore_script += 'if [ -z "${1:-}" ]; then\n'
        restore_script += '    echo "Usage: $0 <date> (format: YYYY-MM-DD)"\n'
        restore_script += '    exit 1\n'
        restore_script += 'fi\n'
        restore_script += 'day=$1\n'
        restore_script += 'BACKUP_NAME="$day-$HOSTNAME-backup"\n'
        restore_script += f'tar -zxvf "{local_dir}/$BACKUP_NAME.tar.gz" -C /tmp\n'
        restore_script += 'cp -r "/tmp/$BACKUP_NAME/kubernetes" /etc/\n'
        restore_script += 'cp -r "/tmp/$BACKUP_NAME/etcd" /var/lib/\n'
        restore_script += 'export ETCDCTL_API=3\n'
        restore_script += (
            'etcdctl --endpoints=https://127.0.0.1:2379 '
            '--cacert=/etc/kubernetes/pki/etcd/ca.crt '
            '--cert=/etc/kubernetes/pki/etcd/server.crt '
            '--key=/etc/kubernetes/pki/etcd/server.key '
            'snapshot restore "/tmp/$BACKUP_NAME/snapshot-etcdctl.db"\n'
        )
        restore_script += 'rm -rf "/tmp/$BACKUP_NAME"\n'

        with open("/etc/scripts/Seguridad/restore.sh", "w") as f:
            f.write(restore_script)
        self.node.execute_command("chmod +x /etc/scripts/Seguridad/restore.sh")

        logger.info("etcd backup system configured successfully")
