from time import sleep

import modules.node_firewall as node_firewall
class K8sNetwork:
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise Exception("Node must be a Node object")

        if type(config).__name__ != "ConfigParser" and "k8s" not in config.sections():
            raise Exception("Config must be a ConfigParser object and the section node_firewall must be in the config")

        self.node = node
        self.config = config

    def configure_network(self):
        if self.config["k8s_components"]["network"] == "calico":
            self.configure_network_calico()
        elif self.config["k8s_components"]["network"] == "flannel":
            self.configure_network_flannel()
        else:
            raise Exception("Network not supported")

        self.install_network()

    def install_network(self):
        if self.node.node_type == "master":
            if self.config["k8s_components"]["network"] == "calico":
                self.install_network_calico()
            elif self.config["k8s_components"]["network"] == "flannel":
                self.install_network_flannel()
            else:
                raise Exception("Network not supported")
            print('Esperamos 2 minutos para que se inicie todo de manera correcta')
            sleep(120)

    def configure_network_calico(self):
        if self.config.getboolean("global", "firewall"):
            firewall = node_firewall.NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["4789","51820","51821","4789"], "udp","Calico ports")
            firewall.configure_firewalld(["4789","51820","51821","4789"], "udp")
            firewall.configure_ufw(["4789","51820","51821","4789"], "udp")

        pass

    def install_network_calico(self):
        # # Instalamos calico
        self.node.execute_command("kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/tigera-operator.yaml")
        self.node.execute_command("curl https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/custom-resources.yaml -O")
        self.node.execute_command("kubectl create -f custom-resources.yaml")
        self.node.execute_command("curl https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/calico.yaml -O")
        self.node.execute_command("kubectl apply -f calico.yaml")

        # # Instalar calicoctl
        self.node.execute_command("curl -L https://github.com/projectcalico/calico/releases/latest/download/calicoctl-linux-amd64 -o /usr/local/bin/kubectl-calico")
        self.node.execute_command("chmod +x /usr/local/bin/kubectl-calico")
        pass

    def configure_network_flannel(self):
        if self.config.getboolean("global", "firewall"):
            firewall = node_firewall.NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["8285", "8472"], "udp", "Calico ports")
            firewall.configure_firewalld(["8285", "8472"], "udp")
            firewall.configure_ufw(["8285", "8472"], "udp")

        self.node.execute_command("mkdir -p /opt/cni/bin")
        self.node.execute_command("curl -O -L https://github.com/containernetworking/plugins/releases/download/v1.2.0/cni-plugins-linux-amd64-v1.2.0.tgz")
        self.node.execute_command("tar -C /opt/cni/bin -xzf cni-plugins-linux-amd64-v1.2.0.tgz")

        pass

    def install_network_flannel(self):
        # # Instalamos flannel
        self.node.execute_command("kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml")
        pass
