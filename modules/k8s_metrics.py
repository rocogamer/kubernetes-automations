import logging

logger = logging.getLogger(__name__)


class K8sMetrics:
    def __init__(self, node, config):
        if type(node).__name__ != "Node":
            raise TypeError("node must be a Node object")
        if type(config).__name__ != "ConfigParser" or "k8s_components_metricas" not in config.sections():
            raise ValueError(
                "config must be a ConfigParser object with a 'k8s_components_metricas' section"
            )

        self.node = node
        self.config = config

    def configure_metrics(self):
        if not self.config.getboolean("k8s_components", "metricas"):
            logger.info("Metrics component installation disabled")
            return

        if self.node.node_type != "master":
            logger.info("Metrics components are only installed from master nodes")
            return

        if self.config.getboolean("k8s_components_metricas", "Kube_metrics_server"):
            self._install_metrics_server()

    def _install_metrics_server(self):
        logger.info("Installing Kubernetes Metrics Server")

        # Install metrics-server
        self.node.execute_command(
            "kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/"
            "releases/latest/download/components.yaml"
        )

        # For bare-metal/self-signed clusters, patch to allow insecure TLS
        self.node.execute_command(
            "kubectl -n kube-system patch deployment metrics-server "
            "--type='json' -p='[{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/0/args/-\", "
            "\"value\": \"--kubelet-insecure-tls\"}]'"
        )

        logger.info("Kubernetes Metrics Server installed (HPA ready)")
