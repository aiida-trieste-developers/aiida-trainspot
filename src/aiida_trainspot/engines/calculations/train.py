"""Base CalcJob shared by all training engines (MACE, METATRAIN, ...)."""

from aiida.engine import CalcJob
from aiida.orm import Bool, Code, FolderData, List

from aiida_trainspot.data.pesdata import PESData


class TrainCalculation(CalcJob):
    """Common CalcJob to launch the training of a machine-learning potential.

    Subclasses add their own engine-specific config input (e.g. ``mace_config``), model
    output(s), extra exit codes, and must set ``metadata.options.parser_name`` to their own
    parser entry point.
    """

    @classmethod
    def define(cls, spec):
        """Specify the inputs, outputs and exit codes shared by every training engine."""
        super().define(spec)

        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }

        spec.input(
            "training_set",
            valid_type=PESData,
            help="Training dataset list",
            required=False,
        )
        spec.input(
            "validation_set",
            valid_type=PESData,
            help="Validation dataset list",
            required=False,
        )
        spec.input(
            "test_set",
            valid_type=PESData,
            help="Test dataset list",
            required=False,
        )
        spec.input(
            "checkpoints",
            valid_type=FolderData,
            help="Checkpoints file",
            required=False,
        )
        spec.input("postprocess_code", valid_type=Code, help="Postprocess code", required=False)
        spec.input(
            "restart",
            valid_type=Bool,
            help="Restart from a previous calculation",
            required=False,
            default=lambda: Bool(False),
        )
        spec.input(
            "checkpoints_restart",
            valid_type=FolderData,
            help="Checkpoints file",
            required=False,
        )
        spec.inputs.validator = cls.validate_inputs

        spec.output(
            "checkpoints",
            valid_type=FolderData,
            help="Checkpoints file",
        )
        spec.output(
            "RMSE",
            valid_type=List,
            help="List of the checkpoints result table",
        )

        spec.exit_code(
            300,
            "ERROR_MISSING_OUTPUT_FILES",
            message="Calculation did not produce all expected output files.",
        )
        spec.exit_code(
            400,
            "ERROR_OUT_OF_WALLTIME",
            message="The calculation stopped prematurely because it ran out of walltime.",
        )

    @staticmethod
    def validate_inputs(inputs, _):
        """Validate the top-level inputs shared by every training engine.

        This base implementation has no shared constraints of its own; it exists so subclasses
        can uniformly call ``super().validate_inputs(...)`` before appending their own checks
        (e.g. ``parent_folder``, or engine-specific inputs like MACE's finetuning protocol).
        """
        return None
