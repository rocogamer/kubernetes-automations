import logging
import configparser

from models.node import Node
from modules.node_firewall import NodeFirewall

logger = logging.getLogger(__name__)


class NodeHA:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'k8s' section")

        self.node = node
        self.config = config

    def configure_ha(self):
        if not self.config.getboolean("k8s", "master_ha_installation"):
            logger.info("HA installation disabled")
            return

        lb_ip = self.config["k8s"]["master_load_balancer_ip"]
        if not lb_ip:
            raise ValueError("master_load_balancer_ip is required for HA installation")

        logger.info("Configuring HA with KeepAlived and HAProxy")
        self._install_keepalived(lb_ip)
        self._install_haproxy(lb_ip)

    def _install_keepalived(self, virtual_ip):
        logger.info("Installing KeepAlived")

        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y keepalived")

        # Open VRRP protocol on firewall
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["112"], "tcp", "VRRP keepalived")
            firewall.configure_firewalld(["112"], "tcp")
            firewall.configure_ufw(["112"], "tcp")

        # Determine priority based on whether this is the primary master
        priority = "100"
        state = "BACKUP"
        master_ip = self.config["k8s"].get("master_ip", "")
        if not master_ip or master_ip == self.node.node_ip:
            priority = "200"
            state = "MASTER"

        interface = self.node.execute_command_output(
            "ip route | grep default | awk '{print $5}' | head -1"
        )
        if not interface:
            raise RuntimeError(
                "Could not detect default network interface. "
                "Ensure the node has a default route configured."
            )

        ha_auth_pass = self.config["k8s"].get("ha_auth_pass", "k8s_ha_pass")

        keepalived_conf = f"""global_defs {{
    router_id K8S_MASTER
}}

vrrp_script check_apiserver {{
    script "/etc/keepalived/check_apiserver.sh"
    interval 3
    weight -2
    fall 10
    rise 2
}}

vrrp_instance VI_1 {{
    state {state}
    interface {interface}
    virtual_router_id 51
    priority {priority}
    authentication {{
        auth_type PASS
        auth_pass {ha_auth_pass}
    }}
    virtual_ipaddress {{
        {virtual_ip}
    }}
    track_script {{
        check_apiserver
    }}
}}
"""
        self.node.execute_command("mkdir -p /etc/keepalived")
        self.node.write_remote_file("/etc/keepalived/keepalived.conf", keepalived_conf)

        # Create health check script
        check_script = (
            "#!/bin/bash\n"
            "errorExit() {\n"
            '    echo "*** $*" 1>&2\n'
            "    exit 1\n"
            "}\n\n"
            "curl --silent --max-time 2 --insecure https://localhost:6443/healthz "
            '-o /dev/null || errorExit "Error GET https://localhost:6443/healthz"\n'
        )
        self.node.write_remote_file("/etc/keepalived/check_apiserver.sh", check_script)
        self.node.execute_command("chmod +x /etc/keepalived/check_apiserver.sh")

        self.node.execute_command("systemctl enable keepalived")
        self.node.execute_command("systemctl restart keepalived")
        logger.info("KeepAlived configured")

    def _install_haproxy(self, virtual_ip):
        logger.info("Installing HAProxy for API server load balancing")

        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y haproxy")

        # Open HAProxy stats port
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["8404"], "tcp", "HAProxy stats port")
            firewall.configure_firewalld(["8404"], "tcp")
            firewall.configure_ufw(["8404"], "tcp")

        haproxy_conf = f"""frontend kubernetes-frontend
    bind {virtual_ip}:6443
    mode tcp
    option tcplog
    default_backend kubernetes-backend

backend kubernetes-backend
    mode tcp
    option tcp-check
    balance roundrobin
    server master1 {self.node.node_ip}:6443 check fall 3 rise 2

listen stats
    bind *:8404
    mode http
    stats enable
    stats uri /
    stats realm HAProxy\\ Statistics
"""
        self.node.write_remote_file("/etc/haproxy/haproxy-k8s.cfg", haproxy_conf)

        # Include in main HAProxy config
        self.node.execute_command(
            "grep -q 'haproxy-k8s.cfg' /etc/haproxy/haproxy.cfg || "
            "echo '\\n# Kubernetes API Server LB\\n"
            "include /etc/haproxy/haproxy-k8s.cfg' >> /etc/haproxy/haproxy.cfg"
        )

        self.node.execute_command("systemctl enable haproxy")
        self.node.execute_command("systemctl restart haproxy")
        logger.info("HAProxy configured for API server load balancing")
