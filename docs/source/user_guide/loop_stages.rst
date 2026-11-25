.. _loop-stages:

========================
The active-learning loop
========================

``TrainsPotWorkChain`` implements the active-learning loop as a sequence of stages. A dataset is
first built from the input structures (augment). The loop then labels the structures that do not
yet have reference data (label), trains a committee of potentials on them (train), runs molecular
dynamics with the new potentials to find configurations the training set does not cover (explore),
and measures how much the committee disagrees on those configurations (evaluate). The most
uncertain ones are added to the dataset, and the next iteration starts from there.

.. code-block:: text

   augment -> [ label -> train -> explore -> evaluate ] x max_loops

Each stage has a namespace on the builder named after it, and every input has a default, so a
builder from ``TrainsPotWorkChain.get_builder()`` runs as is (see :ref:`get-started`). This page
describes what each stage does and the settings that are worth changing.

Loop control
============

Two kinds of inputs act on the loop as a whole. ``max_loops`` is the maximum number of iterations
of the label/train/explore/evaluate cycle (default ``10``). Augmentation is not part of the cycle:
it runs once, before the first iteration.

The flags ``do_dataset_augmentation``, ``do_ab_initio_labelling``, ``do_training`` and
``do_exploration`` (all ``True`` by default) switch a stage off for the first iteration. After
that, labelling, training and exploration are always on and augmentation is off. Switching stages
off is how a run starts from an existing dataset or from existing potentials; see
:ref:`production-resume`. The committee evaluation has no flag: it runs whenever an explored
dataset is available.

.. _stage-augment:

Augment
=======

A handful of input structures is not enough to train a potential that can be used in MD. The first
stage, ``builder.dataset_augmentation``, therefore generates a much larger and more varied dataset
from them: distorted copies, small clusters, slabs, larger cells and so on. Each method is switched
by a ``do_*`` flag and has its own parameters, listed in the table.

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Flag (default)
     - Generates
     - Main parameters (default)
   * - ``do_input`` (``True``)
     - the input structures themselves
     -
   * - ``do_isolated`` (``True``)
     - isolated atoms of each species
     -
   * - ``do_rattle_strain_defects`` (``True``)
     - rattled, strained and defective copies
     - ``rsd.params.n_configs`` (50), ``rattle_fraction`` (0.3), ``max_compressive_strain`` (0.2),
       ``max_tensile_strain`` (0.6), ``frac_vacancies`` (0.3), ``vacancies_per_config`` (2)
   * - ``do_clusters`` (``True``)
     - small clusters
     - ``clusters.n_clusters`` (20), ``max_atoms`` (10), ``interatomic_distance`` (1.5)
   * - ``do_slabs`` (``True``)
     - slabs
     - ``slabs.miller_indices`` (``[[1, 1, 1], [1, 1, 0], [1, 0, 0]]``), ``min_thickness`` (10),
       ``max_atoms`` (450)
   * - ``do_replication`` (``True``)
     - replicas of the cell
     - ``replicate.min_dist`` (18), ``replicate.max_atoms`` (450)
   * - ``do_substitution`` (``True``)
     - structures with swapped species
     - ``substitution.switches_fraction`` (0.2), ``structures_fraction`` (0.2)
   * - ``do_alloys`` (``True``)
     - alloy structures
     - ``alloys.alloy_species`` (no default), ``fixed_species``, ``num_structures`` (100),
       ``fractions``
   * - ``do_check_vacuum`` (``True``)
     - not a generator: enlarges the vacuum along non-periodic directions
     - ``vacuum`` (15)

Alloy generation is skipped, with a message in the report, unless ``alloys.alloy_species`` is set.
As an example, to generate more distorted configurations, drop the slabs and generate alloys of B
and N:

.. code-block:: python

    from aiida.orm import Bool, Int, List

    builder.dataset_augmentation.rsd.params.n_configs = Int(80)
    builder.dataset_augmentation.do_slabs = Bool(False)
    builder.dataset_augmentation.alloys.alloy_species = List(["B", "N"])

The defaults target a production dataset and can take a long time on a small system.
``get_builder(..., demo=True)`` lowers the sizes for a
first trial: slabs and alloys are switched off, and ``rsd.params.n_configs``,
``clusters.n_clusters``, ``clusters.max_atoms`` and ``replicate.max_atoms`` are set to 3, 3, 6 and 24.

Label
=====

The structures produced by the augmentation, and later those selected by the committee, have no
energies, forces or stresses yet. ``builder.ab_initio_labelling`` computes them with Quantum
ESPRESSO, running one calculation for each unlabelled structure of the dataset. ``get_builder``
fills ``ab_initio_labelling.quantumespresso`` from ``abinitiolabelling_protocol`` and
``pseudo_family``. It is a ``PwBaseWorkChain`` builder, so any of its inputs can be changed as for
any other Quantum ESPRESSO calculation, for example the smearing:

.. code-block:: python

    from aiida.orm import Dict

    parameters = builder.ab_initio_labelling.quantumespresso.pw.parameters.get_dict()
    parameters.setdefault("SYSTEM", {})["degauss"] = 0.0125
    builder.ab_initio_labelling.quantumespresso.pw.parameters = Dict(parameters)

Two other inputs are ``group_label`` (calculations are added to this group; a group named
``ab_initio_labelling_<uuid>`` is created if it is not given) and ``batch_size`` (structures
labelled per batch, default ``1000``). The calculations are run with ``tstress`` and ``tprnfor``
enabled.

Train
=====

``builder.training`` trains ``num_potentials`` independent potentials on the labelled dataset. They form the committee whose disagreement drives
the selection of new structures, so at least two are needed. Before training, the labelled dataset
is split into training, validation and test sets.

