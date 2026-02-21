import logging

from modules.node_firewall import NodeFirewall

logger = logging.getLogger(__name__)


class K8sStorage:
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise TypeError("node must be a Node object")
        if type(config).__name__ != "ConfigParser" or "k8s_components_storage" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'k8s_components_storage' section")

        self.node = node
        self.config = config

    def configure_storage(self):
        if not self.config.getboolean("k8s_components", "storage"):
            logger.info("Storage component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("Storage components are only installed on master nodes")
            return

        if self.config.getboolean("k8s_components_storage", "longhorn"):
            self._install_longhorn()

        if self.config.getboolean("k8s_components_storage", "rook"):
            self._install_rook()

        if self.config.getboolean("k8s_components_storage", "flexvolume"):
            self._install_flexvolume_cifs()

    def _install_longhorn(self):
        logger.info("Installing Longhorn storage")

        # Longhorn prerequisites
        self.node.execute_command(
            "DEBIAN_FRONTEND=noninteractive apt install -y open-iscsi nfs-common"
        )
        self.node.execute_command("systemctl enable iscsid")
        self.node.execute_command("systemctl start iscsid")

        # Configure firewall for Longhorn (port 9500 for UI, 9501-9504 for internal)
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["9500", "9501", "9502", "9503", "9504"], "tcp", "Longhorn ports")
            firewall.configure_firewalld(["9500", "9501", "9502", "9503", "9504"], "tcp")
            firewall.configure_ufw(["9500", "9501", "9502", "9503", "9504"], "tcp")

        # Install Longhorn via kubectl
        self.node.execute_command(
            "kubectl apply -f https://raw.githubusercontent.com/longhorn/longhorn/v1.5.1/deploy/longhorn.yaml"
        )
        logger.info("Longhorn installation completed")

    def _install_rook(self):
        logger.info("Installing Rook-Ceph storage")

        # Clone Rook repository and apply manifests
        self.node.execute_command(
            "git clone --single-branch --branch v1.12.5 https://github.com/rook/rook.git /tmp/rook"
        )
        self.node.execute_command("kubectl create -f /tmp/rook/deploy/examples/crds.yaml")
        self.node.execute_command("kubectl create -f /tmp/rook/deploy/examples/common.yaml")
        self.node.execute_command("kubectl create -f /tmp/rook/deploy/examples/operator.yaml")
        self.node.execute_command("kubectl create -f /tmp/rook/deploy/examples/cluster.yaml")

        # Cleanup
        self.node.execute_command("rm -rf /tmp/rook")
        logger.info("Rook-Ceph installation completed")

    def _install_flexvolume_cifs(self):
        logger.info("Installing FlexVolume CIFS driver")

        # Install CIFS utilities
        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y cifs-utils")

        # Install CIFS FlexVolume driver
        self.node.execute_command("mkdir -p /usr/libexec/kubernetes/kubelet-plugins/volume/exec/fstab~cifs")
        self.node.execute_command(
            "curl -sL https://raw.githubusercontent.com/fstab/cifs/master/cifs "
            "-o /usr/libexec/kubernetes/kubelet-plugins/volume/exec/fstab~cifs/cifs"
        )
        self.node.execute_command(
            "chmod +x /usr/libexec/kubernetes/kubelet-plugins/volume/exec/fstab~cifs/cifs"
        )

        # Configure firewall for CIFS (ports 137-139, 445)
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["137", "138", "139", "445"], "tcp", "CIFS ports")
            firewall.configure_firewalld(["137", "138", "139", "445"], "tcp")
            firewall.configure_ufw(["137", "138", "139", "445"], "tcp")

        logger.info("FlexVolume CIFS installation completed")
