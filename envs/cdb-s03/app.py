"""The bench's CDB-S03, invoice reconciliation, as one computer app: the bench's Ledger Lantern Mail Electron app,
LibreOffice Calc on the task's workbook and GnuCash on its book, all on its workspace, ~/cdb-s03."""
from agentenv_protocol.computer import computer_app, install, linux

import bench_app as bench


@computer_app(supports=bench.SUPPORTS)
@linux(**bench.install(workspace="cdb-s03", first_window="Ledger Lantern Mail",
                       apt=[*bench.CALC_APT, *bench.GNUCASH_APT]))
@install("macos", **bench.macos(workspace="cdb-s03", calc=True, gnucash=True))
class CdbS03(bench.BenchTaskApp):
    pass