``training.num_potentials``
   Default ``2``.

``training.non_training_fraction``
   Fraction of the dataset kept out of training and split between validation and test sets. Default
   ``0.2``. Input structures, isolated atoms and single-atom configurations always go to the
   training set.

The inputs of the training engine itself sit under ``training.mace`` or ``training.meta``, matching
``training_engine``; the one for the other engine is left empty. For MACE:

.. code-block:: python

    builder.training.num_potentials = Int(4)
    builder.training.mace.train.mace_config = Dict(mace_config)
    builder.training.mace.train.code = mace_train_code
    builder.training.mace.train.postprocess_code = mace_postprocess_code
    builder.training.mace.train.preprocess_code = mace_preprocess_code
    builder.training.mace.train.do_preprocess = Bool(True)

``postprocess_code`` is required for MACE. ``preprocess_code`` is read only if ``do_preprocess`` is
``True`` (default ``False``). For metatrain the config is ``training.meta.train.meta_config`` and
there is no post-processing code. The choice of engine is described in :ref:`production-engine`.

.. _stage-explore:

Explore
=======

The training set only covers the configurations it contains, so the next question is where the
potentials fail. ``builder.exploration`` runs LAMMPS molecular dynamics with one of the freshly
trained potentials, starting from structures of the dataset, and samples frames from the
trajectories; these are the candidates for labelling. The inputs below control what is simulated
and how it is sampled.

``params_list``
   List of MD runs. ``get_builder`` sets a single one: 300 K, zero pressure, ``nvt``, 50 steps of
   0.001. ``generate_lammps_md_config`` builds a list from lists of temperatures, pressures,
   step counts and integration styles; every combination becomes one run:

   .. code-block:: python

       from aiida_trainspot.utils.generate_config import generate_lammps_md_config

       timestep = 0.001
       builder.exploration.params_list = generate_lammps_md_config(
           temperatures=[300, 600],
           pressures=[0],
           steps=[2000],
           styles=["npt"],
           dt=timestep,
       )
       builder.exploration.parameters = Dict({"control": {"timestep": timestep}})

   The same ``dt`` has to be passed to the function and set as ``control.timestep``: the function
   uses it to set the thermostat and barostat damping times (100 and 1000 timesteps), and
   ``exploration.parameters["control"]["timestep"]`` is required.

``sampling_time``, ``thermalization_time``
   Interval between extracted frames (default ``1.0``) and initial time discarded (default
   ``0.0``), in LAMMPS time units. Their sum must not exceed the shortest run,
   ``min(steps) * timestep``. ``get_builder`` sets ``sampling_time`` to ``0.01``,
   a fifth of its default run.

``potential_pair_style``
   The LAMMPS ``pair_style`` of the trained potentials. Default ``"mace no_domain_decomposition"``.
   A value the training engine cannot produce is replaced by that engine's default, and the change
   is written in the report. See :ref:`production-engine`.

``protocol``
   ``None`` or ``"vdw_d2"``, set by the ``md_protocol`` argument of ``get_builder``. With
   ``"vdw_d2"`` the potential is combined with a DFT-D2 dispersion correction through
   ``pair_style hybrid/overlay``.

``check_vacuum``
   Default ``True``. Enlarges the vacuum along non-periodic directions of the extracted frames.

Which structures the MD starts from is chosen at the top level of the builder:
``random_input_structures_lammps`` (default ``True``) and
``num_random_structures_lammps`` (default ``20``) select how many structures of the dataset are
used as MD starting points, skipping single atoms. A fixed set can be given instead with
``lammps_input_structures``, a ``PESData`` node, and ``random_input_structures_lammps = Bool(False)``.

LAMMPS settings can be passed through ``builder.exploration.md.lammps.settings``, for example
``additional_cmdline_params`` for GPU options, and the structure and thermo output parameters
through ``builder.exploration.parameters``.

Evaluate
========

The last stage decides which of the explored frames are worth labelling.
``builder.committee_evaluation`` evaluates the explored frames, and the labelled dataset, with
every potential of the committee. The deviation among the members is a measure of how uncertain the
committee is on a frame. Frames whose deviation is above the thresholds are added to the dataset
and labelled in the next loop.

.. code-block:: python

    from aiida.orm import Float, Int

    builder.thr_energy = Float(2e-3)
    builder.thr_forces = Float(5e-2)
    builder.thr_stress = Float(1e-2)
    builder.max_selected_frames = Int(500)

``thr_energy``, ``thr_forces``, ``thr_stress``
   Defaults ``0.001``, ``0.1`` and ``0.001``. A frame is selected if any of its energy, forces or
   stress deviations exceeds the corresponding threshold. The thresholds are expressed in units of
   the error: at each loop they are multiplied by the slope of a linear fit, through the origin,
   of the committee deviation against the RMSE on the labelled dataset (the calibration shown by
   ``plot_error_calibration``).

``max_selected_frames``
   Maximum number of frames selected per loop. Default ``1000``. If more frames pass the
   thresholds, a random subset is kept.

The committee evaluation is run as a ``PortableCode`` with no computer of its own, so
``committee_evaluation.metadata.computer`` has to be set together with ``committee_evaluation.code``.

Outputs
=======

When the workflow finishes, its main results are available as outputs of the process node.

``dataset``
   The final dataset: labelled structures plus the structures selected in the last loop.

``models_lammps``, ``models_ase``
   The last committee, compiled for LAMMPS and for ASE. For MACE, ``models_lammps_mliap`` is also
   present when the post-processing step produced the ``mliap`` format.

``checkpoints``
   Last checkpoints of the trained potentials.

``RMSE``
   RMSE on the labelled dataset for each loop.

``explored_dataset``
   Frames sampled in the last successful exploration.
