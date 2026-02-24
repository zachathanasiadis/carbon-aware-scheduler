import os
import random
import logging
import requests
import kopf
import uuid
from kubernetes import client, config
import asyncio
import yaml

NODE_REGIONS = {
    "vm1": "DE",
    "vm2": "ERCOT",
    "vm3": "NL",
}

SCHEDULING_PERIOD = int(os.environ.get("SCHEDULING_PERIOD", 10))
CARBON_API_URL = str(os.environ.get("CARBON_API_URL"))
CARBON_AWARE = True

LOG_DIR = "/var/log/carbon-aware"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s %(message)s')

carbon_aware_handler = logging.FileHandler(os.path.join(LOG_DIR, "carbonaware_strategy.log"))
carbon_aware_handler.setFormatter(formatter)

normal_handler = logging.FileHandler(os.path.join(LOG_DIR, "normal_strategy.log"))
normal_handler.setFormatter(formatter)

config.load_incluster_config()
v1 = client.CoreV1Api()


def set_log_handler() -> None:
    if logger.handlers:
        logger.removeHandler(logger.handlers[0])
    logger.addHandler(carbon_aware_handler if CARBON_AWARE else normal_handler)


set_log_handler()


def select_best_node() -> tuple[str, float, dict[str, float]]:
    region_intensity = requests.get(CARBON_API_URL).json()
    node_intensity = {node: region_intensity[region] for node, region in NODE_REGIONS.items()}

    lowest_intensity = min(node_intensity.values())
    best_nodes = [node for node, intensity in node_intensity.items() if intensity == lowest_intensity]

    # Pick first node if there are more than one nodes with the same lowest average carbon intensity
    best_node = best_nodes[0]
    return best_node, lowest_intensity, node_intensity


def create_pod() -> None:
    node, carbon, carbon_all_nodes = select_best_node()
    exec_time = random.randint(20, 60)
    name = f"carbon-aware-{uuid.uuid4().hex[:8]}"

    with open("workload.yaml", "r") as f:
        pod_spec = yaml.safe_load(f)

    pod_spec["metadata"]["name"] = name
    for env_var in pod_spec["spec"]["containers"][0]["env"]:
        if env_var["name"] == "EXEC_TIME":
            env_var["value"] = str(exec_time)
            break

    if CARBON_AWARE:
        pod_spec["spec"]["affinity"] = {"nodeAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [
            {"weight": 100, "preference": {"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": [node]}]}}]}}

    v1.create_namespaced_pod("default", pod_spec)

    logger.info("Workload: %s | Recommended node: %s | Average carbon intensity of recommended node: %s | Average carbon intensity of all nodes: %s",
                name, node, carbon, carbon_all_nodes)


async def scheduler_loop() -> None:
    global CARBON_AWARE
    for i in range(600):
        is_carbon_aware = i < 300
        if is_carbon_aware != CARBON_AWARE:
            CARBON_AWARE = is_carbon_aware
            set_log_handler()
        try:
            await asyncio.to_thread(create_pod)
        except Exception as e:
            logger.info(f"Error creating pod: {e}")

        await asyncio.sleep(SCHEDULING_PERIOD)


@kopf.on.startup()
async def startup_handler(settings: kopf.OperatorSettings, *_, **__) -> None:
    asyncio.create_task(scheduler_loop())


@kopf.on.field("", "v1", "pods", field='spec.nodeName', labels={"app": "carbon-aware"})
def watch_pod_placement(old, new, name, body, *_, **__) -> None:
    if new:
        logger.info("Actual placement: Workload %s on node %s", name, new)
