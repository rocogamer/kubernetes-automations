import logging

from modules.node_firewall import NodeFirewall

logger = logging.getLogger(__name__)


class K8sMonitoring:
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise TypeError("node must be a Node object")
        if type(config).__name__ != "ConfigParser" or "k8s_components_monitoring" not in config.sections():
            raise ValueError(
                "config must be a ConfigParser object with a 'k8s_components_monitoring' section"
            )

        self.node = node
        self.config = config

    def configure_monitoring(self):
        if not self.config.getboolean("k8s_components", "monitoring"):
            logger.info("Monitoring component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("Monitoring components are only installed from master nodes")
            return

        if self.config.getboolean("k8s_components_monitoring", "grafana"):
            self._install_grafana_prometheus()

        if self.config.getboolean("k8s_components_monitoring", "check_mk"):
            self._install_checkmk_agent()

    def _install_grafana_prometheus(self):
        logger.info("Installing Grafana + Prometheus stack (kube-prometheus-stack)")

        # Open firewall ports: Grafana (3000), Prometheus (9090), Alertmanager (9093)
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["3000", "9090", "9093"], "tcp", "Monitoring ports")
            firewall.configure_firewalld(["3000", "9090", "9093"], "tcp")
            firewall.configure_ufw(["3000", "9090", "9093"], "tcp")

        # Create monitoring namespace
        self.node.execute_command(
            "kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -"
        )

        # Install kube-prometheus-stack using manifests
        self.node.execute_command(
            "git clone --depth 1 https://github.com/prometheus-operator/kube-prometheus.git /tmp/kube-prometheus"
        )
        self.node.execute_command("kubectl apply --server-side -f /tmp/kube-prometheus/manifests/setup")
        self.node.execute_command(
            "kubectl wait --for condition=Established --all CustomResourceDefinition "
            "--namespace=monitoring --timeout=120s"
        )
        self.node.execute_command("kubectl apply -f /tmp/kube-prometheus/manifests/")

        # Cleanup
        self.node.execute_command("rm -rf /tmp/kube-prometheus")

        logger.info("Grafana + Prometheus stack installed in 'monitoring' namespace")

    def _install_checkmk_agent(self):
        logger.info("Installing Checkmk agent for Kubernetes")

        # Open firewall port for Checkmk agent (6556)
        if self.config.getboolean("global", "firewall"):
            firewall = NodeFirewall(self.node, self.config)
            firewall.configure_iptables(["6556"], "tcp", "Checkmk agent port")
            firewall.configure_firewalld(["6556"], "tcp")
            firewall.configure_ufw(["6556"], "tcp")

        # Create namespace for Checkmk
        self.node.execute_command(
            "kubectl create namespace checkmk --dry-run=client -o yaml | kubectl apply -f -"
        )

        # Deploy Checkmk Kubernetes collector as DaemonSet
        checkmk_manifest = """apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkmk
  namespace: checkmk
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: checkmk
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods", "services", "endpoints", "namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: checkmk
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: checkmk
subjects:
  - kind: ServiceAccount
    name: checkmk
    namespace: checkmk
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: checkmk-agent
  namespace: checkmk
  labels:
    app: checkmk-agent
spec:
  selector:
    matchLabels:
      app: checkmk-agent
  template:
    metadata:
      labels:
        app: checkmk-agent
    spec:
      serviceAccountName: checkmk
      containers:
        - name: checkmk-agent
          image: checkmk/check-mk-raw:2.2.0-latest
          ports:
            - containerPort: 6556
              hostPort: 6556
          securityContext:
            privileged: true
          volumeMounts:
            - name: proc
              mountPath: /host/proc
              readOnly: true
            - name: sys
              mountPath: /host/sys
              readOnly: true
      volumes:
        - name: proc
          hostPath:
            path: /proc
        - name: sys
          hostPath:
            path: /sys
"""
        with open("/tmp/checkmk-agent.yaml", "w") as f:
            f.write(checkmk_manifest)
        self.node.execute_command("kubectl apply -f /tmp/checkmk-agent.yaml")
        self.node.execute_command("rm -f /tmp/checkmk-agent.yaml")

        logger.info("Checkmk agent installed as DaemonSet in 'checkmk' namespace")
