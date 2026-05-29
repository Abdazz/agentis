import time
import docker
import structlog
from dataclasses import dataclass, field
from app.config import settings

log = structlog.get_logger()


@dataclass
class SandboxSession:
    task_id: str
    container_id: str
    endpoint: str  # http://{ip}:9999
    created_at: float = field(default_factory=time.time)


class SandboxManager:
    """
    Manages sandbox container lifecycle.
    Dev: plain Docker with security options.
    Prod (K3s): replaced by Kata Container RuntimeClass.
    """

    def __init__(self):
        self._client = docker.from_env()
        self._sessions: dict[str, SandboxSession] = {}

    def _start_container(self, task_id: str) -> SandboxSession:
        import docker.types

        container = self._client.containers.run(
            image=settings.sandbox_image,
            detach=True,
            network=settings.sandbox_network,
            name=f"agentis-sandbox-{task_id}",
            # Security hardening (spec §7.3)
            security_opt=["no-new-privileges"],
            read_only=True,
            cap_drop=["ALL"],
            # /workspace must be writable — use tmpfs (ephemeral, destroyed with container)
            mounts=[
                docker.types.Mount(
                    target="/workspace",
                    source=None,
                    type="tmpfs",
                    tmpfs_size="5368709120",  # 5 GB limit
                )
            ],
            environment={
                "http_proxy": settings.egress_proxy_url,
                "https_proxy": settings.egress_proxy_url,
                "HTTP_PROXY": settings.egress_proxy_url,
                "HTTPS_PROXY": settings.egress_proxy_url,
            } if settings.egress_proxy_url else None,
            mem_limit="2g",
            nano_cpus=2 * 10**9,
            remove=False,
            labels={"agentis.task_id": task_id, "agentis.managed": "true"},
        )

        container.reload()
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        network_info = networks.get(settings.sandbox_network, {})
        ip = network_info.get("IPAddress", "")

        if not ip:
            for net_data in networks.values():
                if net_data.get("IPAddress"):
                    ip = net_data["IPAddress"]
                    break

        endpoint = f"http://{ip}:{settings.sandbox_rpc_port}"
        session = SandboxSession(
            task_id=task_id,
            container_id=container.id,
            endpoint=endpoint,
        )
        self._sessions[task_id] = session
        log.info("sandbox_created", task_id=task_id, container_id=container.id[:12], endpoint=endpoint)
        return session

    def get_session(self, task_id: str) -> SandboxSession | None:
        return self._sessions.get(task_id)

    def destroy_session(self, task_id: str) -> None:
        session = self._sessions.pop(task_id, None)
        if session is None:
            return
        try:
            container = self._client.containers.get(session.container_id)
            container.stop(timeout=10)
            container.remove()
            log.info("sandbox_destroyed", task_id=task_id)
        except Exception as e:
            log.error("sandbox_destroy_failed", task_id=task_id, error=str(e))

    async def create_session(self, task_id: str) -> SandboxSession:
        """
        Create a new sandbox session. Waits for the tool server to be ready (up to 15s).
        """
        import asyncio
        import httpx

        session = self._start_container(task_id)

        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{session.endpoint}/health")
                    if resp.status_code == 200:
                        log.info("sandbox_ready", task_id=task_id)
                        return session
            except Exception:
                pass
            await asyncio.sleep(0.5)

        self.destroy_session(task_id)
        raise RuntimeError(f"Sandbox for task {task_id} did not become ready within 15 seconds")


# Module-level singleton
sandbox_manager = SandboxManager()
