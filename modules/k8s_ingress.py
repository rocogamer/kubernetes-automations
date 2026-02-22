import logging
import configparser

from models.node import Node
from modules.node_firewall import NodeFirewall

logger = logging.getLogger(__name__)


class K8sIngress:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s_components_ingress" not in config.sections():
            raise ValueError("config must be a ConfigParser object with a 'k8s_components_ingress' section")

        self.node = node
        self.config = config

    def configure_ingress(self):
        if not self.config.getboolean("k8s_components", "ingress"):
            logger.info("Ingress component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("Ingress components are only installed from master nodes")
            return

        # Open HTTP/HTTPS ports on all nodes
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["80", "443"], "tcp", "Ingress HTTP/HTTPS ports")
            firewall.configure_firewalld(["80", "443"], "tcp")
            firewall.configure_ufw(["80", "443"], "tcp")

        if self.config.getboolean("k8s_components_ingress", "nginx_ingress"):
            self._install_nginx_ingress()

        if self.config.getboolean("k8s_components_ingress", "nginx_ingress_by_kubernetes"):
            self._install_nginx_ingress_kubernetes()

        if self.config.getboolean("k8s_components_ingress", "traefik"):
            self._install_traefik()

        if self.config.getboolean("k8s_components_ingress", "haproxy_ingress"):
            self._install_haproxy_ingress()

    def _get_service_type(self):
        if self.config.getboolean("k8s_components_ingress", "expose_service_has_loadbalancer"):
            return "LoadBalancer"
        if self.config.getboolean("k8s_components_ingress", "expose_service_has_node_port"):
            return "NodePort"
        return "ClusterIP"

    def _install_nginx_ingress(self):
        logger.info("Installing NGINX Ingress Controller (community)")

        nginx_version = self.config["k8s_components_ingress"].get("nginx_ingress_version", "v1.8.2")
        # Install using official NGINX Ingress Helm chart via manifests
        self.node.execute_command(
            f"kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/"
            f"controller-{nginx_version}/deploy/static/provider/baremetal/deploy.yaml"
        )

        # Patch service type if needed
        svc_type = self._get_service_type()
        self.node.execute_command(
            f"kubectl -n ingress-nginx patch svc ingress-nginx-controller "
            f"-p '{{\"spec\":{{\"type\":\"{svc_type}\"}}}}'"
        )
        logger.info("NGINX Ingress Controller installed")

    def _install_nginx_ingress_kubernetes(self):
        logger.info("Installing NGINX Ingress Controller (Kubernetes official)")

        nginx_version = self.config["k8s_components_ingress"].get("nginx_ingress_version", "v1.8.2")
        self.node.execute_command(
            f"kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/"
            f"controller-{nginx_version}/deploy/static/provider/baremetal/deploy.yaml"
        )
        logger.info("NGINX Ingress (Kubernetes) installed")

    def _install_traefik(self):
        logger.info("Installing Traefik Ingress Controller")

        # Configure firewall for Traefik dashboard (8080)
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["8080"], "tcp", "Traefik dashboard port")
            firewall.configure_firewalld(["8080"], "tcp")
            firewall.configure_ufw(["8080"], "tcp")

        # Install Traefik CRDs and deployment
        self.node.execute_command(
            "kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/"
            "docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml"
        )
        self.node.execute_command(
            "kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/"
            "docs/content/reference/dynamic-configuration/kubernetes-crd-rbac.yml"
        )

        # Create Traefik namespace and deployment
        self.node.execute_command("kubectl create namespace traefik --dry-run=client -o yaml | kubectl apply -f -")

        svc_type = self._get_service_type()
        traefik_manifest = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: traefik
  namespace: traefik
  labels:
    app: traefik
spec:
  replicas: 1
  selector:
    matchLabels:
      app: traefik
  template:
    metadata:
      labels:
        app: traefik
    spec:
      containers:
        - name: traefik
          image: traefik:v2.10
          args:
            - --api.insecure=true
            - --providers.kubernetesingress
            - --entrypoints.web.address=:80
            - --entrypoints.websecure.address=:443
          ports:
            - name: web
              containerPort: 80
            - name: websecure
              containerPort: 443
            - name: dashboard
              containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: traefik
  namespace: traefik
spec:
  type: {svc_type}
  selector:
    app: traefik
  ports:
    - name: web
      port: 80
      targetPort: web
    - name: websecure
      port: 443
      targetPort: websecure
    - name: dashboard
      port: 8080
      targetPort: dashboard
"""
        self.node.write_remote_file("/tmp/traefik-deployment.yaml", traefik_manifest)
        self.node.execute_command("kubectl apply -f /tmp/traefik-deployment.yaml")
        self.node.execute_command("rm -f /tmp/traefik-deployment.yaml")

        logger.info("Traefik Ingress Controller installed")

    def _install_haproxy_ingress(self):
        logger.info("Installing HAProxy Ingress Controller")

        self.node.execute_command(
            "kubectl create namespace haproxy-controller --dry-run=client -o yaml | kubectl apply -f -"
        )
        haproxy_version = self.config["k8s_components_ingress"].get("haproxy_ingress_version", "v1.10")
        self.node.execute_command(
            f"kubectl apply -f https://raw.githubusercontent.com/haproxytech/kubernetes-ingress/"
            f"{haproxy_version}/deploy/haproxy-ingress.yaml"
        )

        svc_type = self._get_service_type()
        self.node.execute_command(
            f"kubectl -n haproxy-controller patch svc haproxy-ingress "
            f"-p '{{\"spec\":{{\"type\":\"{svc_type}\"}}}}'"
        )
        logger.info("HAProxy Ingress Controller installed")
