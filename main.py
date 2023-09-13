import configparser
import os

import models.node as node
import modules.node_installation as node_installation
import modules.node_firewall as node_firewall


def main():
    # Comprobamos que existe el fichero config.ini
    if not os.path.isfile("config.ini"):
        print("No existe el fichero de configuracion config.ini")
        exit(1)

    config = configparser.ConfigParser()
    config.read('config.ini')
    master_node = node.Node(config['k8s']['node_type'])

    # Hacemos la pre instalacion del nodo
    master_install = node_installation.NodeInstallation(master_node, config)
    master_install.pre_install_node()

    # Preparamos firewall
    if config.getboolean("global", "firewall"):
        master_firewall = node_firewall.NodeFirewall(master_node, config)
        master_firewall.install_firewall()
        master_firewall.configure_firewall()

    # Instalamos el nodo
    master_install.install_node()


if __name__ == "__main__":
    main()
