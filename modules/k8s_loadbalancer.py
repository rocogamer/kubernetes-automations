import logging
import configparser

from models.node import Node

logger = logging.getLogger(__name__)


class K8sLoadBalancer:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s_components_loadbalancer" not in config.sections():
            raise ValueError(
                "config must be a ConfigParser object with a 'k8s_components_loadbalancer' section"
            )

        self.node = node
        self.config = config

    def configure_loadbalancer(self):
        if not self.config.getboolean("k8s_components", "loadbalancer"):
            logger.info("LoadBalancer component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("LoadBalancer components are only installed from master nodes")
            return

        if self.config.getboolean("k8s_components_loadbalancer", "metalb"):
            self._install_metallb()

    def _install_metallb(self):
        logger.info("Installing MetalLB")

        # Enable strict ARP mode required by MetalLB
        self.node.execute_command(
            "kubectl get configmap kube-proxy -n kube-system -o yaml "
            "| sed -e 's/strictARP: false/strictARP: true/' "
            "| kubectl apply -f - -n kube-system"
        )

        # Install MetalLB
        metallb_version = self.config["k8s_components_loadbalancer"].get("metallb_version", "v0.13.12")
        self.node.execute_command(
            f"kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/{metallb_version}/"
            "config/manifests/metallb-native.yaml"
        )

        # Wait for MetalLB pods to be ready
        self.node.execute_command(
            "kubectl wait --namespace metallb-system "
            "--for=condition=ready pod "
            "--selector=app=metallb "
            "--timeout=120s"
        )

        logger.info(
            "MetalLB installed. You need to configure an IPAddressPool and L2Advertisement. "
            "See: https://metallb.universe.tf/configuration/"
        )
