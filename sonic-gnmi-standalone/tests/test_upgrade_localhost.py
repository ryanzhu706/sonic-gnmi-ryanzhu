import pytest
from conftest import run_agent_apply, run_agent_download, verify_grpc_connectivity


@pytest.mark.usefixtures("local_vm_scenario")
class TestLocalUpgrade:
    def test_local_connectivity(self, local_vm_scenario):
        """
        Verify that the gNOI server is reachable in local VM scenario
        """
        verify_grpc_connectivity(local_vm_scenario["server_addr"])

    def test_local_download(self, local_vm_scenario):
        """
        Verify that the gNOI server can download files in local VM scenario
        """
        test_url = "http://httpbin.org/robots.txt"
        dest_file = "/tmp/sonic-test.bin"
        md5_checksum = "e2a3e68d23ce348b8d8cf1e1f1b6e36c"  # robots.txt MD5

        run_agent_download(
            server_addr=local_vm_scenario["server_addr"],
            url=test_url,
            dest_file=dest_file,
            md5=md5_checksum
        )

    def test_local_apply(self, local_vm_scenario):
        """
        Verify that the gNOI server can execute apply workflow in local VM scenario
        """
        run_agent_apply(
            server_addr=local_vm_scenario["server_addr"],
            workflow_file=local_vm_scenario["workflow_file"]
        )
