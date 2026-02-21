import logging
import configparser

from models.node import Node

logger = logging.getLogger(__name__)


class K8sSecurity:
    def __init__(self, node, config):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node object")
        if not isinstance(config, configparser.ConfigParser) or "k8s_components_security" not in config.sections():
            raise ValueError(
                "config must be a ConfigParser object with a 'k8s_components_security' section"
            )

        self.node = node
        self.config = config

    def configure_security(self):
        if not self.config.getboolean("k8s_components", "security"):
            logger.info("Security component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("Security components are only installed from master nodes")
            return

        if self.config.getboolean("k8s_components_security", "falco"):
            self._install_falco()

    def _install_falco(self):
        logger.info("Installing Falco runtime security")

        falco_version = self.config["k8s_components_security"].get("falco_version", "0.36.2")

        # Create namespace
        self.node.execute_command(
            "kubectl create namespace falco --dry-run=client -o yaml | kubectl apply -f -"
        )

        # Install Falco using official manifests
        falco_manifest = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: falco
  namespace: falco
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: falco
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods", "namespaces", "replicationcontrollers", "services", "events", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["daemonsets", "deployments", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]
  - nonResourceURLs: ["/healthz", "/healthz/*"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: falco
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: falco
subjects:
  - kind: ServiceAccount
    name: falco
    namespace: falco
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: falco
  namespace: falco
  labels:
    app: falco
spec:
  selector:
    matchLabels:
      app: falco
  template:
    metadata:
      labels:
        app: falco
    spec:
      serviceAccountName: falco
      hostNetwork: true
      hostPID: true
      tolerations:
        - effect: NoSchedule
          key: node-role.kubernetes.io/master
      containers:
        - name: falco
          image: falcosecurity/falco-no-driver:{falco_version}
          securityContext:
            privileged: true
          volumeMounts:
            - name: dev
              mountPath: /host/dev
            - name: proc
              mountPath: /host/proc
              readOnly: true
            - name: boot
              mountPath: /host/boot
              readOnly: true
            - name: lib-modules
              mountPath: /host/lib/modules
              readOnly: true
            - name: usr
              mountPath: /host/usr
              readOnly: true
            - name: etc
              mountPath: /host/etc
              readOnly: true
      volumes:
        - name: dev
          hostPath:
            path: /dev
        - name: proc
          hostPath:
            path: /proc
        - name: boot
          hostPath:
            path: /boot
        - name: lib-modules
          hostPath:
            path: /lib/modules
        - name: usr
          hostPath:
            path: /usr
        - name: etc
          hostPath:
            path: /etc
"""
        with open("/tmp/falco.yaml", "w") as f:
            f.write(falco_manifest)
        self.node.execute_command("kubectl apply -f /tmp/falco.yaml")
        self.node.execute_command("rm -f /tmp/falco.yaml")

        logger.info("Falco runtime security installed as DaemonSet in 'falco' namespace")
