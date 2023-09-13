import os


class Node:
    def __init__(self, config = None, node_type = "NA", node_name="NA", node_ip="NA"):
        if node_type != "NA" and node_type.lower() != "master" and node_type.lower() != "worker":
            raise Exception("Node type must be master or worker")
        if node_type == "NA" and config is None and type(config).__name__ != "ConfigParser":
            raise Exception("Node type must be master or worker or config bust be ConfigParser object")

        self.node_name = os.popen("hostname").read().strip() if node_name == "NA" else node_name
        self.node_ip = os.popen("hostname -I").read().strip() if node_ip == "NA" else node_ip

        if node_type == "NA" and config is not None:
            self.node_type = config[f"node_{self.node_name}"]["node_type"]


    def execute_command(self, command):
        os.system(command)
