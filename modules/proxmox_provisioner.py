import os
import time
import logging
import configparser

logger = logging.getLogger(__name__)


class ProxmoxProvisioner:
    """Provisions VMs in Proxmox VE for a Kubernetes cluster.

    Supports two modes:
    - Clone from an existing template (template_id > 0)
    - Create from scratch using an ISO (template_id = 0)

    VMs are configured with cloud-init for automatic network and SSH setup.
    """

    def __init__(self, config):
        if not isinstance(config, configparser.ConfigParser):
            raise TypeError("config must be a ConfigParser object")
        if "proxmox" not in config.sections():
            raise ValueError("config must contain a 'proxmox' section")

        self.config = config
        self.proxmox_config = config["proxmox"]
        self.api = None

    def _connect(self):
        """Establish connection to Proxmox VE API."""
        try:
            from proxmoxer import ProxmoxAPI
        except ImportError:
            raise RuntimeError(
                "proxmoxer is not installed. Run: pip3 install proxmoxer requests"
            )

        host = self.proxmox_config["host"]
        port = int(self.proxmox_config.get("port", "8006"))
        user = self.proxmox_config["user"]
        verify_ssl = self.proxmox_config.getboolean("verify_ssl", fallback=False)

        token_name = self.proxmox_config.get("token_name", "")
        token_value = self.proxmox_config.get("token_value", "")

        if token_name and token_value:
            logger.info(f"Connecting to Proxmox {host}:{port} with API token")
            self.api = ProxmoxAPI(
                host,
                port=port,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=verify_ssl,
            )
        else:
            password = self.proxmox_config.get("password", "")
            if not password:
                raise ValueError(
                    "Proxmox requires either password or API token (token_name + token_value)"
                )
            logger.info(f"Connecting to Proxmox {host}:{port} with password")
            self.api = ProxmoxAPI(
                host,
                port=port,
                user=user,
                password=password,
                verify_ssl=verify_ssl,
            )

        logger.info("Connected to Proxmox VE successfully")

    def _get_vm_sections(self):
        """Find all proxmox_vm_* sections in the config."""
        vm_sections = []
        for section in self.config.sections():
            if section.startswith("proxmox_vm_"):
                vm_sections.append(section)
        if not vm_sections:
            raise ValueError(
                "No VM definitions found. Add [proxmox_vm_master_1], [proxmox_vm_worker_1], etc."
            )
        return sorted(vm_sections)

    def _get_vm_role(self, section_name):
        """Extract the role (master/worker) from section name."""
        # proxmox_vm_master_1 -> master
        parts = section_name.replace("proxmox_vm_", "").rsplit("_", 1)
        return parts[0] if parts else "worker"

    def _read_ssh_public_key(self):
        """Read the SSH public key for cloud-init injection."""
        key_path = self.proxmox_config.get("ssh_public_key_file", "")
        if not key_path:
            return ""
        key_path = os.path.expanduser(key_path)
        if not os.path.isfile(key_path):
            logger.warning(f"SSH public key file not found: {key_path}")
            return ""
        with open(key_path, "r") as f:
            return f.read().strip()

    def _wait_for_task(self, pve_node, task_id, timeout=120):
        """Wait for a Proxmox task to complete."""
        start = time.time()
        while time.time() - start < timeout:
            status = self.api.nodes(pve_node).tasks(task_id).status.get()
            if status["status"] == "stopped":
                if status.get("exitstatus") == "OK":
                    return True
                raise RuntimeError(
                    f"Proxmox task {task_id} failed: {status.get('exitstatus', 'unknown')}"
                )
            time.sleep(3)
        raise TimeoutError(f"Proxmox task {task_id} timed out after {timeout}s")

    def _vm_exists(self, pve_node, vmid):
        """Check if a VM with the given VMID already exists."""
        try:
            self.api.nodes(pve_node).qemu(vmid).status.current.get()
            return True
        except Exception:
            return False

    def _create_vm_from_template(self, pve_node, vm_config, section_name):
        """Create a VM by cloning an existing template."""
        template_id = int(self.proxmox_config["template_id"])
        vmid = int(vm_config["vmid"])
        name = vm_config["name"]

        logger.info(f"Cloning template {template_id} -> VM {vmid} ({name})")
        task = self.api.nodes(pve_node).qemu(template_id).clone.create(
            newid=vmid,
            name=name,
            full=1,
            target=pve_node,
        )
        self._wait_for_task(pve_node, task, timeout=300)

        # Resize disk if specified
        disk_gb = int(vm_config.get("disk", "0"))
        if disk_gb > 0:
            logger.info(f"Resizing disk for VM {vmid} to {disk_gb}G")
            self.api.nodes(pve_node).qemu(vmid).resize.put(
                disk="scsi0",
                size=f"{disk_gb}G",
            )

        # Update VM hardware
        self._configure_vm_hardware(pve_node, vmid, vm_config)
        # Configure cloud-init
        self._configure_cloud_init(pve_node, vmid, vm_config)

    def _create_vm_from_scratch(self, pve_node, vm_config, section_name):
        """Create a new VM from scratch with an ISO."""
        vmid = int(vm_config["vmid"])
        name = vm_config["name"]
        cores = int(vm_config.get("cores", "2"))
        memory = int(vm_config.get("memory", "4096"))
        disk_gb = int(vm_config.get("disk", "32"))
        storage = self.proxmox_config.get("storage", "local-lvm")
        bridge = self.proxmox_config.get("bridge", "vmbr0")
        iso = self.proxmox_config.get("iso", "")

        logger.info(f"Creating VM {vmid} ({name}) from scratch")

        create_params = {
            "vmid": vmid,
            "name": name,
            "cores": cores,
            "memory": memory,
            "ostype": "l26",
            "scsihw": "virtio-scsi-single",
            "scsi0": f"{storage}:{disk_gb},iothread=1",
            "net0": f"virtio,bridge={bridge}",
            "boot": "order=scsi0;ide2",
            "agent": "1,fstrim_cloned_disks=1",
            "serial0": "socket",
            "vga": "serial0",
        }

        # Add ISO if specified
        if iso:
            create_params["ide2"] = f"{iso},media=cdrom"

        # Add cloud-init drive
        create_params["ide0"] = f"{storage}:cloudinit"

        # Add VLAN if specified
        vlan = self.proxmox_config.get("vlan", "")
        if vlan:
            create_params["net0"] = f"virtio,bridge={bridge},tag={vlan}"

        self.api.nodes(pve_node).qemu.create(**create_params)
        logger.info(f"VM {vmid} ({name}) created")

        # Configure cloud-init
        self._configure_cloud_init(pve_node, vmid, vm_config)

    def _configure_vm_hardware(self, pve_node, vmid, vm_config):
        """Update VM CPU, memory, and network settings."""
        cores = int(vm_config.get("cores", "2"))
        memory = int(vm_config.get("memory", "4096"))
        bridge = self.proxmox_config.get("bridge", "vmbr0")

        update_params = {
            "cores": cores,
            "memory": memory,
        }

        vlan = self.proxmox_config.get("vlan", "")
        if vlan:
            update_params["net0"] = f"virtio,bridge={bridge},tag={vlan}"
        else:
            update_params["net0"] = f"virtio,bridge={bridge}"

        self.api.nodes(pve_node).qemu(vmid).config.put(**update_params)
        logger.info(f"VM {vmid}: {cores} cores, {memory}MB RAM")

    def _configure_cloud_init(self, pve_node, vmid, vm_config):
        """Configure cloud-init settings for the VM."""
        ip = vm_config["ip"]
        cidr = self.proxmox_config.get("cidr", "24")
        gateway = self.proxmox_config.get("gateway", "")
        ssh_user = self.proxmox_config.get("ssh_user", "root")
        dns_domain = self.proxmox_config.get("dns_domain", "")
        dns_servers = self.proxmox_config.get("dns_servers", "")
        ssh_public_key = self._read_ssh_public_key()

        ci_params = {
            "ipconfig0": f"ip={ip}/{cidr}" + (f",gw={gateway}" if gateway else ""),
            "ciuser": ssh_user,
        }

        if ssh_public_key:
            ci_params["sshkeys"] = ssh_public_key.replace("\n", "")

        if dns_servers:
            ci_params["nameserver"] = dns_servers

        if dns_domain:
            ci_params["searchdomain"] = dns_domain

        self.api.nodes(pve_node).qemu(vmid).config.put(**ci_params)
        logger.info(f"VM {vmid}: cloud-init configured with IP {ip}/{cidr}")

    def _start_vm(self, pve_node, vmid, name):
        """Start a VM and wait for it to be running."""
        status = self.api.nodes(pve_node).qemu(vmid).status.current.get()
        if status["status"] == "running":
            logger.info(f"VM {vmid} ({name}) is already running")
            return

        logger.info(f"Starting VM {vmid} ({name})")
        task = self.api.nodes(pve_node).qemu(vmid).status.start.create()
        self._wait_for_task(pve_node, task, timeout=60)
        logger.info(f"VM {vmid} ({name}) started")

    def _wait_for_vm_ready(self, pve_node, vmid, name, expected_ip):
        """Wait for VM to be reachable via QEMU guest agent."""
        timeout = int(self.proxmox_config.get("vm_ready_timeout", "300"))
        logger.info(f"Waiting for VM {vmid} ({name}) to be ready (timeout: {timeout}s)")

        start = time.time()
        while time.time() - start < timeout:
            try:
                ifaces = self.api.nodes(pve_node).qemu(vmid).agent("network-get-interfaces").get()
                for iface in ifaces.get("result", []):
                    for addr in iface.get("ip-addresses", []):
                        if addr.get("ip-address") == expected_ip:
                            logger.info(f"VM {vmid} ({name}) is ready with IP {expected_ip}")
                            return True
            except Exception:
                pass
            time.sleep(10)

        logger.warning(
            f"VM {vmid} ({name}) did not report IP {expected_ip} within {timeout}s. "
            "Continuing anyway - the VM may still be booting."
        )
        return False

    def provision(self):
        """Main entry point: create and start all cluster VMs.

        Returns a list of dicts with vm info:
        [{"name": "k8s-master-1", "ip": "...", "role": "master", "vmid": 200}, ...]
        """
        self._connect()

        pve_node = self.proxmox_config.get("node", "pve")
        template_id = int(self.proxmox_config.get("template_id", "0"))
        vm_sections = self._get_vm_sections()

        logger.info(f"Provisioning {len(vm_sections)} VMs on Proxmox node '{pve_node}'")

        created_vms = []

        for section in vm_sections:
            vm_config = self.config[section]
            vmid = int(vm_config["vmid"])
            name = vm_config["name"]
            role = self._get_vm_role(section)

            if self._vm_exists(pve_node, vmid):
                logger.info(f"VM {vmid} ({name}) already exists, skipping creation")
            elif template_id > 0:
                self._create_vm_from_template(pve_node, vm_config, section)
            else:
                self._create_vm_from_scratch(pve_node, vm_config, section)

            self._start_vm(pve_node, vmid, name)

            created_vms.append({
                "name": name,
                "ip": vm_config["ip"],
                "role": role,
                "vmid": vmid,
                "section": section,
            })

        # Wait for all VMs to be ready
        logger.info("Waiting for all VMs to be reachable...")
        for vm in created_vms:
            self._wait_for_vm_ready(pve_node, vm["vmid"], vm["name"], vm["ip"])

        # Sort so masters come first
        created_vms.sort(key=lambda v: (0 if v["role"] == "master" else 1, v["vmid"]))

        logger.info(f"Proxmox provisioning complete: {len(created_vms)} VMs ready")
        for vm in created_vms:
            logger.info(f"  - {vm['name']} ({vm['ip']}) [{vm['role']}]")

        return created_vms

    def destroy(self, vmids=None):
        """Destroy VMs created for the cluster (for cleanup).

        Args:
            vmids: List of VMIDs to destroy. If None, destroys all VMs from config.
        """
        self._connect()
        pve_node = self.proxmox_config.get("node", "pve")

        if vmids is None:
            vmids = []
            for section in self._get_vm_sections():
                vmids.append(int(self.config[section]["vmid"]))

        for vmid in vmids:
            if not self._vm_exists(pve_node, vmid):
                logger.info(f"VM {vmid} does not exist, skipping")
                continue

            # Stop the VM first
            try:
                status = self.api.nodes(pve_node).qemu(vmid).status.current.get()
                if status["status"] == "running":
                    logger.info(f"Stopping VM {vmid}")
                    task = self.api.nodes(pve_node).qemu(vmid).status.stop.create()
                    self._wait_for_task(pve_node, task, timeout=60)
            except Exception as e:
                logger.warning(f"Error stopping VM {vmid}: {e}")

            # Delete the VM
            logger.info(f"Deleting VM {vmid}")
            try:
                task = self.api.nodes(pve_node).qemu(vmid).delete()
                self._wait_for_task(pve_node, task, timeout=60)
                logger.info(f"VM {vmid} deleted")
            except Exception as e:
                logger.error(f"Error deleting VM {vmid}: {e}")
