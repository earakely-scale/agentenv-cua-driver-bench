"""The bench's CDB-S04, linked support diagnosis, as one computer app: the bench's Rillwatch Cases and Margin Lantern
Manual Electron apps and its Morrowglass Archive service on Node, all on its workspace, ~/cdb-s04. The task's browser
on that service joins once the computer has one."""
from agentenv_protocol.computer import computer_app, linux

import bench_app as bench


@computer_app(supports=bench.SUPPORTS)
@linux(**bench.install(workspace="cdb-s04", first_window="Rillwatch Cases", node=True))
class CdbS04(bench.BenchTaskApp):
    pass
