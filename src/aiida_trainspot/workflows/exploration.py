"""Workchain to perform exploration MD simulations with LAMMPS."""

import os
import tempfile

from pathlib import Path

from aiida.engine import WorkChain, append_, calcfunction
from aiida.orm import Bool, Dict, Float, List, SinglefileData, Str, StructureData
from aiida_lammps.data.potential import LammpsPotentialData
from aiida_quantumespresso.workflows.protocols.utils import recursive_merge

from ..data.pesdata import PESData
from ..utils import potential_engines as pe
from ..utils.lammps_pair_coeffs import get_dftd2_pair_coeffs
from ..utils.tools import enlarge_vacuum
from .lammps_md import LammpsMdWorkChain as LammpsWorkChain


@calcfunction
def LammpsFrameExtraction(
    sampling_time,
    saving_frequency,
    thermalization_time=lambda: Float(0),
    check_vacuum=lambda: Bool(False),
    min_vacuum=lambda: Float(5.0),  # noqa B008
    target_vacuum=lambda: Float(15.0),  # noqa B008
    **trajectories,
):
    """Extract frames from trajectory."""
    extracted_frames = []
    for _, trajectory in trajectories.items():
        try:
            calculation = next(
                calc.node
                for calc in trajectory.base.links.get_incoming().all()
                if calc.node.process_type == "aiida.calculations:lammps.base"
            )
        except StopIteration:
            # in principle should not happen, but in case skip this trajectory
            continue
        params = calculation.inputs.parameters
        input_structure = calculation.inputs.structure

        timestep = params["control"]["timestep"]
        integration_style = params["md"]["integration"]["style"].lower()
        temperature = params["md"]["integration"]["constraints"]["temp"]

        i = int(thermalization_time.value / timestep / saving_frequency.value) if thermalization_time.value > 0 else 1

        while i < trajectory.number_steps:
            frame = trajectory.get_step_structure(i).get_ase()
            if check_vacuum:
                frame = enlarge_vacuum(
                    frame,
                    min_vacuum=min_vacuum.value,
                    target_vacuum=target_vacuum.value,
                )

            extracted_frames.append(
                {
                    "cell": frame.get_cell(),
                    "symbols": frame.get_chemical_symbols(),
                    "positions": frame.get_positions(),
                    "input_structure_uuid": str(input_structure.uuid),
                    "gen_method": "LAMMPS",
                    "pbc": frame.get_pbc(),
                }
            )
            extracted_frames[-1]["style"] = integration_style
            extracted_frames[-1]["temp"] = temperature
            extracted_frames[-1]["timestep"] = timestep
            extracted_frames[-1]["id_lammps"] = calculation.uuid

            i = i + int(sampling_time.value / timestep / saving_frequency.value)

    pes_extracted_frames = PESData(extracted_frames)
    return {"explored_dataset": pes_extracted_frames}


def generate_potential(potential, pair_style) -> LammpsPotentialData:
    """Generate the potential to be used in the calculation.

    Takes a potential form OpenKIM and stores it as a LammpsPotentialData object.

    :return: potential to do the calculation
    :rtype: LammpsPotentialData
    """
    potential_parameters = {
        "species": [],
        "atom_style": "atomic",
        "units": "metal",
        "extra_tags": {},
    }

    # Assuming you have a trained MACE model
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        with potential.open(mode="rb") as potential_handle:
            potential_content = potential_handle.read()
        tmp_file.write(potential_content)
        tmp_file_path = tmp_file.name

    potential = LammpsPotentialData.get_or_create(
        source=Path(tmp_file_path),
        pair_style=pair_style,
        **potential_parameters,
    )

    os.remove(tmp_file_path)

    return potential


###################################################################
##                       DEFAULT VALUES                          ##
###################################################################

DEFAULT_potential_pair_style = Str("mace no_domain_decomposition")
DEFAULT_sampling_time = Float(1.0)
DEFAULT_thermalization_time = Float(0.0)
DEFAULT_check_vacuum = Bool(True)
DEFAULT_min_vacuum = Float(5.0)
DEFAULT_target_vacuum = Float(15.0)
DEFAULT_settings = Dict(
    {
        "store_restart": True,
    },
)
DEFAULT_parameters = Dict(
    {
        "structure": {
            "atom_style": "atomic",
            "atom_modify": "map yes",
            "dimension": "3",
            "boundary": "p p p",
        },
        "control": {
            "timestep": 0.001,
            "newton": "on",
            "units": "metal",
        },
        "thermo": {
            "printing_rate": 100,
            "thermo_printing": {
                "step": True,
                "time": True,
                "pe": True,
                "ke": True,
                "etotal": True,
                "press": True,
                "pxx": True,
                "pyy": True,
                "pzz": True,
                "temp": True,
            },
        },
        "restart": {
            "print_final": True,
        },
        "md": {},
        "dump": {},
    }
)
###################################################################


