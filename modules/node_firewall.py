class NodeFirewall:
    # Definimos el constructor
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise Exception("Node must be a Node object")

        if type(config).__name__ != "ConfigParser" and "node_firewall" not in config.sections():
            raise Exception("Config must be a ConfigParser object and the section node_firewall must be in the config")

        self.node = node
        self.config = config

    def install_firewall(self):
        if self.config["global"]["firewall"]:
            self.node.excute_command("apt update")
            if self.config["firewall"]["iptables"]:
                self.node.execute_command("apt install -y iptables")

            if self.config["firewall"]["firewalld"]:
                self.node.execute_command("apt install -y firewalld")

            if self.config["firewall"]["ufw"]:
                self.node.execute_command("apt install -y ufw")

            self.configure_firewall()
        else:
            print("Firewall configuration disabled")

    def configure_firewall(self):
        # Ajustar firewall:
        #  - Se necesitara lo siguiente para los master: 6443, 2379, 2380, 10250, 10251, 10252
        #  - Se necesitara lo siguiente para los workers: 10250, 30000-32767
        if self.node.node_type == "master":
            self.configure_iptables(["6443","2379","2380","10250","10251","10252","30000:32767"], "tcp", "Puertos necesarios para K8s")
            self.configure_firewalld(["6443","2379","2380","10250","10251","10252","30000:32767"], "tcp")
            self.configure_ufw(["6443","2379","2380","10250","10251","10252","30000:32767"], "tcp")
        else:
            self.configure_iptables(["10250","30000:32767"], "tcp", "Puertos necesarios para K8s")
            self.configure_firewalld(["10250","30000:32767"], "tcp")
            self.configure_ufw(["10250","30000:32767"], "tcp")

    def configure_iptables(self, ports=[], proto="tcp", comment="Puertos necesarios para K8s"):
        if ports == []:
            return

        if self.config["firewall"]["iptables"]:
            if len(ports) > 1 and not ports[0].__contains__(":"):
                ports = ",".join(ports)
                self.node.execute_command(
                    f"iptables -A INPUT -p {proto} -m multiport -m comment --dports {ports}"
                    f" -j ACCEPT --comment '{comment}'")
            else:
                self.node.execute_command(
                    f"iptables -A INPUT -p {proto} -m comment --dport {ports[0]}"
                    f" -j ACCEPT --comment '{comment}'")

            if self.config["firewall"]["iptables_save"]:
                self.node.execute_command("iptables-save > /etc/iptables/rules.v4")

            if self.config["firewall"]["firewall_script"] != "NA":
                # Hacemos append de los comandos de iptables al script
                file = open(self.config["firewall"]["firewall_script"], "a")
                if len(ports) > 1 and not ports[0].__contains__(":"):
                    ports = ",".join(ports)
                    file.write(
                        f"iptables -A INPUT -p {proto} -m multiport -m comment --dports {ports}"
                        f" -j ACCEPT --comment '{comment}'")
                else:
                    file.write(
                        f"iptables -A INPUT -p {proto} -m comment --dport {ports[0]}"
                        f" -j ACCEPT --comment '{comment}'")
                file.close()
        else:
            print("iptables configuration disabled")

    def configure_firewalld(self, ports=[], proto="tcp"):
        if self.config["firewall"]["firewalld"]:
            for i, port in enumerate(ports):
                self.node.execute_command(
                    f"firewall-cmd --permanent --add-port={port}/{proto} --zone={self.config['firewall']['firewalld_zone']} --permanent --add-port={port}/{proto}"
                )

            self.node.execute_command("firewall-cmd --reload")

            if self.config["firewall"]["firewall_script"] != "NA":
                # Hacemos append de los comandos de firewalld al script
                file = open(self.config["firewall"]["firewall_script"], "a")
                for i, port in enumerate(ports):
                    file.write(
                        f"firewall-cmd --permanent --add-port={port}/{proto} --zone={self.config['firewall']['firewalld_zone']} --permanent --add-port={port}/{proto}"
                    )
                file.close()
        else:
            print("firewalld configuration disabled")

    def configure_ufw(self, ports=[], proto="tcp"):
        if self.config["firewall"]["ufw"]:
            for i, port in enumerate(ports):
                self.node.execute_command(f"ufw allow {port}/{proto}")
            self.node.execute_command("ufw reload")

            if self.config["firewall"]["firewall_script"] != "NA":
                # Hacemos append de los comandos de ufw al script
                file = open(self.config["firewall"]["firewall_script"], "a")
                for i, port in enumerate(ports):
                    file.write(f"ufw allow {port}/{proto}")
                file.close()
        else:
            print("ufw configuration disabled")
