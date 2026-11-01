"""The bench's CDB-S02, a conflicting change to replan, as one computer app: Copperfield Mail, Signal Quay Chat and
Daymark Calendar, the three windows of the bench's lighthouse-desk Electron app, and LibreOffice Calc on the task's
workbook, all on its workspace, ~/cdb-s02."""
from agentenv_protocol.computer import computer_app, linux

import bench_app as bench


@computer_app(supports=bench.SUPPORTS)
@linux(**bench.install(workspace="cdb-s02", first_window="Copperfield Mail", apt=bench.CALC_APT))
class CdbS02(bench.BenchTaskApp):
    pass
