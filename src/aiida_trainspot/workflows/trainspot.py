"""AiiDA WorkChain for active learning of interatomic potentials using LAMMPS and MACE."""

import random

from aiida import load_profile
from aiida.engine import WorkChain, calcfunction, if_, while_
from aiida.orm import Bool, Dict, Float, FolderData, Int, List, SinglefileData, Str, StructureData, load_node
from aiida_quantumespresso.workflows.pw.base import PwBaseWorkChain
from ase import Atoms

from aiida_trainspot.utils.generate_config import generate_lammps_md_config
from aiida_trainspot.utils.tools import error_calibration

from ..calculations.evaluation import EvaluationCalculation
from ..data.pesdata import PESData
from ..utils.potential_engines import ENGINES, default_pair_style_for_training_engine, is_pair_style_compatible
from ..utils.restart import resume_trainspotwc
from .dataset_augmentation import DatasetAugmentationWorkChain
from .exploration import (
    DEFAULT_potential_pair_style,
    DEFAULT_sampling_time,
    DEFAULT_thermalization_time,
    ExplorationWorkChain,
)
from .labelling import AbInitioLabellingWorkChain
from .training import TrainingWorkChain

load_profile()


# Every training_engine that can produce at least one pair_style in potential_engines.json.
ALLOWED_ENGINES = sorted(
    {training_engine for engine in ENGINES.values() for training_engine in engine["training_engine"]}
)


@calcfunction
def SaveRMSE(rmse):
    """A calcfunction to save RMSE values stored in a list of dictionaries as an AiiDA output.

    :param rmse: A list containing dictionaries or JSON-serializable data.
    :return: A List node containing the RMSE values.
    """
    # Convert any AiiDA Dict nodes in the input list to raw dictionaries
    rmse_serializable = [item.get_dict() if isinstance(item, Dict) else item for item in rmse]

    return List(list=rmse_serializable)


@calcfunction
def SelectToLabel(evaluated_dataset, thr_energy, thr_forces, thr_stress, max_frames=None):
    """Select configurations to label."""
    if max_frames:
        max_frames = max_frames.value
    selected_dataset = []
    energy_deviation = []
    forces_deviation = []
    stress_deviation = []
    loss = []
    for config in evaluated_dataset:
        energy_deviation.append(config["energy_deviation"])
        forces_deviation.append(config["forces_deviation"])
        stress_deviation.append(config["stress_deviation"])
        if (
            config["energy_deviation"] > thr_energy
            or config["forces_deviation"] > thr_forces
            or config["stress_deviation"] > thr_stress
        ):
            selected_dataset.append(config)
            if max_frames:
                loss.append(
                    config["energy_deviation"] / thr_energy
                    + config["forces_deviation"] / thr_forces
                    + config["stress_deviation"] / thr_stress
                )
    if max_frames:
        if len(selected_dataset) > max_frames:
            random.shuffle(selected_dataset)
            selected_dataset = selected_dataset[:max_frames]
    pes_selected_dataset = PESData(selected_dataset)
    return {
        "selected_dataset": pes_selected_dataset,
        "min_energy_deviation": Float(min(energy_deviation)),
        "max_energy_deviation": Float(max(energy_deviation)),
        "min_forces_deviation": Float(min(forces_deviation)),
        "max_forces_deviation": Float(max(forces_deviation)),
        "min_stress_deviation": Float(min(stress_deviation)),
        "max_stress_deviation": Float(max(stress_deviation)),
    }


def validate_engine(value, _):
    """Validate the training engine input."""
    if value.value not in ALLOWED_ENGINES:
        return f"Invalid training engine: {value.value}. Must be one of {ALLOWED_ENGINES}."
    return None


######################################################
##                 DEFAULT VALUES                   ##
######################################################
DEFAULT_thr_energy = Float(0.001)
DEFAULT_thr_forces = Float(0.1)
DEFAULT_thr_stress = Float(0.001)

DEFAULT_max_selected_frames = Int(1000)
DEFAULT_random_input_structures_lammps = Bool(True)
DEFAULT_num_random_structures_lammps = Int(20)

DEFAULT_max_loops = Int(10)

