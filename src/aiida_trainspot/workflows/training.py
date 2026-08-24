"""Training workchain for AiiDA TrainsPot."""

import itertools
import random

from aiida.common.exceptions import MissingEntryPointError
from aiida.engine import WorkChain, append_, calcfunction
from aiida.orm import Bool, Float, FolderData, Int, Str
from aiida.plugins import WorkflowFactory

from aiida_trainspot.data.pesdata import PESData


def _try_workflow_factory(entry_point):
    """Resolve a workflow entry point, returning None if its package is not installed."""
    try:
        return WorkflowFactory(entry_point)
    except MissingEntryPointError:
        return None


MetaWorkChain = _try_workflow_factory("metatrain.base")
MaceWorkChain = _try_workflow_factory("mace.base")
NequipWorkChain = _try_workflow_factory("nequip.base")

DEFAULT_NON_TRAIN_FRAC = Float(0.2)
DEFAULT_SEED = Int(42)


@calcfunction
def SplitDataset(
    dataset,
    non_training_fraction=DEFAULT_NON_TRAIN_FRAC,
    seed=DEFAULT_SEED,
):
    """Split dataset preserving groups with stochastic rounding.

    Configurations already tagged with a "set" from a previous split are kept as-is;
    only the unassigned ones are grouped and split.
    """
    if not (0.0 < non_training_fraction.value < 1.0):
        raise ValueError("non_training_fraction must be between 0 and 1")

    train_p = 1.0 - non_training_fraction.value

    rng = random.Random(seed.value)

    exclude_list = [
        "energy",
        "cell",
        "stress",
        "forces",
        "symbols",
        "positions",
        "id_lammps",
        "input_structure_uuid",
        "sigma_strain",
    ]

    def check_exclude(key):
        return not any(el in key for el in exclude_list)

    def get_grouping_key(d):
        return tuple((k, v) for k, v in d.items() if check_exclude(k))

    # Already-classified configurations keep their existing bucket; only the
    # unassigned ones need grouping and (possibly stochastic) splitting.
    training_set = dataset.get_training().get_list()
    validation_set = dataset.get_validation().get_list()
    test_set = dataset.get_test().get_list()

    sorted_data = sorted(dataset.get_no_set().get_list(), key=get_grouping_key)
    grouped_data = itertools.groupby(sorted_data, key=get_grouping_key)

    for _, group in grouped_data:
        group_list = list(group)

        # ---- Forced assignment ----
        gen_method = group_list[0].get("gen_method")
        if gen_method in ("INPUT_STRUCTURE", "ISOLATED_ATOM", "EQUILIBRIUM") or len(group_list[0]["positions"]) == 1:
            training_set += group_list
            continue

        rng.shuffle(group_list)

        total = len(group_list)
        exp_train = int(total * train_p)
        # Split the data into sets
        training_set += group_list[:exp_train]
        validation_set += group_list[exp_train:][::2]
        test_set += group_list[exp_train:][1::2]

    # ---- tagging ----
    def tag(lst, label):
        for el in lst:
            el["set"] = label
            if "gen_method" not in el:
                el["gen_method"] = "UNKNOWN"

    tag(training_set, "TRAINING")
    tag(validation_set, "VALIDATION")
    tag(test_set, "TEST")

    def _pop_non_isolated(pool):
        """Pop a random non-ISOLATED_ATOM element from the given list."""
        non_isolated_indices = [i for i, el in enumerate(pool) if el.get("gen_method", "UNKNOWN") != "ISOLATED_ATOM"]

        if not non_isolated_indices:
            raise ValueError("Dataset too small: cannot split into TRAINING, VALIDATION, and TEST sets.")

        idx = random.choice(non_isolated_indices)
        return pool.pop(idx)

    # test or validation can be accidentally empty if the dataset is small
    # in that case we move one element from the training set to the empty set
    if len(validation_set) == 0:
        validation_set.append(_pop_non_isolated(training_set))

    if len(test_set) == 0:
        test_set.append(_pop_non_isolated(training_set))

    pes_global = PESData()
    pes_global.set_list(training_set + validation_set + test_set)

    return {
        "train_set": pes_global.get_training(),
        "validation_set": pes_global.get_validation(),
        "test_set": pes_global.get_test(),
        "global_splitted": pes_global,
    }


