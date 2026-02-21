import logging
import configparser
from time import sleep

from models.node import Node
from modules.node_firewall import NodeFirewall

logger = logging.getLogger(__name__)


class K8sNetwork:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s_components" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'k8s_components' section")

        self.node = node
        self.config = config

    def configure_network(self):
        network = self.config["k8s_components"]["network"]
        if network == "calico":
            self._configure_calico()
        elif network == "flannel":
            self._configure_flannel()
        else:
            raise ValueError(f"Unsupported network plugin: {network}")

        self._install_network()

    def _install_network(self):
        if self.node.node_type != "master":
            logger.info("Network plugin installation skipped on worker node")
            return

        network = self.config["k8s_components"]["network"]
        if network == "calico":
            self._install_calico()
        elif network == "flannel":
            self._install_flannel()

        logger.info("Waiting 120 seconds for network plugin to initialize...")
        sleep(120)

    def _configure_calico(self):
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            # Calico requires: VXLAN (4789/udp), WireGuard (51820-51821/udp)
            firewall.configure_iptables(["4789", "51820", "51821"], "udp", "Calico network ports")
            firewall.configure_firewalld(["4789", "51820", "51821"], "udp")
            firewall.configure_ufw(["4789", "51820", "51821"], "udp")
            # Calico BGP port
            firewall.configure_iptables(["179"], "tcp", "Calico BGP port")
            firewall.configure_firewalld(["179"], "tcp")
            firewall.configure_ufw(["179"], "tcp")

    def _install_calico(self):
        logger.info("Installing Calico network plugin")
        calico_version = self.config["k8s_components"].get("calico_version", "v3.26.1")
        self.node.execute_command(
            f"kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/{calico_version}/manifests/tigera-operator.yaml"
        )
        self.node.execute_command(
            f"curl -sO https://raw.githubusercontent.com/projectcalico/calico/{calico_version}/manifests/custom-resources.yaml"
        )
        self.node.execute_command("kubectl create -f custom-resources.yaml")
        self.node.execute_command(
            f"curl -sO https://raw.githubusercontent.com/projectcalico/calico/{calico_version}/manifests/calico.yaml"
        )
        self.node.execute_command("kubectl apply -f calico.yaml")

        # Install calicoctl
        self.node.execute_command(
            "curl -sL https://github.com/projectcalico/calico/releases/latest/download/calicoctl-linux-amd64 "
            "-o /usr/local/bin/kubectl-calico"
        )
        self.node.execute_command("chmod +x /usr/local/bin/kubectl-calico")
        logger.info("Calico installation completed")

    def _configure_flannel(self):
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            # Flannel requires: UDP backend (8285/udp), VXLAN (8472/udp)
            firewall.configure_iptables(["8285", "8472"], "udp", "Flannel network ports")
            firewall.configure_firewalld(["8285", "8472"], "udp")
            firewall.configure_ufw(["8285", "8472"], "udp")

        # Install CNI plugins
        cni_version = self.config["k8s_components"].get("flannel_cni_version", "v1.2.0")
        self.node.execute_command("mkdir -p /opt/cni/bin")
        self.node.execute_command(
            f"curl -sOL https://github.com/containernetworking/plugins/releases/download/{cni_version}/"
            f"cni-plugins-linux-amd64-{cni_version}.tgz"
        )
        self.node.execute_command(f"tar -C /opt/cni/bin -xzf cni-plugins-linux-amd64-{cni_version}.tgz")

    def _install_flannel(self):
        logger.info("Installing Flannel network plugin")
        self.node.execute_command(
            "kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml"
        )
        logger.info("Flannel installation completed")
