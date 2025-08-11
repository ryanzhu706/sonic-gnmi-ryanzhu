import os
import subprocess
import time
import tempfile
import hashlib
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]  # sonic-gnmi/
STANDALONE = REPO_ROOT / "sonic-gnmi-standalone"
AGENT_BIN = STANDALONE / "bin" / "upgrade-agent"
BAREMETAL = STANDALONE / "docker" / "build_run_baremetal_testonly.sh"
DOCKER_DEPLOY = STANDALONE / "docker" / "build_run_docker_testonly.sh"

def _run(cmd, **kw):
    return subprocess.run(cmd, text=True, check=True, capture_output=True, **kw)

def pytest_addoption(parser):
    g = parser.getgroup("gNOI e2e")
    g.addoption("--dut", help="DUT mgmt IP or 'user@host' for SSH (docker deploy needs 'admin@IP')", default=None)
    g.addoption("--ptf", help="PTF host for running agent (if omitted, run agent locally)", default=None)
    g.addoption("--port", help="gNOI server port", default="50055")
    g.addoption("--url",  help="image/file URL to download", default="http://httpbin.org/robots.txt")
    g.addoption("--dest", help="destination path on DUT filesystem", default="/tmp/sonic-test.bin")
    g.addoption("--use-baremetal-local", action="store_true", help="start server locally via baremetal script (dev/debug)")
    g.addoption("--tls", action="store_true", help="use TLS when agent connects (server must be started with TLS)")
    g.addoption("--scenario", choices=["kvm-pr-gnmi","kvm-pr-buildimage","physical-nightly","dev-local"], default="kvm-pr-gnmi")

@pytest.fixture(scope="session")
def cfg(pytestconfig):
    return {
        "dut": pytestconfig.getoption("--dut"),
        "ptf": pytestconfig.getoption("--ptf"),
        "port": pytestconfig.getoption("--port"),
        "url": pytestconfig.getoption("--url"),
        "dest": pytestconfig.getoption("--dest"),
        "use_baremetal_local": pytestconfig.getoption("--use-baremetal-local"),
        "tls": pytestconfig.getoption("--tls"),
        "scenario": pytestconfig.getoption("--scenario"),
    }

@pytest.fixture(scope="session")
def build_bins():
    _run(["make", "build"], cwd=STANDALONE)
    assert AGENT_BIN.exists(), f"agent missing: {AGENT_BIN}"
    return {"agent": str(AGENT_BIN)}

@pytest.fixture(scope="session")
def deploy_server(cfg, build_bins):
    """
    Deploy gNOI server, yield its address (host:port)
      - Dev/Local: local baremetal server (requires --use-baremetal-local)
      - KVM-PR-gnmi: docker deploy to KVM PR testbed (requires --dut=admin@<ip>)
      - KVM-PR-buildimage: docker deploy to KVM PR build image (requires --dut=admin@<ip>)
      - Nightly physical: docker deploy to nightly physical testbed (requires --dut=admin@<ip>)
    """
    port = cfg["port"]
    if cfg["use_baremetal_local"]:
        # Local baremetal server
        _ = subprocess.Popen([str(BAREMETAL), "-a", f":{port}"])
        time.sleep(2)
        addr = f"localhost:{port}"
        yield addr
        subprocess.run(["pkill", "-f", "sonic-gnmi-standalone"], check=False)
        return

    # Docker deploy
    assert cfg["dut"], "--dut is required for docker deploy"
    target = cfg["dut"] if "@" in cfg["dut"] else f"admin@{cfg['dut']}"
    _run([str(DOCKER_DEPLOY), "-t", target, "-a", f":{port}"])
    addr = f"{target.split('@')[-1]}:{port}"
    time.sleep(2)
    yield addr
    # Cleanup docker container
    host = target.split("@")[-1]
    subprocess.run(["ssh", target, "docker rm -f gnmi-standalone-testonly || true"], check=False)

@pytest.fixture(scope="session")
def md5sum(cfg):
    data = _run(["curl", "-fsSL", cfg["url"]]).stdout.encode()
    return hashlib.md5(data).hexdigest()

@pytest.fixture(scope="session")
def agent_runner(cfg, build_bins):
    """
    Returns a function to run the upgrade-agent binary, either locally or on PTF.
    Usage:
        run_agent = agent_runner(cfg, build_bins)
        output = run_agent(["download", "--server", "   addr:port", "--url", "http://...", "--dest", "/tmp/file"])
    """
    agent_local = build_bins["agent"]

    def _ensure_ptf_has_agent(ptf):
        subprocess.run(["scp", agent_local, f"{ptf}:/tmp/upgrade-agent"], check=True)
        subprocess.run(["ssh", ptf, "chmod +x /tmp/upgrade-agent"], check=True)

    def _run_agent(args: list[str], where="local"):
        if where == "local":
            return _run([agent_local] + args).stdout
        assert cfg["ptf"], "--ptf must be provided to run agent on PTF"
        ptf = cfg["ptf"] if "@" in cfg["ptf"] else f"root@{cfg['ptf']}"
        _ensure_ptf_has_agent(ptf)
        cmd = " ".join(["/tmp/upgrade-agent"] + args)
        out = _run(["ssh", ptf, cmd]).stdout
        return out

    return _run_agent
