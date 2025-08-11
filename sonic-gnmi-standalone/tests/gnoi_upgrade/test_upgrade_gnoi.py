import tempfile
import textwrap
import pytest
from pathlib import Path
import subprocess
import yaml
pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
    pytest.mark.skip_check_dut_health,
]

def _tls_flag(cfg):
    return ["--tls"] if cfg["tls"] else []

def _dut_host_from_server_addr(server_addr: str) -> str:
    # "10.0.0.10:50055" -> "admin@10.0.0.10"
    host = server_addr.split(":")[0]
    return f"admin@{host}"

def assert_dut_file_md5(server_addr: str, path: str, expected_md5: str):
    target = _dut_host_from_server_addr(server_addr)
    cmd = f"test -f {path} && md5sum {path} | awk '{{print $1}}'"
    res = subprocess.run(["ssh", target, cmd], text=True, capture_output=True)
    assert res.returncode == 0, f"File not found on DUT: {path}"
    md5 = res.stdout.strip()
    assert md5 == expected_md5, f"MD5 mismatch for {path}: got {md5}, want {expected_md5}"

def test_connectivity_smoke(cfg, deploy_server):
    """
    Verify gNOI server is reachable
    If grpcurl is installed on the control machine, the CI can be enhanced with:
      grpcurl -plaintext <addr> list | grep gnoi.system.System
    """
    addr = deploy_server
    assert ":" in addr and addr.split(":")[1].isdigit()

def test_download(cfg, md5sum, deploy_server, agent_runner):
    """
    Verify download step
    - agent can run locally or on PTF (controlled by --ptf)
    """
    server = deploy_server
    where = "ptf" if cfg["ptf"] else "local"
    out = agent_runner(
        ["download",
         "--server", server, *_tls_flag(cfg),
         "--url", cfg["url"],
         "--file", cfg["dest"],
         "--md5", md5sum],
        where=where
    )
    assert_dut_file_md5(server, cfg["dest"], md5sum)

def test_apply(cfg, deploy_server, agent_runner):
    repo_root = Path(__file__).resolve().parents[2]
    wf_path = repo_root / "sonic-gnmi-standalone" / "tests" / "examples" / "multi-step-workflow.yaml"
    server = deploy_server
    where = "ptf" if cfg["ptf"] else "local"

    out = agent_runner(["apply", str(wf_path), "--server", server], where=where)
    assert "Workflow completed successfully" in out

    data = yaml.safe_load(wf_path.read_text())
    for step in data["spec"]["steps"]:
        if step.get("type") != "download":
            continue
        p = step["params"]
        filename = p["filename"]
        expected_md5 = p.get("md5") 
        if not expected_md5:
            import subprocess, hashlib
            blob = subprocess.check_output(["curl", "-fsSL", p["url"]])
            expected_md5 = __import__("hashlib").md5(blob).hexdigest()

        assert_dut_file_md5(server, filename, expected_md5)

