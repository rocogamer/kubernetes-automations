import logging
import configparser

from models.node import Node

logger = logging.getLogger(__name__)


class NodeFirewall:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "node_firewall" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'node_firewall' section")

        self.node = node
        self.config = config

    def install_firewall(self):
        if not self.config.getboolean("global", "firewall"):
            logger.info("Firewall configuration disabled")
            return

        self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt update")

        if self.config.getboolean("node_firewall", "iptables"):
            self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y iptables")

        if self.config.getboolean("node_firewall", "firewalld"):
            self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y firewalld")

        if self.config.getboolean("node_firewall", "ufw"):
            self.node.execute_command("DEBIAN_FRONTEND=noninteractive apt install -y ufw")

        self.configure_firewall()

    def configure_firewall(self):
        # Master ports: 6443 (API), 2379-2380 (etcd), 10250-10252 (kubelet/scheduler/controller)
        # Worker ports: 10250 (kubelet), 30000-32767 (NodePort range)
        if self.node.node_type == "master":
            ports = ["6443", "2379", "2380", "10250", "10251", "10252", "30000:32767"]
        else:
            ports = ["10250", "30000:32767"]

        self.configure_iptables(ports, "tcp", "Kubernetes required ports")
        self.configure_firewalld(ports, "tcp")
        self.configure_ufw(ports, "tcp")

    def configure_iptables(self, ports, proto="tcp", comment="Kubernetes required ports"):
        if not ports:
            return

        if not self.config.getboolean("node_firewall", "iptables"):
            logger.info("iptables configuration disabled")
            return

        # Separate range ports from single ports
        range_ports = [p for p in ports if ":" in p]
        single_ports = [p for p in ports if ":" not in p]

        # Apply single ports with multiport match
        if single_ports:
            joined = ",".join(single_ports)
            self.node.execute_command(
                f"iptables -A INPUT -p {proto} -m multiport --dports {joined} "
                f"-m comment --comment '{comment}' -j ACCEPT"
            )

        # Apply port ranges individually
        for port_range in range_ports:
            self.node.execute_command(
                f"iptables -A INPUT -p {proto} --dport {port_range} "
                f"-m comment --comment '{comment}' -j ACCEPT"
            )

        if self.config.getboolean("node_firewall", "iptables_save"):
            self.node.execute_command("iptables-save > /etc/iptables/rules.v4")

        self._append_to_firewall_script(ports, proto, comment, "iptables")

    def configure_firewalld(self, ports, proto="tcp"):
        if not self.config.getboolean("node_firewall", "firewalld"):
            logger.info("firewalld configuration disabled")
            return

        zone = self.config["node_firewall"]["firewalld_zone"]
        for port in ports:
            self.node.execute_command(
                f"firewall-cmd --permanent --zone={zone} --add-port={port}/{proto}"
            )
        self.node.execute_command("firewall-cmd --reload")

        self._append_to_firewall_script(ports, proto, "", "firewalld")

    def configure_ufw(self, ports, proto="tcp"):
        if not self.config.getboolean("node_firewall", "ufw"):
            logger.info("ufw configuration disabled")
            return

        for port in ports:
            self.node.execute_command(f"ufw allow {port}/{proto}")
        self.node.execute_command("ufw reload")

        self._append_to_firewall_script(ports, proto, "", "ufw")

    def _append_to_firewall_script(self, ports, proto, comment, fw_type):
        script_path = self.config["node_firewall"]["firewall_script"]
        if script_path == "NA":
            return

        zone = self.config["node_firewall"].get("firewalld_zone", "public")

        with open(script_path, "a") as f:
            for port in ports:
                if fw_type == "iptables":
                    if ":" in port:
                        f.write(
                            f"iptables -A INPUT -p {proto} --dport {port} "
                            f"-m comment --comment '{comment}' -j ACCEPT\n"
                        )
                    else:
                        f.write(
                            f"iptables -A INPUT -p {proto} --dport {port} "
                            f"-m comment --comment '{comment}' -j ACCEPT\n"
                        )
                elif fw_type == "firewalld":
                    f.write(
                        f"firewall-cmd --permanent --zone={zone} --add-port={port}/{proto}\n"
                    )
                elif fw_type == "ufw":
                    f.write(f"ufw allow {port}/{proto}\n")
