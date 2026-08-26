"""Utilities to restart training from previous workchains."""

from aiida.orm import Bool, load_node


def models_from_trainingwc(builder, identifier, get_labelled_dataset=False, get_config=False):
    """Return a builder populated with potentials and checkpoints from previous training.

    Args:
        builder: Builder to be populated.
        identifier: Identifier of the training workchain (pk or uuid).
        get_labelled_dataset: If True, the labelled dataset will be added to the builder.
        get_config: If True, the mace configuration parameters will be added to the builder.

    Returns:
        builder: Builder populated with potentials, checkpoints and eventually labelled
        dataset and mace configuration parameters.
    """
    outputs = load_node(identifier).outputs
    models_ase = {}
    models_lammps = {}
    models_checkpoints = {}
    if get_labelled_dataset:
        builder.dataset = outputs["global_splitted"]
    if get_config:
        inputs = load_node(identifier).inputs
        builder.training.mace.train.mace_config = inputs["mace"]["train"]["mace_config"]
    for trainings in outputs["training"]:
        if trainings.startswith("mace"):
            if "model_stage2_ase" in outputs["training"][trainings]:
                models_ase[trainings] = outputs["training"][trainings]["model_stage2_ase"]
            elif "model_stage1_ase" in outputs["training"][trainings]:
                models_ase[trainings] = outputs["training"][trainings]["model_stage1_ase"]
            if "model_stage2_lammps" in outputs["training"][trainings]:
                models_lammps[trainings] = outputs["training"][trainings]["model_stage2_lammps"]
            elif "model_stage1_lammps" in outputs["training"][trainings]:
                models_lammps[trainings] = outputs["training"][trainings]["model_stage1_lammps"]
            if "checkpoints" in outputs["training"][trainings]:
                models_checkpoints[trainings] = outputs["training"][trainings]["checkpoints"]
        if trainings.startswith("meta"):
            if "model_stage2_lammps" in outputs["training"][trainings]:
                models_lammps[trainings] = outputs["training"][trainings]["model_stage2_lammps"]
            if "checkpoints" in outputs["training"][trainings]:
                models_checkpoints[trainings] = outputs["training"][trainings]["checkpoints"]

    builder.models_ase = models_ase
    builder.models_lammps = models_lammps
    builder.training.checkpoints = models_checkpoints

    return builder


def models_from_aiidatrainspotwc(builder, identifier):
    """Return a builder populated with potentials and checkpoints from previous training.

    Args:
        builder: Builder to be populated.
        identifier: Identifier of the training workchain (pk or uuid).

    Returns:
        builder: Builder populated with dataset, models_ase, models_lammps configuration parameters.
    """
    outputs = load_node(identifier).outputs
    models_ase = {}
    models_lammps = {}
    checkpoints = {}

    for model_ase in outputs["models_ase"]:
        models_ase[model_ase] = outputs["models_ase"][model_ase]
    for model_lammps in outputs["models_lammps"]:
        models_lammps[model_lammps] = outputs["models_lammps"][model_lammps]
    for checkpoint in outputs["checkpoints"]:
        checkpoints[checkpoint] = outputs["checkpoints"][checkpoint]

    builder.dataset = outputs["dataset"]
    builder.models_ase = models_ase
    builder.models_lammps = models_lammps
    builder.training.checkpoints = checkpoints

    return builder


def resume_trainspotwc(builder, identifier):
    """Populate a builder to resume from a previous TrainsPotWorkChain, whether it finished or was interrupted.

    Unlike `models_from_aiidatrainspotwc`, this only reuses whatever outputs the previous run
    actually produced before finishing or failing -- a run that stopped early (e.g. before training
    completed, or before exploration/evaluation ran) won't have all of them. For each stage whose
    result is found, the corresponding do_* flag is set to skip it for the first loop iteration,
    since its result is already reflected in the resumed state.

    Args:
        builder: Builder to be populated (already created via TrainsPotWorkChain.get_builder(...)).
        identifier: Identifier of the previous TrainsPotWorkChain (pk or uuid).

    Returns:
        builder: Builder populated with whatever dataset/potentials/checkpoints/explored_dataset the
        previous run produced, with do_dataset_augmentation/do_ab_initio_labelling/do_training/
        do_exploration set to skip stages already reflected in that state.
    """
    outputs = load_node(identifier).outputs

    if "dataset" in outputs:
        builder.dataset = outputs["dataset"]

    # The resumed dataset already reflects whatever augmentation happened; redoing it would add
    # fresh, unlabelled structures on top of a dataset that may already have been trained on.
    builder.do_dataset_augmentation = Bool(False)

    have_training = "models_ase" in outputs and "models_lammps" in outputs
    if have_training:
        builder.models_ase = {key: outputs["models_ase"][key] for key in outputs["models_ase"]}
        builder.models_lammps = {key: outputs["models_lammps"][key] for key in outputs["models_lammps"]}
        if "models_lammps_mliap" in outputs:
            builder.models_lammps_mliap = {
                key: outputs["models_lammps_mliap"][key] for key in outputs["models_lammps_mliap"]
            }
        if "checkpoints" in outputs:
            builder.training.checkpoints = {key: outputs["checkpoints"][key] for key in outputs["checkpoints"]}
    # Training only runs after ab initio labelling in the same iteration, so if it succeeded,
    # labelling is already reflected in the resumed dataset too. Explicitly set both ways (not just
    # to skip) so resuming always restarts from the first missing stage, regardless of any prior
    # state already on the builder.
    builder.do_ab_initio_labelling = Bool(not have_training)
    builder.do_training = Bool(not have_training)

    have_explored_dataset = "explored_dataset" in outputs and len(outputs["explored_dataset"]) > 0
    if have_explored_dataset:
        builder.explored_dataset = outputs["explored_dataset"]
    builder.do_exploration = Bool(not have_explored_dataset)

    return builder
