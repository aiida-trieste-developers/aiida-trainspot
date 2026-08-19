"""Base WorkChain shared by all training engines (MACE, METATRAIN, ...)."""

import os

from aiida.common.extendeddicts import AttributeDict
from aiida.engine import BaseRestartWorkChain, ProcessHandlerReport, process_handler, while_
from aiida.orm import FolderData


class TrainWorkChain(BaseRestartWorkChain):
    """Common WorkChain to launch the training of a machine-learning potential.

    Subclasses only need to set ``_process_class`` to the ``CalcJob`` that runs the
    training engine. The engine's exit codes must define an ``ERROR_OUT_OF_WALLTIME``
    label for the restart-on-walltime handler to trigger.
    """

    _process_class = None

    @classmethod
    def define(cls, spec):
        """Specify inputs and outputs."""
        super().define(spec)

        spec.expose_inputs(cls._process_class, namespace="train", namespace_options={"validator": None})
        spec.expose_outputs(cls._process_class)
        spec.input_namespace(
            "checkpoints",
            valid_type=FolderData,
            required=False,
            help="Checkpoints file",
        )
        spec.outline(
            cls.setup,
            while_(cls.should_run_process)(
                cls.run_process,
                cls.inspect_process,
            ),
            cls.results,
        )

    def report_error_handled(self, calculation, action):
        """Report an action taken for a calculation that has failed.

        This should be called in a registered error handler if its condition
        is met and an action was taken.
        :param calculation: the failed calculation node
        :param action: a string message with the action taken
        """
        self.report(
            f"{calculation.process_label}<{calculation.pk}> failed "
            f"with exit status {calculation.exit_status}: {calculation.exit_message}"
        )
        self.report(f"Action taken: {action}")

    def set_restart(self, calculation):
        """Set the parameters to run the restart calculation.

        Depending on the type of restart several variables of the input parameters
        will be changed to try to ensure that the calculation can resume from
        the last stored structure

        :param calculation: node from the previous calculation
        """
        files_retrieved = calculation.outputs.retrieved.list_object_names()
        for file in files_retrieved:
            output_filename = file
            if "checkpoint" in output_filename:
                folder_data = FolderData()
                folder_contents = calculation.outputs.retrieved.list_object_names(output_filename)
                for file_in_folder in folder_contents:
                    file_path = os.path.join(output_filename, file_in_folder)
                    with calculation.outputs.retrieved.open(file_path, "rb") as handle:
                        folder_data.put_object_from_filelike(handle, file_in_folder)
                self.ctx.inputs.checkpoints_restart = folder_data

        if "checkpoints" in calculation.outputs:
            self.ctx.inputs.checkpoints_restart = calculation.outputs.checkpoints

    def setup(self):
        """Call the ``setup`` of the ``BaseRestartWorkChain`` and create the inputs dictionary in ``self.ctx.inputs``.

        This ``self.ctx.inputs`` dictionary will be used by the ``BaseRestartWorkChain`` to submit the calculations
        in the internal loop.
        """
        super().setup()
        self.ctx.inputs = AttributeDict(self.exposed_inputs(self._process_class, namespace="train"))

    def restart_from(self, calculation):
        """Set the inputs of the next calculation so that it resumes from ``calculation``.

        Default implementation copies the checkpoint files out of the previous calculation's
        retrieved output (see :meth:`set_restart`). Engines whose ``CalcJob`` can resume in place
        from a remote folder (avoiding a costly re-upload of datasets/checkpoints already present
        on the remote computer) should override this method, e.g. by setting
        ``self.ctx.inputs.parent_folder = calculation.outputs.remote_folder``.

        :param calculation: node from the previous calculation
        """
        self.set_restart(calculation=calculation)

    @process_handler(priority=610)
    def handle_out_of_walltime(self, calculation):
        """Handle calculations where the walltime was reached.

        The handler will try to find a configuration to restart from with the
        following priority

        Use a stored restart file in the repository from the previous calculation.
        """
        if calculation.exit_status != self._process_class.exit_codes.ERROR_OUT_OF_WALLTIME.status:  # pylint: disable=no-member
            return None

        self.report("Walltime reached attempting restart")

        if "retrieved" in calculation.outputs:
            self.restart_from(calculation)
            self.report_error_handled(
                calculation,
                "restarting from the stored checkpoints",
            )

        return ProcessHandlerReport(True)
