import subprocess
import os
import time
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT_BIN_LOCAL = os.path.join(PROJECT_ROOT, "bin/upgrade-agent")
AGENT_BIN_REMOTE = "/tmp/upgrade-agent"


# ========================
# Build / deploy functions
# ========================
def make_build():
    """Build server and agent binaries"""
    subprocess.run(["make", "build"], cwd=PROJECT_ROOT, check=True)
    assert os.path.exists(AGENT_BIN_LOCAL), "upgrade-agent binary not built"


def verify_grpc_connectivity(server_addr):
    """Verify gNOI server is working properly"""
    result = subprocess.run(["grpcurl", "-plaintext", server_addr, "list"],
                            capture_output=True, text=True)
    print("gRPC Services:\n", result.stdout)
    assert result.returncode == 0, f"grpcurl failed: {result.stderr}"
    assert "gnoi.system.System" in result.stdout


# ========================
# Deploy server functions encapsulation
# ========================
def deploy_server_baremetal_local(port="50055"):
    script = os.path.join(PROJECT_ROOT, "docker/build_run_baremetal_testonly.sh")
    subprocess.Popen([script, "-a", f":{port}"])
    time.sleep(2)

def deploy_server_docker_remote(host, port="50055", user="admin"):
    script = os.path.join(PROJECT_ROOT, "docker/build_run_docker_testonly.sh")
    subprocess.run(
        [script, "-t", f"{user}@{host}", "-a", f":{port}"],
        check=True
    )
    time.sleep(2)

def stop_server_local():
    subprocess.run(["pkill", "-f", "sonic-gnmi-standalone"], check=False)

def stop_server_docker(host, user="admin"):
    subprocess.run(["ssh", f"{user}@{host}", "docker rm -f gnmi-standalone-testonly || true"],
                   check=False)


# ========================
# Agent operations encapsulation
# ========================
def run_agent_apply(server_addr, workflow_file, remote_host=None, user="admin"):
    if remote_host:
        cmd = f"{AGENT_BIN_REMOTE} apply {workflow_file} --server {server_addr}"
        subprocess.run(["ssh", f"{user}@{remote_host}", cmd],
                       check=True, capture_output=True, text=True)
    else:
        subprocess.run([AGENT_BIN_LOCAL, "apply", workflow_file, "--server", server_addr],
                       check=True)

def run_agent_download(server_addr, url, dest_file, md5, remote_host=None, user="admin"):
    if remote_host:
        cmd = f"{AGENT_BIN_REMOTE} download --server {server_addr} --url {url} --file {dest_file} --md5 {md5}"
        subprocess.run(["ssh", f"{user}@{remote_host}", cmd],
                       check=True, capture_output=True, text=True)
    else:
        subprocess.run([
            AGENT_BIN_LOCAL, "download", "--server", server_addr,
            "--url", url, "--file", dest_file, "--md5", md5
        ], check=True)


# ========================
# deploy agent to ptf
# ========================
def deploy_agent_to_remote(ptf_host, user="admin"):
    subprocess.run(["scp", AGENT_BIN_LOCAL, f"{user}@{ptf_host}:{AGENT_BIN_REMOTE}"], check=True)


# ========================
# Fixtures
# ========================
@pytest.fixture(scope="session")
def local_vm_scenario():
    port = "50055"
    make_build()
    deploy_server_baremetal_local(port)
    verify_grpc_connectivity(f"localhost:{port}")
    yield {
        "server_addr": f"localhost:{port}",
        "workflow_file": os.path.join(PROJECT_ROOT, "tests/workflows/workflow-local-vm.yaml")
    }
    stop_server_local()


@pytest.fixture(scope="session")
def kvm_scenario():
    kvm_host = "10.0.0.10"
    port = "50055"
    make_build()
    deploy_server_docker_remote(kvm_host, port=port)
    verify_grpc_connectivity(f"{kvm_host}:{port}")
    yield {
        "server_addr": f"{kvm_host}:{port}",
        "workflow_file": os.path.join(PROJECT_ROOT, "tests/workflows/workflow-kvm.yaml")
    }
    stop_server_docker(kvm_host)


@pytest.fixture(scope="session")
def physical_scenario():
    dut_host = "192.168.1.100"
    ptf_host = "192.168.1.200"
    port = "50055"
    make_build()
    deploy_server_docker_remote(dut_host, port=port)
    deploy_agent_to_remote(ptf_host)
    verify_grpc_connectivity(f"{dut_host}:{port}")
    yield {
        "server_addr": f"{dut_host}:{port}",
        "workflow_file": "/tmp/workflow-physical.yaml",
        "ptf_host": ptf_host
    }
    stop_server_docker(dut_host)
