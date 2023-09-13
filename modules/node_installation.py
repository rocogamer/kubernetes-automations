class NodeInstallation:
    # Definimos el constructor
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise Exception("Node must be a Node object")

        if type(config).__name__ != "ConfigParser" and "k8s" not in config.sections():
            raise Exception("Config must be a ConfigParser object and the section node_firewall must be in the config")

        self.node = node
        self.config = config

    # Definimos el método para instalar el nodo
    def pre_install_node(self):
        self.node.execute_command("modprobe overlay")
        self.node.execute_command("modprobe br_netfilter")
        file = open("/etc/modules-load.d/containerd.conf", "w")
        file.write("overlay\n")
        file.write("br_netfilter\n")
        file.close()

        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y containerd")
        self.node.execute_command("containerd config default | tee /etc/containerd/config.toml")
        self.node.execute_command("sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml")

        self.node.execute_command("systemctl restart containerd")
        self.node.execute_command("systemctl enable containerd")

        file = open("/etc/sysctl.d/99-kubernetes-cri.conf", "w")
        file.write("net.bridge.bridge-nf-call-iptables = 1\n")
        file.write("net.ipv4.ip_forward = 1\n")
        file.write("net.bridge.bridge-nf-call-ip6tables = 1\n")
        file.close()

        self.node.execute_command("sysctl --system")

        self.node.execute_command(
            "echo fs.inotify.max_user_instances=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p")

        self.node.execute_command("sysctl -w net.netfilter.nf_conntrack_max=1000000")
        self.node.execute_command("echo 'net.netfilter.nf_conntrack_max=1000000' |tee -a /etc/sysctl.conf")

        self.node.execute_command("swapoff -a")
        self.node.execute_command("sed -i '/swap/ s/^/#/' /etc/fstab")

        # Ejecutaremos una serie de comandos para instalar el nodo que serian los siguientes:
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
        self.node.execute_command(
            "DEBIAN_FRONTEND=noninteractive apt install -y apt-transport-https ca-certificates curl software-properties-common "
            "curl git vim ipvsadm iptables")
        self.node.execute_command(
            "curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | gpg --dearmor -o "
            "/etc/apt/keyrings/kubernetes-apt-keyring.gpg")
        self.node.execute_command(
            'echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list')
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")

    def install_node(self):
        self.node.execute_command(
            f"DEBIAN_FRONTEND=noninteractive apt install -y kubelet='{self.config['k8s']['version']}' kubeadm='{self.config['k8s']['version']}' kubectl='{self.config['k8s']['version']}'")
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt-mark hold kubelet kubeadm kubectl")
        self.post_install_node()

    def post_install_node(self):
        self.node.execute_command("kubeadm config images pull")
        kubeadm_init = ""
        if self.node.node_type == "master":
            if self.config['k8s_components']['network'] == "calico":
                kubeadm_init = "kubeadm init --pod-network-cidr=10.244.0.0/16"
            elif self.config['k8s_components']['network'] == "flannel":
                kubeadm_init = "kubeadm init --pod-network-cidr=192.168.0.0/16"
            else:
                raise Exception("Network not supported")
        else:
            kubeadm_init = f"kubeadm join {self.config['k8s']['master_ip']}:{self.config['k8s']['master_port']} --token {self.config['k8s']['token']} --discovery-token-ca-cert-hash sha256:{self.config['k8s']['ca_cert_hash']}"

        self.node.execute_command(kubeadm_init)

        if self.node.node_type == "master":
            self.node.execute_command("mkdir -p $HOME/.kube")
            self.node.execute_command("cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
            self.node.execute_command("chown $(id -u):$(id -g) $HOME/.kube/config")

            if self.config.getboolean("k8s", "master_etcd_backup"):
                self.node.execute_command("mkdir -p /opt/backup")
                self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")
                self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y etcd-client")
                # Creamoe el fichero de script de backup /etc/scripts/Seguridad/backup.sh
                file = open("/etc/scripts/Seguridad/backup.sh", "w")
                file.write("#!/bin/bash\n")
                file.write("day=$(date +%Y-%m-%d)\n")
                file.write("cp -r /etc/kubernetes \"/tmp/$day-$HOSTNAME-backup\"\n")
                file.write("cp -r /var/lib/etcd \"/tmp/$day-$HOSTNAME-backup\"\n")
                file.write("export ETCDCTL_API=3\n")
                file.write("etcdctl --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt "
                           "--cert=/etc/kubernetes/pki/etcd/server.crt --key=/etc/kubernetes/pki/etcd/server.key "
                           "snapshot save \"/tmp/$day-$HOSTNAME-backup/snapshot-etcdctl.db\"\n")
                file.write("tar -zcvf \"/tmp/$day-$HOSTNAME-backup.tar.gz\" \"/tmp/$day-$HOSTNAME-backup\"\n")
                file.write("rm -rf \"/tmp/$day-$HOSTNAME-backup\"\n")
                file.write("rm -rf \"/tmp/$day-$HOSTNAME-backup.tar.gz\"\n")
                if self.config.getboolean("k8s_etc_backup", "local_save"):
                    file.write("mv \"/tmp/$day-$HOSTNAME-backup.tar.gz\" /opt/backup\n")
                    file.write("find " + self.config["k8s_etc_backup"][
                        "local_directory"] + " -type f -mtime +7 -exec rm {} \\;\n")

                file.close()
                self.node.execute_command("chmod +x /etc/scripts/Seguridad/backup.sh")

                # Creamos el servicio en el sistema
                file = open("/etc/systemd/system/backup.service", "w")
                file.write("[Unit]\n")
                file.write("Description=Backup service\n")
                file.write("After=network.target\n")
                file.write("\n")
                file.write("[Service]\n")
                file.write("Type=simple\n")
                file.write("User=root\n")
                file.write("ExecStart=/etc/scripts/Seguridad/backup.sh\n")
                file.write("\n")
                file.write("[Install]\n")
                file.write("WantedBy=multi-user.target\n")
                file.close()

                # Damos ahora de alta el timer dentro del systemd
                file = open("/etc/systemd/system/backup.timer", "w")
                file.write("[Unit]\n")
                file.write("Description=Backup timer\n")
                file.write("\n")
                file.write("[Timer]\n")
                file.write("OnCalendar=*-*-* 00:00:00\n")
                file.write("Unit=backup.service\n")
                file.write("\n")
                file.write("[Install]\n")
                file.write("WantedBy=timers.target\n")
                file.close()

                self.node.execute_command("systemctl daemon-reload")
                self.node.execute_command("systemctl enable backup.timer")
                self.node.execute_command("systemctl start backup.timer")

                # Creamos el fichero de script de restauracion
                file = open("/etc/scripts/Seguridad/restore.sh", "w")
                file.write("#!/bin/bash\n")
                file.write("day=$1 # hara falta indicar el dia en formato: 2023-09-13\n")
                file.write("tar -zxvf \"/opt/backup/$day-$HOSTNAME-backup.tar.gz\" -C /tmp\n")
                file.write("cp -r \"/tmp/$day-$HOSTNAME-backup/etc/kubernetes\" /etc\n")
                file.write("cp -r \"/tmp/$day-$HOSTNAME-backup/var/lib/etcd\" /var/lib\n")
                file.write("export ETCDCTL_API=3\n")
                file.write("etcdctl --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt "
                           "--cert=/etc/kubernetes/pki/etcd/server.crt --key=/etc/kubernetes/pki/etcd/server.key "
                           "snapshot restore \"/tmp/$day-$HOSTNAME-backup/snapshot-etcdctl.db\"\n")
                file.write("rm -rf \"/tmp/$day-$HOSTNAME-backup\"\n")
                file.close()
