import os
import subprocess
import configparser
import logging

logger = logging.getLogger(__name__)


class CommandResult:
    """Unified result object for both local and SSH command execution."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class Node:
    def __init__(self, config=None, node_type="NA", node_name="NA", node_ip="NA",
                 ssh_user=None, ssh_key_file=None):
        if node_type != "NA" and node_type.lower() not in ("master", "worker"):
            raise ValueError("Node type must be 'master' or 'worker'")
        if node_type == "NA" and (config is None or not isinstance(config, configparser.ConfigParser)):
            raise ValueError("Node type must be 'master' or 'worker', or config must be a ConfigParser object")

        self._ssh_client = None
        self._ssh_user = ssh_user
        self._ssh_key_file = ssh_key_file
        self._is_remote = ssh_user is not None and node_ip != "NA"

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

    def _get_ssh_client(self):
        """Create or return existing SSH connection to the remote node."""
        if self._ssh_client is not None:
            # Check if connection is still active
            transport = self._ssh_client.get_transport()
            if transport and transport.is_active():
                return self._ssh_client
            self._ssh_client = None

        try:
            import paramiko
        except ImportError:
            raise RuntimeError(
                "paramiko is not installed. Run: pip3 install paramiko"
            )

        logger.info(f"Opening SSH connection to {self._ssh_user}@{self.node_ip}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.node_ip,
            "username": self._ssh_user,
            "timeout": 30,
        }

        if self._ssh_key_file:
            key_path = os.path.expanduser(self._ssh_key_file)
            if os.path.isfile(key_path):
                connect_kwargs["key_filename"] = key_path
            else:
                logger.warning(f"SSH key file not found: {key_path}, using default")

        client.connect(**connect_kwargs)
        self._ssh_client = client
        logger.info(f"SSH connected to {self.node_ip}")
        return client

    def _execute_remote(self, command):
        """Execute a command on the remote node via SSH."""
        client = self._get_ssh_client()
        stdin, stdout, stderr = client.exec_command(command, timeout=600)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return CommandResult(exit_code, out, err)

    def _execute_local(self, command):
        """Execute a command locally."""
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return CommandResult(result.returncode, result.stdout, result.stderr)

    def execute_command(self, command):
        logger.info(f"Executing on {self.node_name}: {command}")

        if self._is_remote:
            result = self._execute_remote(command)
        else:
            result = self._execute_local(command)

        if result.returncode != 0:
            logger.error(f"Command failed with code {result.returncode}: {result.stderr.strip()}")
        else:
            if result.stdout.strip():
                logger.debug(result.stdout.strip())
        return result

    def execute_command_output(self, command):
        logger.info(f"Executing (capture) on {self.node_name}: {command}")

        if self._is_remote:
            result = self._execute_remote(command)
        else:
            result = self._execute_local(command)

        if result.returncode != 0:
            logger.error(f"Command failed with code {result.returncode}: {result.stderr.strip()}")
        return result.stdout.strip()

    def upload_file(self, local_path, remote_path):
        """Upload a file to the remote node via SFTP."""
        if not self._is_remote:
            logger.debug(f"Local node, skipping upload: {local_path} -> {remote_path}")
            return

        client = self._get_ssh_client()
        sftp = client.open_sftp()
        try:
            logger.info(f"Uploading {local_path} -> {self.node_ip}:{remote_path}")
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()

    def write_remote_file(self, remote_path, content):
        """Write content to a file on the remote node."""
        if not self._is_remote:
            # Local execution: write directly
            os.makedirs(os.path.dirname(remote_path), exist_ok=True)
            with open(remote_path, "w") as f:
                f.write(content)
            return

        client = self._get_ssh_client()
        sftp = client.open_sftp()
        try:
            logger.info(f"Writing file on {self.node_ip}: {remote_path}")
            with sftp.open(remote_path, "w") as f:
                f.write(content)
        finally:
            sftp.close()

    def close(self):
        """Close SSH connection if open."""
        if self._ssh_client is not None:
            self._ssh_client.close()
            self._ssh_client = None
            logger.info(f"SSH connection to {self.node_ip} closed")

    def __del__(self):
        self.close()
