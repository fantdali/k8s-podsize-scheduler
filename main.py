import math
import random
from dataclasses import dataclass, field

# Objects


@dataclass
class Pod:
    name: str
    cpu_request: float
    service: str
    node: str | None = None


@dataclass
class Node:
    name: str
    allocatable_cpu: float
    pods: list[Pod] = field(default_factory=list)

    @property
    def used_cpu(self) -> float:
        return sum(p.cpu_request for p in self.pods)

    @property
    def free_cpu(self) -> float:
        return self.allocatable_cpu - self.used_cpu

    def pod_cpu_list(self) -> list[float]:
        return [p.cpu_request for p in self.pods]


@dataclass
class Service:
    name: str
    cpu_request: float
    replicas: int


# Scoring helpers


def gaussian_kernel(x: float, y: float, sigma: float) -> float:
    return math.exp(-((x - y) ** 2) / (2 * sigma**2))


# Soft-bucket anchors: (center, sigma, alpha weight)
# Sigma controls bucket width, tighter = more distinct buckets.
# Alpha weights let emphasise certain size classes.
DEFAULT_ANCHORS: list[tuple[float, float, float]] = [
    (1.0, 1.0, 1.0),  # S (0.5-2 CPU)
    (4.0, 1.5, 1.0),  # M (2-6 CPU)
    (10.0, 2.5, 1.0),  # L (6-14 CPU)
    (18.0, 3.0, 1.0),  # XL (14+ CPU)
]


def soft_bucket_weights(
    x: float, anchors: list[tuple[float, float, float]]
) -> list[float]:
    """Return per-anchor soft weight for a pod of size x."""
    return [gaussian_kernel(x, mu, sigma) for mu, sigma, _ in anchors]


def compute_soft_counts(
    node: Node, anchors: list[tuple[float, float, float]]
) -> list[float]:
    """Soft mass per anchor on a node."""
    n_buckets = len(anchors)
    counts = [0.0] * n_buckets
    for cpu in node.pod_cpu_list():
        for k, w in enumerate(soft_bucket_weights(cpu, anchors)):
            counts[k] += w
    return counts


# Scorer: soft-bucket imbalance


class SoftBucketScorer:
    """
    Score nodes by how loaded they are in the buckets relevant to the incoming pod.

    S_j = -SUM_k  w_k(x) · n^soft_{j,k}

    Prefers nodes with less soft mass in the incoming pod's size class.
    This naturally spreads pods of each size across nodes.
    """

    def __init__(
        self,
        anchors: list[tuple[float, float, float]] | None = None,
    ):
        self.anchors = anchors or DEFAULT_ANCHORS

    def score(self, node: Node, pod_cpu: float) -> float:
        current = compute_soft_counts(node, self.anchors)
        incoming = soft_bucket_weights(pod_cpu, self.anchors)
        s = 0.0
        for k, (mu, sigma, alpha) in enumerate(self.anchors):
            s -= alpha * incoming[k] * current[k]
        return s

    def score_all(self, nodes: list[Node], pod_cpu: float) -> list[float]:
        return [self.score(n, pod_cpu) for n in nodes]


# Pure density scorer D_j(x) = -SUM K(x, x_q)


class DensityScorer:
    """Simple kernel-density scorer."""

    def __init__(self, sigma: float = 2.0):
        self.sigma = sigma

    def score(self, node: Node, pod_cpu: float) -> float:
        return -sum(
            gaussian_kernel(pod_cpu, q, self.sigma) for q in node.pod_cpu_list()
        )

    def score_all(self, nodes: list[Node], pod_cpu: float) -> list[float]:
        return [self.score(n, pod_cpu) for n in nodes]


# Cluster simulation


@dataclass
class ScheduleEvent:
    """Record of one scheduling decision."""

    step: int
    pod: Pod
    scores: dict[str, float]  # node_name → score
    chosen_node: str


class Cluster:
    def __init__(self, nodes: list[Node], scorer: SoftBucketScorer | DensityScorer):
        self.nodes = {n.name: n for n in nodes}
        self.scorer = scorer
        self.history: list[ScheduleEvent] = []
        self._step = 0

    def _feasible_nodes(self, pod: Pod) -> list[Node]:
        return [n for n in self.nodes.values() if n.free_cpu >= pod.cpu_request]

    def schedule_pod(self, pod: Pod) -> ScheduleEvent | None:
        feasible = self._feasible_nodes(pod)
        if not feasible:
            return None
        scores = {n.name: self.scorer.score(n, pod.cpu_request) for n in feasible}
        best = max(scores, key=scores.get)

        # bind
        pod.node = best
        self.nodes[best].pods.append(pod)
        self._step += 1
        evt = ScheduleEvent(self._step, pod, scores, best)
        self.history.append(evt)
        return evt

    def deploy_service(self, svc: Service) -> list[ScheduleEvent]:
        events: list[ScheduleEvent] = []
        for i in range(svc.replicas):
            pod = Pod(
                name=f"{svc.name}-{i}",
                cpu_request=svc.cpu_request,
                service=svc.name,
            )
            evt = self.schedule_pod(pod)
            if evt:
                events.append(evt)
        return events


def make_nodes(count: int = 10, cpu: float = 88.0) -> list[Node]:
    return [Node(name=f"node-{i:02d}", allocatable_cpu=cpu) for i in range(count)]


def make_example_services() -> list[Service]:
    return [
        Service("nginx", 1.0, 23),
        Service("auth", 2.0, 11),
        Service("api", 3.0, 7),
        Service("search", 4.0, 8),
        Service("payment", 5.0, 3),
        Service("recommendation", 6.0, 4),
        Service("video", 10.0, 9),
        Service("inference", 14.0, 4),
        Service("pipeline", 20.0, 3),
        Service("analytics", 8.0, 3),
        Service("redis", 2.0, 7),
        Service("logging", 0.5, 12),
        Service("composer", 12.0, 7),
        Service("tracing", 6.0, 8),
        Service("postgres", 1.0, 30),
        Service("marketing", 17.0, 5),
    ]


def run_default_simulation(
    scorer_type: str = "soft_bucket",
    sigma: float = 2.0,
    seed: int = 42,
) -> Cluster:
    random.seed(seed)
    nodes = make_nodes()
    services = make_example_services()

    if scorer_type == "soft_bucket":
        scorer = SoftBucketScorer()
    else:
        scorer = DensityScorer(sigma=sigma)

    cluster = Cluster(nodes, scorer)

    # Shuffle deployment order
    random.shuffle(services)
    for svc in services:
        cluster.deploy_service(svc)

    return cluster