class TrainingWorkChain(WorkChain):
    """A workchain to loop over structures and submit MACEWorkChain."""

    ######################################################
    ##                 DEFAULT VALUES                   ##
    ######################################################
    ENGINE_WORKCHAINS = {
        name: workchain
        for name, workchain in (("MACE", MaceWorkChain), ("META", MetaWorkChain), ("NEQUIP", NequipWorkChain))
        if workchain is not None
    }
    ACCEPTED_ENGINES = list(ENGINE_WORKCHAINS)
    DEFAULT_TRAINING_ENGINE = "MACE" if "MACE" in ACCEPTED_ENGINES else next(iter(ACCEPTED_ENGINES), None)
    ######################################################

    @classmethod
    def define(cls, spec):
        """Input and output specification."""
        super().define(spec)

        if not cls.ACCEPTED_ENGINES:
            raise RuntimeError(
                "No training engine plugin is installed. Install at least one of `aiida-mace` or `aiida-metatrain`."
            )

        spec.input(
            "num_potentials",
            valid_type=Int,
            default=lambda: Int(1),
            required=False,
            validator=cls.validate_num_potentials,
        )
        spec.input("non_training_fraction", valid_type=Float, default=lambda: Float(0.2), required=False)
        spec.input(
            "engine",
            default=lambda: Str(cls.DEFAULT_TRAINING_ENGINE),
            valid_type=Str,
            help="Training engine",
            required=True,
            validator=cls.validate_engine,
        )
        spec.input(
            "dataset",
            valid_type=PESData,
            help="Training dataset",
        )
        spec.input_namespace(
            "checkpoints",
            valid_type=FolderData,
            required=False,
            help="Checkpoints file",
        )
        for name, workchain in cls.ENGINE_WORKCHAINS.items():
            spec.expose_inputs(
                workchain,
                namespace=name.lower(),
                exclude=("train.training_set", "train.validation_set", "train.test_set"),
                namespace_options={"validator": None, "required": False, "populate_defaults": False},
            )

        spec.inputs.validator = cls.validate_inputs
        spec.output_namespace("training", dynamic=True, help="Training outputs")
        spec.output(
            "global_splitted",
            valid_type=PESData,
        )
        spec.exit_code(
            300,
            "ERROR_ALL_CHILDREN_FAILED",
            message="All child training workchains failed.",
        )
        spec.outline(cls.run_training, cls.finalize)

    @classmethod
    def validate_inputs(cls, inputs, _):
        """Validate the inputs based on the selected engine."""
        engine = inputs["engine"].value
        namespace = engine.lower()
        if namespace not in inputs:
            return f"Missing required `{namespace}` inputs for engine='{engine}'."
        return None

    @classmethod
    def validate_engine(cls, value, _):
        """Validate the engine input."""
        if value.value not in cls.ACCEPTED_ENGINES:
            return f"The `engine` input can only be {', '.join(cls.ACCEPTED_ENGINES)}."

    @classmethod
    def validate_num_potentials(cls, value, _):
        """Validate the num_potentials input."""
        if value.value < 1:
            return "The `num_potentials` input must be at least 1."

    def run_training(self):
        """Run training."""
        split_datasets = SplitDataset(self.inputs.dataset, self.inputs.non_training_fraction)
        train_set = split_datasets["train_set"]
        validation_set = split_datasets["validation_set"]
        test_set = split_datasets["test_set"]

        self.out("global_splitted", split_datasets["global_splitted"])

        self.report(f"Training set size: {len(train_set)}")
        self.report(f"Validation set size: {len(validation_set)}")
        self.report(f"Test set size: {len(test_set)}")

        engine = self.inputs.engine.value
        namespace = engine.lower()
        workchain = self.ENGINE_WORKCHAINS[engine]
        context_key = f"{namespace}_wc"

        inputs = self.exposed_inputs(workchain, namespace=namespace)

        inputs.train["training_set"] = train_set
        inputs.train["validation_set"] = validation_set
        inputs.train["test_set"] = test_set

        chkpts = []
        if "checkpoints" in self.inputs:
            inputs["checkpoints"] = self.inputs.checkpoints
            inputs.train["restart"] = Bool(True)
            chkpts = list(inputs.checkpoints.values())

        for ii in range(self.inputs.num_potentials.value):
            if ii < len(chkpts):
                inputs.train["checkpoints"] = chkpts[ii]

            future = self.submit(workchain, **inputs)
            self.to_context(**{context_key: append_(future)})

    def finalize(self):
        """Collect and output results from all WorkChain instances."""
        namespace = self.inputs.engine.value.lower()
        children = self.ctx[f"{namespace}_wc"]

        results = {}
        for ii, calc in enumerate(children):
            if not calc.is_finished_ok:
                self.report(f"Child `{namespace}_{ii}` did not finish successfully, skipping its outputs.")
                continue
            results[f"{namespace}_{ii}"] = {el: calc.outputs[el] for el in calc.outputs}

        if not results:
            self.report(f"All {len(children)} child `{namespace}` training workchains failed.")
            return self.exit_codes.ERROR_ALL_CHILDREN_FAILED

        self.out("training", results)
