import subprocess
import configparser
import logging

logger = logging.getLogger(__name__)


class Node:
    def __init__(self, config=None, node_type="NA", node_name="NA", node_ip="NA"):
        if node_type != "NA" and node_type.lower() not in ("master", "worker"):
            raise ValueError("Node type must be 'master' or 'worker'")
        if node_type == "NA" and (config is None or not isinstance(config, configparser.ConfigParser)):
            raise ValueError("Node type must be 'master' or 'worker', or config must be a ConfigParser object")

        self.node_name = (
            subprocess.check_output(["hostname"]).decode().strip()
            if node_name == "NA" else node_name
        )
        self.node_ip = (
            subprocess.check_output(["hostname", "-I"]).decode().strip().split()[0]
            if node_ip == "NA" else node_ip
        )

        if node_type == "NA" and config is not None:
            section = f"node_{self.node_name}"
            if section not in config.sections():
                raise ValueError(f"Section '{section}' not found in config. Available: {config.sections()}")
            self.node_type = config[section]["node_type"]
        else:
            self.node_type = node_type.lower()

    def execute_command(self, command):
        logger.info(f"Executing: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Command failed with code {result.returncode}: {result.stderr.strip()}")
        else:
            if result.stdout.strip():
                logger.debug(result.stdout.strip())
        return result

    def execute_command_output(self, command):
        logger.info(f"Executing (capture): {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Command failed with code {result.returncode}: {result.stderr.strip()}")
        return result.stdout.strip()
