"""`LammpsBaseWorkChain` with an extra blind-retry handler for exploration MD runs.

`LammpsBaseWorkChain`'s own `handle_unrecoverable_failure` (priority 600) treats any exit code below
400 as immediately unrecoverable and gives up without a single retry attempt. During active-learning
exploration, though, several of those are plausibly transient/numerically stochastic - e.g. a LAMMPS
run that blows up depending on the random velocity seed drawn for a given committee member/structure -
and simply resubmitting the exact same inputs may well succeed next time. This subclass adds one extra
handler, at a priority above 600 so it intercepts before the base class gives up, that does exactly
that: no smarter fix, just try again, bounded by the inherited `max_iterations`.

Deliberately NOT included: `ERROR_SCHEDULER_OUT_OF_MEMORY` (a resubmission with the same resources
will just run out of memory again) and `ERROR_SCHEDULER_INVALID_ACCOUNT` (a configuration error, not a
transient one) - those still fall straight through to the base class's immediate give-up.
"""

from aiida.engine import ProcessHandlerReport, process_handler
from aiida_lammps.calculations.base import LammpsBaseCalculation
from aiida_lammps.workflows.base import LammpsBaseWorkChain

_TRANSIENT_EXIT_CODES = [
    LammpsBaseCalculation.exit_codes.ERROR_SCHEDULER_NODE_FAILURE,
    LammpsBaseCalculation.exit_codes.ERROR_NO_RETRIEVED_FOLDER,
    LammpsBaseCalculation.exit_codes.ERROR_STDOUT_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_STDERR_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_OUTPUT_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_LOG_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_FINAL_VARIABLE_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_TRAJECTORY_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_RESTART_FILE_MISSING,
    LammpsBaseCalculation.exit_codes.ERROR_PARSER_DETECTED_LAMMPS_RUN_ERROR,
]


class LammpsMdWorkChain(LammpsBaseWorkChain):
    """`LammpsBaseWorkChain`, plus a blind retry for plausibly transient/stochastic LAMMPS failures."""

    @process_handler(priority=605, exit_codes=_TRANSIENT_EXIT_CODES)
    def handle_transient_failure(self, calculation):
        # The velocity seed isn't fixed anywhere in `parameters` (see generate_config.py), so
        # aiida-lammps' own fallback (np.random.randint in generate_velocity_string) draws a new one
        # on every prepare_for_submission -- these "identical" inputs render a different .in file.
        """Blindly resubmit identical inputs: the failure may be numerically stochastic (e.g. seed-dependent)."""
        self.report_error_handled(calculation, "plausibly transient failure, resubmitting identical inputs")
        return ProcessHandlerReport(True)
