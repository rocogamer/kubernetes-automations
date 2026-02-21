import logging
import configparser

from models.node import Node

logger = logging.getLogger(__name__)


class K8sOPA:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s_components_opa" not in config.sections():
            raise ValueError(
                "config must be a ConfigParser object with a 'k8s_components_opa' section"
            )

        self.node = node
        self.config = config

    def configure_opa(self):
        if not self.config.getboolean("k8s_components", "opa"):
            logger.info("OPA component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("OPA components are only installed from master nodes")
            return

        if self.config.getboolean("k8s_components_opa", "gatekeeper"):
            self._install_gatekeeper()

    def _install_gatekeeper(self):
        logger.info("Installing OPA Gatekeeper")

        gatekeeper_version = self.config["k8s_components_opa"].get("gatekeeper_version", "v3.13.3")
        # Install Gatekeeper
        self.node.execute_command(
            f"kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/"
            f"{gatekeeper_version}/deploy/gatekeeper.yaml"
        )

        # Wait for Gatekeeper to be ready
        self.node.execute_command(
            "kubectl wait --namespace gatekeeper-system "
            "--for=condition=ready pod "
            "--selector=control-plane=controller-manager "
            "--timeout=120s"
        )

        logger.info("OPA Gatekeeper installed in 'gatekeeper-system' namespace")
