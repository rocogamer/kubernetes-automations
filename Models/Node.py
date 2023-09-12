import os


class Node:
    def __init__(self, node_type, node_name="NA", node_ip="NA"):
        if node_type.lower() != "master" and node_type.lower() != "worker":
            raise Exception("Node type must be master or worker")

        self.node_type = node_type

        self.node_name = os.popen("hostname").read().strip() if node_name == "NA" else node_name
        self.node_ip = os.popen("hostname -I").read().strip() if node_ip == "NA" else node_ip

    def execute_command(self, command):
        os.system(command)
