import configparser
import os

import models.node as node
import modules.node_installation as node_installation
import modules.node_firewall as node_firewall
import modules.k8s_network as k8s_network


def main():
    # Comprobamos que existe el fichero config.ini
    if not os.path.isfile("config.ini"):
        print("No existe el fichero de configuracion config.ini")
        exit(1)

    config = configparser.ConfigParser()
    config.read('config.ini')
    master_node = node.Node(config)

    # Hacemos la pre instalacion del nodo
    master_install = node_installation.NodeInstallation(master_node, config)
    master_install.pre_install_node()

    # Preparamos firewall
    if config.getboolean("global", "firewall"):
        master_firewall = node_firewall.NodeFirewall(master_node, config)
        master_firewall.install_firewall()

    # Instalamos el nodo
    master_install.install_node()

    # Instalamos la red
    master_network = k8s_network.K8sNetwork(master_node, config)
    master_network.configure_network()


if __name__ == "__main__":
    main()
