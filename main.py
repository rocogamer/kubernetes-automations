import configparser
import logging
import os
import sys

from models.node import Node
from modules.node_installation import NodeInstallation
from modules.node_firewall import NodeFirewall
from modules.node_ha import NodeHA
from modules.k8s_network import K8sNetwork
from modules.k8s_storage import K8sStorage
from modules.k8s_ingress import K8sIngress
from modules.k8s_loadbalancer import K8sLoadBalancer
from modules.k8s_metrics import K8sMetrics
from modules.k8s_monitoring import K8sMonitoring
from modules.k8s_security import K8sSecurity
from modules.k8s_opa import K8sOPA

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/k8s-automation.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

    if not os.path.isfile(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)

    logger.info("=== Kubernetes Automation Starting ===")

    # Create node object
    node = Node(config)
    logger.info(f"Node: {node.node_name} ({node.node_ip}) - Type: {node.node_type}")

    # 1. Pre-install node (containerd, kernel modules, k8s repo)
    logger.info("--- Phase 1: Node pre-installation ---")
    installer = NodeInstallation(node, config)
    installer.pre_install_node()

    # 2. Configure firewall
    if config.getboolean("global", "firewall"):
        logger.info("--- Phase 2: Firewall configuration ---")
        firewall = NodeFirewall(node, config)
        firewall.install_firewall()

    # 3. Configure HA (if enabled, before node installation)
    if config.getboolean("k8s", "master_ha_installation"):
        logger.info("--- Phase 3: HA configuration ---")
        ha = NodeHA(node, config)
        ha.configure_ha()

    # 4. Install Kubernetes node (kubeadm, kubelet, kubectl)
    logger.info("--- Phase 4: Kubernetes node installation ---")
    installer.install_node()

    # The following components are only installed on master nodes
    if node.node_type != "master":
        logger.info("Worker node setup complete. Skipping component installation.")
        logger.info("=== Kubernetes Automation Finished ===")
        return

    # 5. Install network plugin
    logger.info("--- Phase 5: Network plugin ---")
    network = K8sNetwork(node, config)
    network.configure_network()

    # 6. Install storage components
    logger.info("--- Phase 6: Storage components ---")
    storage = K8sStorage(node, config)
    storage.configure_storage()

    # 7. Install LoadBalancer (MetalLB)
    logger.info("--- Phase 7: LoadBalancer ---")
    lb = K8sLoadBalancer(node, config)
    lb.configure_loadbalancer()

    # 8. Install Ingress controllers
    logger.info("--- Phase 8: Ingress controllers ---")
    ingress = K8sIngress(node, config)
    ingress.configure_ingress()

    # 9. Install Metrics Server
    logger.info("--- Phase 9: Metrics server ---")
    metrics = K8sMetrics(node, config)
    metrics.configure_metrics()

    # 10. Install Monitoring (Grafana + Prometheus, Checkmk)
    logger.info("--- Phase 10: Monitoring ---")
    monitoring = K8sMonitoring(node, config)
    monitoring.configure_monitoring()

    # 11. Install Security (Falco)
    logger.info("--- Phase 11: Security ---")
    security = K8sSecurity(node, config)
    security.configure_security()

    # 12. Install OPA (Gatekeeper)
    logger.info("--- Phase 12: OPA ---")
    opa = K8sOPA(node, config)
    opa.configure_opa()

    logger.info("=== Kubernetes Automation Finished ===")


if __name__ == "__main__":
    main()
