import configparser
import logging
import os
import sys
import time

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


def validate_config(config):
    """Validate that all required configuration sections and keys exist."""
    required_sections = ["global", "node_firewall", "k8s", "k8s_etc_backup", "k8s_components"]
    missing = [s for s in required_sections if s not in config.sections()]
    if missing:
        raise ValueError(f"Missing required config sections: {missing}")

    # Validate Proxmox config if enabled
    if config.getboolean("global", "proxmox_provision", fallback=False):
        if "proxmox" not in config.sections():
            raise ValueError("proxmox_provision is enabled but [proxmox] section is missing")
        required_proxmox = ["host", "user", "node"]
        for key in required_proxmox:
            if not config["proxmox"].get(key):
                raise ValueError(f"Proxmox config requires '{key}' in [proxmox] section")
        # Check auth method
        has_password = bool(config["proxmox"].get("password", ""))
        has_token = bool(config["proxmox"].get("token_name", "")) and bool(
            config["proxmox"].get("token_value", "")
        )
        if not has_password and not has_token:
            raise ValueError(
                "Proxmox requires either 'password' or both 'token_name' and 'token_value'"
            )


def install_node(node, config):
    """Run the full K8s installation pipeline on a single node."""
    logger.info(f"=== Installing on node: {node.node_name} ({node.node_ip}) [{node.node_type}] ===")

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
    if config.getboolean("k8s", "master_ha_installation") and node.node_type == "master":
        logger.info("--- Phase 3: HA configuration ---")
        ha = NodeHA(node, config)
        ha.configure_ha()

    # 4. Install Kubernetes node (kubeadm, kubelet, kubectl)
    logger.info("--- Phase 4: Kubernetes node installation ---")
    installer.install_node()

    # The following components are only installed on master nodes
    if node.node_type != "master":
        logger.info(f"Worker node {node.node_name} setup complete.")
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

    logger.info(f"Master node {node.node_name} setup complete.")


def run_proxmox_mode(config):
    """Provision VMs in Proxmox and install K8s on each one via SSH."""
    from modules.proxmox_provisioner import ProxmoxProvisioner

    logger.info("=== Proxmox Provisioning Mode ===")

    # Phase 0: Create VMs in Proxmox
    logger.info("--- Phase 0: Provisioning VMs in Proxmox ---")
    provisioner = ProxmoxProvisioner(config)
    vms = provisioner.provision()

    ssh_user = config["proxmox"].get("ssh_user", "root")
    ssh_key = config["proxmox"].get("ssh_private_key_file", "")

    # Separate masters and workers
    masters = [vm for vm in vms if vm["role"] == "master"]
    workers = [vm for vm in vms if vm["role"] == "worker"]

    if not masters:
        raise ValueError("No master nodes defined in Proxmox VM config")

    logger.info(f"Cluster: {len(masters)} master(s), {len(workers)} worker(s)")

    # Install on the first master (initializes the cluster)
    primary_master = masters[0]
    master_node = Node(
        node_type="master",
        node_name=primary_master["name"],
        node_ip=primary_master["ip"],
        ssh_user=ssh_user,
        ssh_key_file=ssh_key,
    )

    install_node(master_node, config)

    # Get join token and cert hash from the master
    join_token = ""
    join_cert = ""
    if workers or len(masters) > 1:
        logger.info("Retrieving kubeadm join token from master...")
        join_token = master_node.execute_command_output(
            "kubeadm token create --print-join-command 2>/dev/null "
            "| grep -oP '(?<=--token )\\S+'"
        )
        join_cert = master_node.execute_command_output(
            "openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt "
            "| openssl rsa -pubin -outform der 2>/dev/null "
            "| openssl dgst -sha256 -hex | sed 's/^.* //'"
        )
        master_port = "6443"

        if not join_token or not join_cert:
            logger.error(
                "Failed to retrieve join token/cert from master. "
                "Workers cannot join the cluster automatically."
            )
        else:
            # Update config with join credentials for workers
            config.set("k8s", "master_ip", primary_master["ip"])
            config.set("k8s", "master_port", master_port)
            config.set("k8s", "master_token", join_token)
            config.set("k8s", "master_cert", join_cert)

    # Install on additional masters (if any)
    for extra_master in masters[1:]:
        logger.info(f"--- Installing additional master: {extra_master['name']} ---")
        extra_node = Node(
            node_type="master",
            node_name=extra_master["name"],
            node_ip=extra_master["ip"],
            ssh_user=ssh_user,
            ssh_key_file=ssh_key,
        )
        install_node(extra_node, config)
        extra_node.close()

    # Install on workers
    for worker_vm in workers:
        logger.info(f"--- Installing worker: {worker_vm['name']} ---")
        worker_node = Node(
            node_type="worker",
            node_name=worker_vm["name"],
            node_ip=worker_vm["ip"],
            ssh_user=ssh_user,
            ssh_key_file=ssh_key,
        )
        install_node(worker_node, config)
        worker_node.close()

    # Final status
    logger.info("--- Cluster Status ---")
    master_node.execute_command("kubectl get nodes -o wide")
    master_node.close()


def run_local_mode(config):
    """Original mode: install K8s on the local machine."""
    node = Node(config)
    logger.info(f"Node: {node.node_name} ({node.node_ip}) - Type: {node.node_type}")
    install_node(node, config)


def main():
    # Check root privileges
    if os.geteuid() != 0:
        print("Error: This script must be run as root (use sudo)")
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

    if not os.path.isfile(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        validate_config(config)
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)

    logger.info("=== Kubernetes Automation Starting ===")

    if config.getboolean("global", "proxmox_provision", fallback=False):
        run_proxmox_mode(config)
    else:
        run_local_mode(config)

    logger.info("=== Kubernetes Automation Finished ===")


if __name__ == "__main__":
    main()
