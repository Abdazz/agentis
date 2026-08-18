import asyncio
import time
import uuid
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


@dataclass
class WarmContainer:
    """A pre-started, health-checked container not yet assigned to a task
    (BR-SAND-10/11)."""
    container_id: str
    endpoint: str
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > settings.sandbox_warm_ttl_seconds


class SandboxManager:
    """
    Manages sandbox container lifecycle.
    Dev: plain Docker with security options.
    Prod (K3s): replaced by Kata Container RuntimeClass.
    """

    def __init__(self):
        self._client = None  # lazily initialized on first use (API process has no Docker socket)
        self._sessions: dict[str, SandboxSession] = {}
        self._warm_pool: list[WarmContainer] = []
        self._warm_pool_lock = asyncio.Lock()

    @property
    def _docker(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _run_container(self, name: str, labels: dict) -> docker.models.containers.Container:
        import docker.types

        container = self._docker.containers.run(
            image=settings.sandbox_image,
            detach=True,
            network=settings.sandbox_network,
            name=name,
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
            labels=labels,
        )

        container.reload()
        return container

    def _endpoint_for(self, container) -> str:
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        network_info = networks.get(settings.sandbox_network, {})
        ip = network_info.get("IPAddress", "")

        if not ip:
            for net_data in networks.values():
                if net_data.get("IPAddress"):
                    ip = net_data["IPAddress"]
                    break

        return f"http://{ip}:{settings.sandbox_rpc_port}"

    def _start_container(self, task_id: str) -> SandboxSession:
        container = self._run_container(
            name=f"agentis-sandbox-{task_id}",
            labels={"agentis.task_id": task_id, "agentis.managed": "true"},
        )
        endpoint = self._endpoint_for(container)
        session = SandboxSession(task_id=task_id, container_id=container.id, endpoint=endpoint)
        self._sessions[task_id] = session
        log.info("sandbox_created", task_id=task_id, container_id=container.id[:12], endpoint=endpoint)
        return session

    def _start_warm_container(self) -> WarmContainer:
        pool_id = uuid.uuid4().hex[:12]
        container = self._run_container(
            name=f"agentis-sandbox-warm-{pool_id}",
            labels={"agentis.managed": "true", "agentis.warm": "true"},
        )
        endpoint = self._endpoint_for(container)
        return WarmContainer(container_id=container.id, endpoint=endpoint)

    def _destroy_container(self, container_id: str, task_id: str | None = None) -> None:
        try:
            container = self._docker.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
            log.info("sandbox_destroyed", task_id=task_id, container_id=container_id[:12])
        except Exception as e:
            log.error("sandbox_destroy_failed", task_id=task_id,
                      container_id=container_id[:12], error=str(e))

    async def _health_check(self, endpoint: str, timeout_s: float = 15.0) -> bool:
        import httpx

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{endpoint}/health")
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _reap_expired_warm_containers(self) -> None:
        """BR-SAND-13: warm containers unused for 5 minutes are destroyed."""
        async with self._warm_pool_lock:
            live, expired = [], []
            for wc in self._warm_pool:
                (expired if wc.is_expired() else live).append(wc)
            self._warm_pool = live

        loop = asyncio.get_event_loop()
        for wc in expired:
            log.info("warm_sandbox_expired", container_id=wc.container_id[:12])
            await loop.run_in_executor(None, self._destroy_container, wc.container_id)

    async def replenish_warm_pool(self) -> None:
        """Top up the warm pool to sandbox_warm_pool_size (BR-SAND-10/12).
        Safe to call concurrently/repeatedly — failures are logged and
        skipped rather than raised, since this always runs as a
        best-effort background task."""
        await self._reap_expired_warm_containers()

        async with self._warm_pool_lock:
            missing = max(0, settings.sandbox_warm_pool_size - len(self._warm_pool))

        loop = asyncio.get_event_loop()
        for _ in range(missing):
            try:
                wc = await loop.run_in_executor(None, self._start_warm_container)
            except Exception as e:
                log.error("warm_sandbox_start_failed", error=str(e))
                continue
            if not await self._health_check(wc.endpoint):
                log.error("warm_sandbox_unhealthy", container_id=wc.container_id[:12])
                await loop.run_in_executor(None, self._destroy_container, wc.container_id)
                continue
            async with self._warm_pool_lock:
                self._warm_pool.append(wc)
            log.info("warm_sandbox_ready", container_id=wc.container_id[:12])

    async def _take_warm_container(self) -> WarmContainer | None:
        await self._reap_expired_warm_containers()
        async with self._warm_pool_lock:
            if not self._warm_pool:
                return None
            return self._warm_pool.pop(0)

    def get_session(self, task_id: str) -> SandboxSession | None:
        return self._sessions.get(task_id)

    def destroy_session(self, task_id: str) -> None:
        session = self._sessions.pop(task_id, None)
        if session is None:
            return
        self._destroy_container(session.container_id, task_id=task_id)

    async def create_session(self, task_id: str) -> SandboxSession:
        """
        Create a new sandbox session. Assigns a warm container immediately
        if one is available (BR-SAND-11), replenishing the pool afterward
        in the background (BR-SAND-12). Falls back to a cold container,
        waiting for the tool server to be ready (up to 15s), if the pool
        is empty (BR-SAND-14).
        """
        warm = await self._take_warm_container()
        if warm is not None:
            session = SandboxSession(
                task_id=task_id, container_id=warm.container_id, endpoint=warm.endpoint,
            )
            self._sessions[task_id] = session
            log.info("sandbox_assigned_from_warm_pool", task_id=task_id,
                     container_id=warm.container_id[:12], endpoint=warm.endpoint)
            asyncio.create_task(self.replenish_warm_pool())
            return session

        session = self._start_container(task_id)
        if await self._health_check(session.endpoint):
            log.info("sandbox_ready", task_id=task_id)
            return session

        self.destroy_session(task_id)
        raise RuntimeError(f"Sandbox for task {task_id} did not become ready within 15 seconds")


# Module-level singleton
sandbox_manager = SandboxManager()
