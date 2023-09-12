class NodeInstallation:
    # Definimos el constructor
    def __init__(self, node):
        if type(node).__name__ != "Node":
            raise Exception("Node must be a Node object")

        self.node = node

    # Definimos el método para instalar el nodo
    def install_node(self):
        self.node.execute_command("modprobe overlay")
        self.node.execute_command("modprobe br_netfilter")
        file = open("/etc/modules-load.d/containerd.conf", "w")
        file.write("overlay\n")
        file.write("br_netfilter\n")
        file.close()

        self.node.execute_command("apt update")
        self.node.execute_command("apt install -y containerd")
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

        self.node.execute_command("echo fs.inotify.max_user_instances=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p")

        self.node.execute_command("swapoff -a")
        self.node.execute_command("sed -i '/ swap / s/^/#/' /etc/fstab")

        # Ejecutaremos una serie de comandos para instalar el nodo que serian los siguientes:
        self.node.execute_command("apt update")
        self.node.execute_command("apt install -y apt-transport-https ca-certificates curl software-properties-common curl git vim")
        self.node.execute_command("curl -fsSL https://dl.k8s.io/apt/doc/apt-key.gpg | gpg --dearmor -o "
                  "/etc/apt/keyrings/kubernetes-archive-keyring.gpg")
        self.node.execute_command('echo "deb [signed-by=/etc/apt/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ '
                  'kubernetes-xenial main" | tee /etc/apt/sources.list.d/kubernetes.list')
        self.node.execute_command("apt update")