class ExplorationWorkChain(WorkChain):
    """A workchain to loop over structures and submit LammpsWorkChain with retries."""

    @classmethod
    def define(cls, spec):
        """Input and output specification."""
        super().define(spec)
        spec.input("params_list", valid_type=List, help="List of parameters for md")
        spec.input("parameters", valid_type=Dict, help="Global parameters for lammps")
        spec.input(
            "potential_lammps",
            valid_type=SinglefileData,
            required=False,
            help="One of the potential for MD",
        )
        spec.input(
            "potential_pair_style",
            valid_type=Str,
            default=lambda: DEFAULT_potential_pair_style,
            required=False,
            help=f"General potential pair style. Default: {DEFAULT_potential_pair_style}",
        )
        spec.input(
            "sampling_time",
            valid_type=Float,
            default=lambda: DEFAULT_sampling_time,
            required=False,
            help="Correlation time for frame extraction, and the LAMMPS dump rate for the MD runs",
        )
        spec.input(
            "thermalization_time",
            valid_type=Float,
            default=lambda: DEFAULT_thermalization_time,
            required=False,
            help="Thermalization time; frames within it are not considered for extraction",
        )
        spec.input(
            "protocol",
            valid_type=Str,
            help="Protocol for the calculation",
            required=False,
        )
        spec.input(
            "lammps_input_structures",
            valid_type=PESData,
            help="Input structures for lammps",
        )
        spec.input(
            "check_vacuum",
            valid_type=Bool,
            default=lambda: DEFAULT_check_vacuum,
            required=False,
            help="Check vacuum in the extracted frames",
        )
        spec.input(
            "vacuum.min_vacuum",
            valid_type=Float,
            required=False,
            help=f"Minimum vacuum size to consider for enlarging. Default: {DEFAULT_min_vacuum}",
        )
        spec.input(
            "vacuum.target_vacuum",
            valid_type=Float,
            required=False,
            help=f"Target vacuum size after enlarging. Default: {DEFAULT_target_vacuum}",
        )

        spec.expose_inputs(
            LammpsWorkChain,
            namespace="md",
            exclude=("lammps.structure", "lammps.potential", "lammps.parameters"),
            namespace_options={"validator": None},
        )

        spec.output(
            "explored_dataset",
            valid_type=PESData,
            help="Structures sampled from the successful MD trajectories.",
        )

        spec.exit_code(
            300,
            "ERROR_ALL_TRAJECTORIES_FAILED",
            message="All LAMMPS MD trajectories failed.",
        )
        spec.exit_code(
            301,
            "EMPTY_EXPLORATION_DATASET",
            message="No frames were extracted from the successful MD trajectories.",
        )

        spec.outline(
            cls.run_md,
            cls.finalize_md,
            cls.extract_frames,
        )

    def run_md(self):  # noqa: PLR0912
        """Run MD simulations for each structure and MD parameter set.

        Each combination is submitted as a `LammpsMdWorkChain`, which retries itself internally on
        plausibly transient LAMMPS failures - no retry bookkeeping needed here.
        """
        potential = self.inputs.potential_lammps
        # Loop over structures
        for structure in self.inputs.lammps_input_structures.get_ase_list():
            inputs = self.exposed_inputs(LammpsWorkChain, namespace="md")
            inputs.lammps.structure = StructureData(ase=structure)

            base_pair_style = self.inputs.potential_pair_style.value
            # `protocol` is optional with no default: when it is not given it is absent from the
            # inputs, and attribute access would raise.
            protocol = self.inputs.get("protocol")
            use_vdw_d2 = protocol is not None and protocol.value == "vdw_d2"

            _, engine = pe.match_engine(base_pair_style)
            if engine is None:
                raise ValueError(
                    f"`potential_pair_style` = '{base_pair_style}' does not match any known "
                    f"engine (known tags: {sorted(pe.ENGINES)}). Add it to "
                    "`aiida_trainspot/utils/potential_engines.json`."
                )
            potential_filename = pe.filename(base_pair_style)

            lammps_pair_style = "hybrid/overlay" if use_vdw_d2 else base_pair_style
            inputs.lammps.potential = generate_potential(potential, lammps_pair_style)

            generate_pair_coeff = engine.get("pair_coeff") is not None
            if "potential" in self.inputs.parameters:
                if "pair_coeff_list" in self.inputs.parameters["potential"]:
                    generate_pair_coeff = False

            pair_coeffs = None
            if generate_pair_coeff:
                if use_vdw_d2:
                    # Generate DFT-D2 pair coefficients, plus the hybrid-aware coefficients for
                    # whichever engine is the base potential.
                    pair_coeffs = get_dftd2_pair_coeffs(inputs.lammps.structure)
                    pair_coeffs.append(
                        pe.pair_coeff(engine, inputs.lammps.structure, hybrid=True, filename=potential_filename)
                    )
                else:
                    pair_coeffs = [
                        pe.pair_coeff(engine, inputs.lammps.structure, hybrid=False, filename=potential_filename)
                    ]

            params_list = self.inputs.params_list.get_list()
            input_parameters = self.inputs.parameters.get_dict()
            input_parameters.setdefault("potential", {})

            # The engine's own `pair_style` may not reveal which engine actually produced the
            # potential (e.g. it's "hybrid/overlay" for vdw_d2), so the filename is always passed
            # through explicitly rather than relying on aiida-lammps deriving it from `pair_style`.
            input_parameters["potential"].setdefault("potential_filename", potential_filename)

            if "potential_style_options" not in input_parameters["potential"]:
                options = pe.style_options(engine, potential_filename, hybrid=use_vdw_d2)
                if options is not None:
                    input_parameters["potential"]["potential_style_options"] = options

            if pair_coeffs is not None:
                input_parameters["potential"]["pair_coeff_list"] = pair_coeffs

            parameters = recursive_merge(DEFAULT_parameters.get_dict(), input_parameters)
            lammps_inputs = self.inputs.md.lammps
            if "settings" in lammps_inputs:
                inputs.lammps.settings = recursive_merge(
                    DEFAULT_settings.get_dict(), self.inputs.md.lammps.settings.get_dict()
                )
            else:
                inputs.lammps.settings = DEFAULT_settings.get_dict()
            # if 'dump' not in parameters:
            #     parameters['dump'] = {}
            parameters["dump"]["dump_rate"] = int(self.inputs.sampling_time / parameters["control"]["timestep"])

            # Loop over the MD parameter sets
            for params_md in params_list:
                if not any(inputs.lammps.structure.pbc):
                    params_md["integration"]["style"] = "nvt"

                constraint = params_md["integration"]["constraints"]

                # Map dimensions to constraints
                axes = ["x", "y", "z"]

                # Remove constraints for non-periodic directions
                for idx, axis in enumerate(axes):
                    if not inputs.lammps.structure.pbc[idx]:
                        constraint.pop(axis, None)  # Avoid KeyError if axis doesn't exist

                params_md["integration"]["constraints"] = constraint

                parameters["md"] = dict(params_md)

                inputs.lammps.parameters = Dict(parameters)
                future = self.submit(LammpsWorkChain, **inputs)
                self.to_context(md_wc=append_(future))

    def finalize_md(self):
        """Collect the trajectories from the completed LAMMPS calculations."""
        self.ctx.trajectories = {
            f"exploration_{ii}": calc.outputs.trajectories
            for ii, calc in enumerate(self.ctx.md_wc)
            if calc.exit_status == 0 and "trajectories" in calc.outputs
        }

        if not self.ctx.trajectories:
            self.report("All LAMMPS MD trajectories failed.")
            return self.exit_codes.ERROR_ALL_TRAJECTORIES_FAILED

    def extract_frames(self):
        """Extract sampled frames from the successful MD trajectories."""
        timestep = recursive_merge(DEFAULT_parameters.get_dict(), self.inputs.parameters.get_dict())["control"][
            "timestep"
        ]
        dump_rate = int(self.inputs.sampling_time / timestep)
        vacuum_inputs = self.inputs.get("vacuum", {})
        explored_dataset = LammpsFrameExtraction(
            self.inputs.sampling_time,
            dump_rate,
            thermalization_time=self.inputs.thermalization_time,
            check_vacuum=self.inputs.check_vacuum,
            min_vacuum=vacuum_inputs.get("min_vacuum", DEFAULT_min_vacuum),
            target_vacuum=vacuum_inputs.get("target_vacuum", DEFAULT_target_vacuum),
            **self.ctx.trajectories,
        )["explored_dataset"]

        if len(explored_dataset) == 0:
            return self.exit_codes.EMPTY_EXPLORATION_DATASET

        self.out("explored_dataset", explored_dataset)