DEFAULT_do_dataset_augmentation = Bool(True)
DEFAULT_do_ab_initio_labelling = Bool(True)
DEFAULT_training_engine = Str("MACE")
DEFAULT_do_training = Bool(True)
DEFAULT_do_exploration = Bool(True)
######################################################


class TrainsPotWorkChain(WorkChain):
    """WorkChain to launch LAMMPS calculations."""

    @classmethod
    def define(cls, spec):
        """Specify inputs and outputs."""
        super().define(spec)
        spec.input(
            "do_dataset_augmentation",
            valid_type=Bool,
            default=lambda: DEFAULT_do_dataset_augmentation,
            help="Do data generation",
            required=False,
        )
        spec.input(
            "do_ab_initio_labelling",
            valid_type=Bool,
            default=lambda: DEFAULT_do_ab_initio_labelling,
            help="Do ab_initio_labelling calculations",
            required=False,
        )
        spec.input(
            "training_engine",
            valid_type=Str,
            default=lambda: DEFAULT_training_engine,
            help=f"Training engine (allowed values: {ALLOWED_ENGINES})",
            required=False,
            validator=validate_engine,
        )
        spec.input(
            "do_training",
            valid_type=Bool,
            default=lambda: DEFAULT_do_training,
            help="Do MACE calculations",
            required=False,
        )
        spec.input(
            "do_exploration",
            valid_type=Bool,
            default=lambda: DEFAULT_do_exploration,
            help="Do exploration calculations",
            required=False,
        )
        spec.input(
            "max_loops",
            valid_type=Int,
            default=lambda: DEFAULT_max_loops,
            help="Maximum number of active learning workflow loops",
            required=False,
        )

        spec.input(
            "random_input_structures_lammps",
            valid_type=Bool,
            help="If true, input structures for LAMMPS are randomly selected from the dataset",
            default=lambda: DEFAULT_random_input_structures_lammps,
            required=False,
        )
        spec.input(
            "num_random_structures_lammps",
            valid_type=Int,
            help="Number of random structures for LAMMPS",
            default=lambda: DEFAULT_num_random_structures_lammps,
            required=False,
        )
        spec.input(
            "lammps_input_structures",
            valid_type=PESData,
            help="Input structures for lammps, if not specified input structures are used",
            required=False,
        )
        spec.input(
            "dataset",
            valid_type=PESData,
            help="Dataset containing labelled structures and structures to be labelled",
            required=True,
        )

        spec.input_namespace(
            "models_lammps", valid_type=SinglefileData, help="Potential for md exploration", required=False
        )
        spec.input_namespace(
            "models_lammps_mliap",
            valid_type=SinglefileData,
            help="Potential for md exploration with pair_style mliap unified",
            required=False,
        )
        spec.input_namespace("models_ase", valid_type=SinglefileData, help="Potential for Evaluation", required=False)
        spec.input(
            "exploration.parameters", valid_type=Dict, help="List of parameters for md exploration", required=False
        )
        spec.input("explored_dataset", valid_type=PESData, help="List of structures from exploration", required=False)

        spec.input(
            "thr_energy",
            valid_type=Float,
            help="Threshold for energy",
            required=True,
            default=lambda: DEFAULT_thr_energy,
        )
        spec.input(
            "thr_forces",
            valid_type=Float,
            help="Threshold for forces",
            required=True,
            default=lambda: DEFAULT_thr_forces,
        )
        spec.input(
            "thr_stress",
            valid_type=Float,
            help="Threshold for stress",
            required=True,
            default=lambda: DEFAULT_thr_stress,
        )
        spec.input(
            "max_selected_frames",
            valid_type=Int,
            help="Maximum number of frames to be selected for labelling per iteration",
            required=False,
            default=lambda: DEFAULT_max_selected_frames,
        )

        spec.inputs.validator = cls.validate_inputs

        spec.expose_inputs(
            DatasetAugmentationWorkChain,
            namespace="dataset_augmentation",
            exclude=("structures",),
        )
        spec.expose_inputs(
            AbInitioLabellingWorkChain,
            namespace="ab_initio_labelling",
            exclude=("unlabelled_dataset",),
            namespace_options={"validator": None},
        )
        spec.expose_inputs(
            TrainingWorkChain,
            namespace="training",
            exclude=("dataset", "engine"),
            namespace_options={"validator": None, "required": False, "populate_defaults": False},
        )
        spec.expose_inputs(
            ExplorationWorkChain,
            namespace="exploration",
            exclude=("potential_lammps", "lammps_input_structures"),
            namespace_options={"validator": None},
        )
        spec.expose_inputs(
            EvaluationCalculation,
            namespace="committee_evaluation",
            exclude=("engine", "ase_potentials", "datasets"),
        )

        spec.output(
            "dataset",
            valid_type=PESData,
            help="Final dataset containing all structures labelled and selected to be labelled",
        )
        spec.output_namespace(
            "models_ase",
            required=False,
            valid_type=SinglefileData,
            help="Last committee of trained potentials compiled for ASE",
        )
        spec.output_namespace(
            "models_lammps",
            required=False,
            valid_type=SinglefileData,
            help="Last committee of trained potentials compiled for LAMMPS",
        )
        spec.output_namespace(
            "models_lammps_mliap",
            required=False,
            valid_type=SinglefileData,
            help="Last committee of trained potentials compiled for LAMMPS pair_style mliap unified",
        )
        spec.output_namespace(
            "checkpoints",
            required=False,
            valid_type=FolderData,
            help="Last checkpoints of trained potentials",
        )
        spec.output(
            "RMSE",
            required=False,
            valid_type=List,
            help="RMSE on the final dataset computed with the last committee of potentials",
        )
        spec.output(
            "explored_dataset",
            required=False,
            valid_type=PESData,
            help="Structures sampled during the last successful MD exploration, if it was performed.",
        )

        spec.exit_code(
            200,
            "NO_LABELLED_STRUCTURES",
            message="No labelled structures in the dataset.",
        )
        spec.exit_code(
            201,
            "MISSING_PSEUDOS",
            message="Missing pseudopotentials for some atomic species in the input dataset.",
        )

        spec.exit_code(
            308,
            "LESS_THAN_2_POTENTIALS",
            message="Calculation didn't produce more than 1 expected potentials.",
        )
        spec.exit_code(
            320,
            "ERROR_DATASET_AUGMENTATION_FAILED",
            message="The dataset augmentation workchain did not finish successfully.",
        )
        spec.exit_code(
            321,
            "ERROR_AB_INITIO_LABELLING_FAILED",
            message="The ab initio labelling workchain did not finish successfully.",
        )
        spec.exit_code(
            322,
            "ERROR_TRAINING_FAILED",
            message="The training workchain did not finish successfully.",
        )
        spec.exit_code(
            323,
            "ERROR_EXPLORATION_FAILED",
            message="The exploration workchain did not finish successfully.",
        )
        spec.exit_code(
            324,
            "ERROR_COMMITTEE_EVALUATION_FAILED",
            message="The committee evaluation calculation did not finish successfully.",
        )
        spec.exit_code(
            330,
            "ERROR_NO_MLIAP_POTENTIAL",
            message="Exploration requested pair_style mliap but no trained potential produced an mliap-format model.",
        )

        spec.outline(
            cls.initialization,
            if_(cls.do_dataset_augmentation)(cls.dataset_augmentation, cls.finalize_dataset_augmentation),
            while_(cls.check_iteration)(
                if_(cls.do_ab_initio_labelling)(cls.ab_initio_labelling, cls.finalize_ab_initio_labelling),
                if_(cls.do_training)(cls.training, cls.finalize_training),
                if_(cls.do_exploration)(
                    cls.exploration,
                    cls.finalize_exploration,
                ),
                if_(cls.do_evaluation)(cls.run_committee_evaluation, cls.finalize_committee_evaluation),
            ),
            cls._set_outputs,
        )

    @classmethod
    def validate_inputs(cls, inputs, _):
        """Validate the top-level inputs."""
        # --- Exploration validation ---
        if "exploration" in inputs:
            md_params_list = inputs["exploration"].get("params_list")

            if not md_params_list or len(md_params_list) == 0:
                return "The `exploration.params_list` input is required to perform exploration."

            try:
                num_timesteps = [el["max_number_steps"] for el in md_params_list.get_list()]
            except Exception:
                return "`exploration.params_list` must contain `max_number_steps`."

            try:
                timestep = inputs["exploration"]["parameters"]["control"]["timestep"]
            except Exception:
                return "Missing `exploration.parameters.control.timestep`."

            thermalization_time = inputs["exploration"].get("thermalization_time", DEFAULT_thermalization_time)
            sampling_time = inputs["exploration"].get("sampling_time", DEFAULT_sampling_time)

            if thermalization_time + sampling_time > min(num_timesteps) * timestep:
                return (
                    "The sum of `exploration.thermalization_time` and "
                    "`exploration.sampling_time` cannot be greater than the "
                    "shortest MD simulation time. "
                    f"({thermalization_time.value} + {sampling_time.value} "
                    f"> {min(num_timesteps) * timestep})."
                )

    @classmethod
    def get_builder(
        cls,
        dataset,
        abinitiolabelling_code,
        md_code,
        training_engine=None,
        abinitiolabelling_protocol=None,
        pseudo_family=None,
        md_protocol=None,
        dft_engine_entry_point=None,
        demo=False,
        **kwargs,
    ):
        """Return a builder prepopulated with protocol defaults."""
        builder = super().get_builder(**kwargs)
        builder.dataset = dataset

        # ---------- Dataset augmentation ----------
        if demo:
            builder.dataset_augmentation.do_slabs = Bool(False)
            builder.dataset_augmentation.do_alloys = Bool(False)
            builder.dataset_augmentation.rsd.params.n_configs = Int(3)
            builder.dataset_augmentation.clusters.n_clusters = Int(3)
            builder.dataset_augmentation.clusters.max_atoms = Int(6)
            builder.dataset_augmentation.replicate.max_atoms = Int(24)

        # ---------- Quantum ESPRESSO ----------
        qe_protocol = abinitiolabelling_protocol or "stringent"

        atomic_species = dataset.get_atomic_species()
        fictitious_structure = StructureData(ase=Atoms(atomic_species))

        overrides = {"pseudo_family": pseudo_family} if pseudo_family else {}

        qe_builder = PwBaseWorkChain.get_builder_from_protocol(
            protocol=qe_protocol,
            code=abinitiolabelling_code,
            structure=fictitious_structure,
            overrides=overrides,
        )

        builder.ab_initio_labelling.quantumespresso = qe_builder
        if dft_engine_entry_point:
            builder.ab_initio_labelling.dft_engine_entry_point = Str(dft_engine_entry_point)

        # ---------- Training ----------
        if training_engine:
            builder.training_engine = training_engine

        # ---------- LAMMPS ----------
        if md_protocol not in (None, "vdw_d2"):
            raise ValueError(f"MD protocol `{md_protocol}` not supported.")

        builder.exploration.md.lammps.code = md_code

        default_steps = 50
        default_timestep = 0.001
        builder.exploration.params_list = generate_lammps_md_config(
            temperatures=[300],
            pressures=[0.0],
            steps=[default_steps],
            styles=["nvt"],
            dt=default_timestep,
        )

        builder.exploration.protocol = md_protocol
        builder.exploration.parameters = Dict({"control": {"timestep": default_timestep}})
        builder.exploration.sampling_time = Float(default_steps * default_timestep / 5)

        return builder

    @classmethod
    def get_builder_resume(cls, identifier, **kwargs):
        """Return a builder to resume a previous (possibly interrupted) TrainsPotWorkChain.

        Combines `get_builder(...)` with `resume_trainspotwc(...)`: reuses whatever
        dataset/potentials/checkpoints/explored_dataset the run identified by `identifier`
        produced before finishing or failing, and skips the corresponding stages accordingly.
        `abinitiolabelling_code`/`md_code` are taken from the previous run's own inputs if not
        given explicitly, so a plain `get_builder_resume(<pk>)` works out of the box.

        :param identifier: pk or uuid of the previous TrainsPotWorkChain to resume from.
        :param kwargs: forwarded to `get_builder()` (codes, protocols, pseudo_family, etc. -- these
            are fresh deployment configuration for the new run, not part of the resumed state).
        """
        previous_node = load_node(identifier)
        previous_dataset = previous_node.outputs["dataset"]

        if "abinitiolabelling_code" not in kwargs:
            kwargs["abinitiolabelling_code"] = previous_node.inputs.ab_initio_labelling.quantumespresso.pw.code
        if "md_code" not in kwargs:
            kwargs["md_code"] = previous_node.inputs.exploration.md.lammps.code

        builder = cls.get_builder(dataset=previous_dataset, **kwargs)
        return resume_trainspotwc(builder, identifier)

    def do_dataset_augmentation(self):
        """Check if dataset augmentation should be performed."""
        return bool(self.ctx.do_dataset_augmentation)

    def do_ab_initio_labelling(self):
        """Check if ab initio labelling should be performed."""
        return bool(self.ctx.do_ab_initio_labelling)

    def do_training(self):
        """Check if training should be performed."""
        return bool(self.ctx.do_training)

    def do_exploration(self):
        """Check if exploration should be performed."""
        return bool(self.ctx.do_exploration)

    def do_evaluation(self):
        """Check if committee evaluation should be performed."""
        return "explored_dataset" in self.ctx

    def check_iteration(self):
        """Check if the maximum number of iterations has been reached."""
        if self.ctx.iteration > 0:
            self.ctx.do_dataset_augmentation = False
            self.ctx.do_ab_initio_labelling = True
            self.ctx.do_training = True
            self.ctx.do_exploration = True
        self.ctx.iteration += 1
        return self.ctx.iteration < self.inputs.max_loops + 1

    def initialization(self):
        """Initialize workflow context."""
        # --- Thresholds ---
        self.ctx.thr_energy = self.inputs.thr_energy
        self.ctx.thr_forces = self.inputs.thr_forces
        self.ctx.thr_stress = self.inputs.thr_stress

        self.ctx.max_frames = self.inputs.get("max_selected_frames")

        # --- Base state ---
        self.ctx.rmse = []
        self.ctx.iteration = 0
        self.ctx.dataset = self.inputs.get("dataset", PESData())

        self.ctx.do_dataset_augmentation = self.inputs.do_dataset_augmentation
        self.ctx.do_ab_initio_labelling = self.inputs.do_ab_initio_labelling
        self.ctx.do_training = self.inputs.do_training
        self.ctx.do_exploration = self.inputs.do_exploration

        # --- Dataset sanity ---
        if not self.ctx.do_ab_initio_labelling and self.ctx.do_training:
            if self.ctx.dataset.len_labelled == 0:
                return self.exit_codes.NO_LABELLED_STRUCTURES

        # --- Potentials ---
        if not self.ctx.do_training:
            self.ctx.potentials_lammps = list(self.inputs.get("models_lammps", {}).values())
            self.ctx.potentials_lammps_mliap = list(self.inputs.get("models_lammps_mliap", {}).values())
            self.ctx.potentials_ase = list(self.inputs.get("models_ase", {}).values())
            self.ctx.potential_checkpoints = list(self.inputs.get("training", {}).get("checkpoints", {}).values())

        # --- Exploration dataset ---
        if not self.ctx.do_exploration and "explored_dataset" in self.inputs:
            if len(self.inputs.explored_dataset) > 0:
                self.ctx.explored_dataset = self.inputs.explored_dataset

        # --- LAMMPS input structures ---
        if "lammps_input_structures" in self.inputs:
            self.ctx.lammps_input_structures = self.inputs.lammps_input_structures
        else:
            self.ctx.lammps_input_structures = PESData(self.inputs.dataset.get_ase_list())

        # --- Pseudopotential validation ---
        atomic_species = self.ctx.dataset.get_atomic_species()
        pseudos = self.inputs.ab_initio_labelling.quantumespresso.pw.pseudos

        missing = [s for s in atomic_species if s not in pseudos]
        if missing:
            return self.exit_codes.MISSING_PSEUDOS

    def dataset_augmentation(self):
        """Generate data for the dataset."""
        inputs = self.exposed_inputs(DatasetAugmentationWorkChain, namespace="dataset_augmentation")
        inputs["structures"] = self.ctx.dataset

        future = self.submit(DatasetAugmentationWorkChain, **inputs)
        self.report(f"launched lammps calculation <{future.pk}>")
        self.to_context(dataset_augmentation=future)

    def ab_initio_labelling(self):
        """Run ab_initio_labelling calculations."""
        # Set up the inputs for LoopingLabellingWorkChain
        inputs = self.exposed_inputs(AbInitioLabellingWorkChain, namespace="ab_initio_labelling")
        inputs.unlabelled_dataset = self.ctx.dataset.get_unlabelled()

        # Submit LoopingLabellingWorkChain
        future = self.submit(AbInitioLabellingWorkChain, **inputs)

        self.report(f"Launched AbInitioLabellingWorkChain with ase_list <{future.pk}>")
        self.to_context(ab_initio_labelling=future)

    def training(self):
        """Run training calculations."""
        inputs = self.exposed_inputs(TrainingWorkChain, namespace="training")
        inputs.dataset = self.ctx.dataset.get_labelled()
        inputs.engine = self.inputs.training_engine
        if "potential_checkpoints" in self.ctx:
            inputs["checkpoints"] = {
                f"chkpt_{ii+1}": self.ctx.potential_checkpoints[-(ii + 1)]
                for ii in range(
                    min(
                        len(self.ctx.potential_checkpoints),
                        self.inputs.training.num_potentials.value,
                    )
                )
            }

        future = self.submit(TrainingWorkChain, **inputs)

        self.report(f"Launched TrainingWorkChain with dataset_list <{future.pk}>")
        self.to_context(training=future)

    def exploration(self):
        """Run exploration."""
        inputs = self.exposed_inputs(ExplorationWorkChain, namespace="exploration")
        training_engine = self.inputs.training_engine.value
        pair_style = (
            inputs.potential_pair_style.value
            if "potential_pair_style" in inputs
            else DEFAULT_potential_pair_style.value
        )

        # A potential is only usable in the pair_style produced by its training_engine (e.g.
        # metatrain never exports an mliap-format model). If the user's choice doesn't match,
        # warn and fall back to that engine's own default rather than failing deep inside LAMMPS.
        if not is_pair_style_compatible(pair_style, training_engine):
            default_pair_style = default_pair_style_for_training_engine(training_engine) or (
                DEFAULT_potential_pair_style.value
            )
            self.report(
                f"`potential_pair_style` = '{pair_style}' is not produced by training_engine "
                f"'{training_engine}'; using '{default_pair_style}' instead."
            )
            pair_style = default_pair_style
            inputs.potential_pair_style = Str(default_pair_style)

        if "mliap" in pair_style:
            if not self.ctx.potentials_lammps_mliap:
                self.report(
                    "potential_pair_style requests mliap, but no trained potential produced an "
                    "mliap-format model (check the training engine/postprocess code version)."
                )
                self._set_outputs()
                return self.exit_codes.ERROR_NO_MLIAP_POTENTIAL
            inputs.potential_lammps = self.ctx.potentials_lammps_mliap[-1]
        else:
            inputs.potential_lammps = self.ctx.potentials_lammps[-1]

        if "random_input_structures_lammps" in self.inputs:
            if self.inputs.random_input_structures_lammps:
                if "input_lammps_dataset" in self.ctx:
                    self.ctx.lammps_input_structures = self.ctx.input_lammps_dataset
                else:
                    self.ctx.lammps_input_structures = self.ctx.dataset

        # Select random input structures for LAMMPS avoiding isolated atoms
        discarded = set()
        selected = []
        num_structures = self.inputs.num_random_structures_lammps.value
        while len(selected) < num_structures:
            # If choosed all non-discarded unique values, break
            remaining_capacity = len(self.ctx.lammps_input_structures) - len(discarded)
            if remaining_capacity == len(selected):
                self.report(
                    f"Only {len(selected)} random input structures for LAMMPS are selected "
                    f"({num_structures} where requested)."
                )
                break

            x = random.choice(range(len(self.ctx.lammps_input_structures)))
            if len(self.ctx.lammps_input_structures.get_ase_item(x)) < 2:  # noqa: PLR2004
                discarded.add(x)
                continue  # reject isolated atoms
            if x in selected:
                continue  # reject duplicate
            selected.append(x)

        self.ctx.lammps_input_structures = PESData([self.ctx.lammps_input_structures.get_item(key) for key in selected])

        inputs.lammps_input_structures = self.ctx.lammps_input_structures

        if inputs.get("check_vacuum", True):
            vacuum_inputs = dict(inputs.get("vacuum", {}))
            if "min_vacuum" not in vacuum_inputs:
                try:
                    vacuum_inputs["min_vacuum"] = Float(self.inputs.training.mace.train.mace_config.get_dict()["r_max"])
                except Exception:
                    pass
            if "target_vacuum" not in vacuum_inputs and "vacuum" in self.inputs.get("dataset_augmentation", {}):
                vacuum_inputs["target_vacuum"] = self.inputs.dataset_augmentation.vacuum
            if vacuum_inputs:
                inputs.vacuum = vacuum_inputs

        future = self.submit(ExplorationWorkChain, **inputs)

        self.report(f"Launched ExplorationWorkChain with dataset_list <{future.pk}>")
        self.to_context(exploration=future)

    def run_committee_evaluation(self):
        """Run committee evaluation."""
        inputs = self.exposed_inputs(EvaluationCalculation, namespace="committee_evaluation")

        inputs["engine"] = self.inputs.training_engine
        inputs["ase_potentials"] = {
            f"pot_{ii}": self.ctx.potentials_ase[ii] for ii in range(len(self.ctx.potentials_ase))
        }
        inputs["datasets"] = {"labelled": self.ctx.dataset, "exploration": self.ctx.explored_dataset}

        future = self.submit(EvaluationCalculation, **inputs)
        self.to_context(committee_evaluation=future)

    def finalize_dataset_augmentation(self):
        """Finalize dataset augmentation."""
        if not self.ctx.dataset_augmentation.is_finished_ok:
            self.report("DatasetAugmentationWorkChain did not finish successfully.")
            self._set_outputs()
            return self.exit_codes.ERROR_DATASET_AUGMENTATION_FAILED
        self.ctx.dataset += self.ctx.dataset_augmentation.outputs.structures.global_structures
        self.ctx.input_lammps_dataset = self.ctx.dataset

    def finalize_ab_initio_labelling(self):
        """Finalize ab_initio_labelling calculations."""
        if not self.ctx.ab_initio_labelling.is_finished_ok:
            self.report("AbInitioLabellingWorkChain did not finish successfully.")
            self._set_outputs()
            return self.exit_codes.ERROR_AB_INITIO_LABELLING_FAILED
        self.ctx.dataset = (
            self.ctx.dataset.get_labelled() + self.ctx.ab_initio_labelling.outputs.ab_initio_labelling_data
        )

    def finalize_training(self):
        """Finalize training and collect potentials."""
        if not self.ctx.training.is_finished_ok:
            self.report("TrainingWorkChain did not finish successfully.")
            self._set_outputs()
            return self.exit_codes.ERROR_TRAINING_FAILED
        if len(self.ctx.training.outputs.training) < 2:  # noqa: PLR2004
            self._set_outputs()
            return self.exit_codes.LESS_THAN_2_POTENTIALS

        self.ctx.potentials_ase = []
        self.ctx.potentials_lammps = []
        self.ctx.potentials_lammps_mliap = []
        self.ctx.potential_checkpoints = []
        for _, calc in enumerate(self.ctx.training.outputs.training.values()):
            if "checkpoints" in calc:
                self.ctx.potential_checkpoints.append(calc["checkpoints"])
            if "model_stage2_ase" in calc:
                self.ctx.potentials_ase.append(calc["model_stage2_ase"])
            elif "model_stage1_ase" in calc:
                self.ctx.potentials_ase.append(calc["model_stage1_ase"])
            if "model_stage2_lammps" in calc:
                self.ctx.potentials_lammps.append(calc["model_stage2_lammps"])
            elif "model_stage1_lammps" in calc:
                self.ctx.potentials_lammps.append(calc["model_stage1_lammps"])
            if "model_stage2_mliap" in calc:
                self.ctx.potentials_lammps_mliap.append(calc["model_stage2_mliap"])
            elif "model_stage1_mliap" in calc:
                self.ctx.potentials_lammps_mliap.append(calc["model_stage1_mliap"])
            elif "model_lammps_mliap" in calc:
                self.ctx.potentials_lammps_mliap.append(calc["model_lammps_mliap"])
            if "model" in calc:
                self.ctx.potentials_lammps.append(calc["model"])
                self.ctx.potentials_ase.append(calc["model"])

        self.ctx.dataset = self.ctx.training.outputs.global_splitted

    def finalize_exploration(self):
        """Finalize exploration and collect the sampled dataset."""
        if not self.ctx.exploration.is_finished_ok:
            self.report("ExplorationWorkChain did not finish successfully.")
            self._set_outputs()
            return self.exit_codes.ERROR_EXPLORATION_FAILED
        self.ctx.explored_dataset = self.ctx.exploration.outputs.explored_dataset

    def finalize_committee_evaluation(self):
        """Finalize committee evaluation and select structures to label."""
        calc = self.ctx.committee_evaluation
        if not calc.is_finished_ok:
            self.report("Committee evaluation calculation did not finish successfully.")
            self._set_outputs()
            return self.exit_codes.ERROR_COMMITTEE_EVALUATION_FAILED
        self.ctx.thr_energy, self.ctx.thr_forces, self.ctx.thr_stress = error_calibration(
            calc.outputs.evaluated_datasets.labelled,
            self.inputs.thr_energy,
            self.inputs.thr_forces,
            self.inputs.thr_stress,
        )
        selected = SelectToLabel(
            calc.outputs.evaluated_datasets.exploration,
            self.ctx.thr_energy,
            self.ctx.thr_forces,
            self.ctx.thr_stress,
            self.ctx.max_frames,
        )
        self.ctx.dataset += selected["selected_dataset"]
        self.ctx.rmse.append(calc.outputs.rmse.labelled.get_dict())

        # Superseded by the committee-labelled selection above: no longer useful past this point.
        del self.ctx.explored_dataset

        self.report(
            f"Structures selected for labelling: {len(selected['selected_dataset'])}/"
            f"{len(calc.outputs.evaluated_datasets.exploration)}"
        )
        self.report(
            f"Min energy deviation: {round(selected['min_energy_deviation'].value,2)} eV, "
            f"Max energy deviation: {round(selected['max_energy_deviation'].value,2)} eV"
        )
        self.report(
            f"Min forces deviation: {round(selected['min_forces_deviation'].value,2)} eV/Å, "
            f"Max forces deviation: {round(selected['max_forces_deviation'].value,2)} eV/Å"
        )
        self.report(
            f"Min stress deviation: {round(selected['min_stress_deviation'].value,2)} kbar, "
            f"Max stress deviation: {round(selected['max_stress_deviation'].value,2)} kbar"
        )

    def _set_outputs(self):
        """Set the outputs accumulated so far in the context, whether the run completed or a step failed early."""
        if "rmse" in self.ctx:
            self.out("RMSE", SaveRMSE(self.ctx.rmse))
        self.out("dataset", self.ctx.dataset)
        if "potentials_ase" in self.ctx:
            self.out(
                "models_ase",
                {f"model_{ii+1}": pot for ii, pot in enumerate(self.ctx.potentials_ase)},
            )
        if "potentials_lammps" in self.ctx:
            self.out(
                "models_lammps",
                {f"model_{ii+1}": pot for ii, pot in enumerate(self.ctx.potentials_lammps)},
            )
        if self.ctx.get("potentials_lammps_mliap"):
            self.out(
                "models_lammps_mliap",
                {f"model_{ii+1}": pot for ii, pot in enumerate(self.ctx.potentials_lammps_mliap)},
            )
        if "potential_checkpoints" in self.ctx:
            self.out(
                "checkpoints",
                {f"model_{ii+1}": pot for ii, pot in enumerate(self.ctx.potential_checkpoints)},
            )
        if "explored_dataset" in self.ctx:
            self.out("explored_dataset", self.ctx.explored_dataset)
