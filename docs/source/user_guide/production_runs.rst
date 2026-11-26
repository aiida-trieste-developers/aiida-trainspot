.. _production-runs:

===============
Production runs
===============

The trial run in :ref:`get-started` checks that everything works. A production run asks more of the
setup: the scheduler settings have to fit the real cost of each calculation, the training engine
has to be chosen together with the way LAMMPS will use its potentials, the stages are larger, and
the run often has to be continued over several submissions. This page goes through these points
and ends with how to inspect the results.

.. _production-scheduler:

Cluster and scheduler settings
==============================

Every calculation of the workflow is submitted to the cluster separately, and each needs its own
resources, wall time and memory. These are AiiDA ``metadata.options``, set on the namespace of the
builder that runs the calculation:

.. list-table::
   :header-rows: 1
   :widths: 55 45

   * - Namespace
     - Runs
   * - ``ab_initio_labelling.quantumespresso.pw``
     - Quantum ESPRESSO
   * - ``training.mace.train`` or ``training.meta.train``
     - training and post-processing
   * - ``exploration.md.lammps``
     - LAMMPS
   * - ``committee_evaluation``
     - committee evaluation

On a SLURM cluster the account, partition, quality of service and GPU request go in the same place.
The example below is for Leonardo (Booster partition) at CINECA, where all of them are required;
other clusters have their own account, partition and QoS names. For brevity the function below,
the same as in the first-run script, applies one set of settings to every calculation; nothing
prevents passing different ones per code, which is what `examples/graphene/run_atp.py
<https://github.com/aiida-trieste-developers/aiida-trainspot/blob/main/examples/graphene/run_atp.py>`_
does with one block of settings per code. The matching ``computer`` and ``code`` definitions are in
`examples/setup_codes
<https://github.com/aiida-trieste-developers/aiida-trainspot/tree/main/examples/setup_codes>`_.

.. code-block:: python

    HPC_account = "<account>"

    LEONARDO = {
        "account": HPC_account,
        "queue_name": "boost_usr_prod",
        "qos": "normal",
        "custom_scheduler_commands": "#SBATCH --gres=gpu:1",
        "import_sys_environment": False,
    }


    def set_scheduler(options, wallclock, mem_gb, cpus=8):
        """Apply the scheduler settings of one calculation."""
        options.resources = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
            "num_cores_per_mpiproc": cpus,
        }
        options.max_wallclock_seconds = wallclock
        options.max_memory_kb = mem_gb * 1024 * 1024
        for key, value in LEONARDO.items():
            setattr(options, key, value)

The attributes set above are standard AiiDA ``CalcJob`` options: ``account``, ``queue_name`` (the SLURM
partition), ``qos``, ``custom_scheduler_commands`` (extra lines added to the SLURM script),
``max_wallclock_seconds``, ``max_memory_kb``, ``resources``, ``withmpi``, ``import_sys_environment``
and ``prepend_text``.

.. _production-engine:

Choosing the training engine
============================

The workflow trains its potentials with one of two engines, selected by ``training_engine``:
``"MACE"`` (default) or ``"META"`` (metatrain). The corresponding AiiDA plugin has to be installed
(see :doc:`installation`). The choice matters twice: it decides which inputs are needed for
training, and in which format LAMMPS reads the trained potentials, that is, which ``pair_style`` is
used in the exploration. The pair style is set with ``exploration.potential_pair_style``, and the
LAMMPS executable must have been built with the matching support:

.. list-table::
   :header-rows: 1
   :widths: 15 35 50

   * - ``training_engine``
     - ``potential_pair_style``
     - Requires in LAMMPS
   * - ``MACE``
     - ``"mace no_domain_decomposition"`` (default)
     - the MACE extension
   * - ``MACE``
     - ``"mliap"`` (written as ``pair_style mliap unified``)
     - the ML-IAP and PYTHON packages
   * - ``META``
     - ``"metatomic"``
     - ``lammps-metatomic``

If the pair style is not one the engine can produce, it is replaced by the engine's default and the
replacement is written in the workchain report. With ``META``, leaving ``potential_pair_style``
unset therefore gives ``metatomic``; setting it explicitly is clearer.

.. code-block:: python

    from aiida.orm import Str

    # MACE, mliap format
    builder.exploration.potential_pair_style = Str("mliap")

    # metatrain
    builder.training_engine = Str("META")
    builder.exploration.potential_pair_style = Str("metatomic")

The training itself is configured with a dictionary in the native format of the engine: ``training.mace.train.mace_config`` (see
`examples/graphene/mace_config.yml
<https://github.com/aiida-trieste-developers/aiida-trainspot/blob/main/examples/graphene/mace_config.yml>`_)
or ``training.meta.train.meta_config`` (see `examples/graphene/meta_config.yml
<https://github.com/aiida-trieste-developers/aiida-trainspot/blob/main/examples/graphene/meta_config.yml>`_).
A complete metatrain run is `examples/graphene/run_atp_meta.py
<https://github.com/aiida-trieste-developers/aiida-trainspot/blob/main/examples/graphene/run_atp_meta.py>`_.

.. _production-builder-args:

Arguments of ``get_builder``
============================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Argument
     - Meaning
   * - ``dataset``
     - ``PESData`` with the starting structures. Required.
   * - ``abinitiolabelling_code``
     - Quantum ESPRESSO ``pw.x`` code. Required.
   * - ``md_code``
     - LAMMPS code. Required.
   * - ``training_engine``
     - ``"MACE"`` or ``"META"``. Default: ``"MACE"``.
   * - ``abinitiolabelling_protocol``
     - ``"fast"``, ``"balanced"`` or ``"stringent"``, the ``PwBaseWorkChain`` protocols. Default:
       ``"stringent"``. ``fast`` is for tests, ``stringent`` for results to keep.
   * - ``pseudo_family``
     - Label of an installed pseudopotential family, for example ``"SSSP/1.3/PBE/efficiency"``. If
       omitted, the family of the chosen protocol is used.
   * - ``md_protocol``
     - ``None`` (default) or ``"vdw_d2"``, which adds a DFT-D2 dispersion correction to the
       potential during exploration.
   * - ``demo``
     - ``True`` lowers the dataset augmentation to toy size. Default: ``False``.

The arguments that select protocols are the ones to decide on first for a production run. The
default ab initio protocol is the most accurate one, and the ``fast`` protocol of the first run is
meant for tests only. ``get_builder`` also sets one default MD run (300 K, ``nvt``, 50 steps), to be replaced
for production; see :ref:`stage-explore`.

A longer configuration
======================

The script below puts these pieces together for a longer run. It reuses ``set_scheduler`` from
above, and, compared with the first-run script, it uses the default (``stringent``) ab initio
protocol, the DFT-D2 correction in the MD, longer MD runs at two temperatures, a larger committee
and explicit selection thresholds. It trains four potentials with MACE, explores two
temperatures with ``npt`` dynamics, and keeps the default augmentation.

.. code-block:: python

    import yaml

    from aiida import load_profile
    from aiida.engine import submit
    from aiida.orm import Bool, Dict, Float, Int, Str, load_code, load_computer
    from ase.io import read

    from aiida_trainspot.data.pesdata import PESData
    from aiida_trainspot.utils.generate_config import generate_lammps_md_config
    from aiida_trainspot.workflows.trainspot import TrainsPotWorkChain

    load_profile()

    dataset = PESData([read("structure.xyz")])

    builder = TrainsPotWorkChain.get_builder(
        dataset=dataset,
        abinitiolabelling_code=load_code("pw@cluster"),
        md_code=load_code("lammps@cluster"),
        md_protocol="vdw_d2",
        pseudo_family="SSSP/1.3/PBE/efficiency",  # protocol: stringent (default)
    )
    builder.max_loops = Int(8)

    # Selection
    builder.thr_energy = Float(2e-3)
    builder.thr_forces = Float(5e-2)
    builder.thr_stress = Float(1e-2)
    builder.max_selected_frames = Int(500)

    # Labelling
    builder.ab_initio_labelling.group_label = Str("my_system")
    set_scheduler(builder.ab_initio_labelling.quantumespresso.pw.metadata.options, 4 * 3600, 70)

    # Training
    with open("mace_config.yml") as handle:
        builder.training.mace.train.mace_config = Dict(yaml.safe_load(handle))
    builder.training.num_potentials = Int(4)
    builder.training.mace.train.code = load_code("mace_train@cluster")
    builder.training.mace.train.preprocess_code = load_code("mace_preprocess@cluster")
    builder.training.mace.train.postprocess_code = load_code("mace_postprocess@cluster")
    builder.training.mace.train.do_preprocess = Bool(True)
    set_scheduler(builder.training.mace.train.metadata.options, 24 * 3600, 30)

    # Exploration
    timestep = 0.001
    builder.exploration.params_list = generate_lammps_md_config(
        temperatures=[300, 600],
        pressures=[0],
        steps=[5000],
        styles=["npt"],
        dt=timestep,
    )
    builder.exploration.parameters = Dict({"control": {"timestep": timestep}})
    builder.exploration.sampling_time = Float(0.05)
    builder.num_random_structures_lammps = Int(20)
    set_scheduler(builder.exploration.md.lammps.metadata.options, 3600, 30)

    # Committee evaluation
    builder.committee_evaluation.code = load_code("committee_evaluation_portable")
    builder.committee_evaluation.metadata.computer = load_computer("cluster")
    set_scheduler(builder.committee_evaluation.metadata.options, 3600, 30)

    node = submit(builder)
    print(f"Submitted TrainsPotWorkChain with PK = {node.pk}")

The example script ``examples/graphene/run_atp.py`` also uses a few options that depend on the
cluster and the codes:

- ``builder.training.mace.train.metadata.options.prepend_text`` defines a ``mace_run_train`` shell
  function that launches the training through ``srun``, for training on multiple GPUs.
- ``builder.exploration.md.lammps.settings = Dict({"additional_cmdline_params": ["-k", "on", "g",
  "1", "-sf", "kk"]})`` runs LAMMPS with the Kokkos GPU package.
- ``builder.ab_initio_labelling.quantumespresso.pw.metadata.options.withmpi = True`` runs
  ``pw.x`` under ``mpirun``.

.. _production-resume:

Resuming a run
==============

Production runs are long, and a run can stop because of a failed job or an exhausted allocation,
or simply because more loops are wanted once the first ones are examined. Instead of starting over,
``get_builder_resume`` creates a builder from a previous run:

.. code-block:: python

    builder = TrainsPotWorkChain.get_builder_resume(1234)  # pk or uuid of the previous run
    builder.max_loops = Int(4)
    # ... training, exploration, evaluation and scheduler settings, as above ...
    node = submit(builder)

The dataset, and the potentials, checkpoints and explored dataset if the previous run produced
them, are taken from its outputs. The stages already reflected in them are skipped in the first
loop: augmentation is not repeated, and labelling and training are skipped if potentials exist. The
Quantum ESPRESSO and LAMMPS codes are taken from the previous run unless ``abinitiolabelling_code``
or ``md_code`` is passed. Other keyword arguments are forwarded to ``get_builder``.

The rest of the builder (training config and codes, exploration parameters, evaluation code,
scheduler options, thresholds) is not copied from the previous run. Set it again, for instance with
a function shared by the first submission and the resumed ones.

.. _production-results:

Looking at the results
======================

.. code-block:: python

    from aiida.orm import load_node
    from aiida_trainspot.utils.plotting import plot_error_calibration, plot_parity

    node = load_node(1234)  # pk of the TrainsPotWorkChain

    plot_parity(node)
    plot_error_calibration(node)

    plot_parity(node, cycles=[1, 3], sets=["test"], save_path="parity.png")

Once the run has produced at least one committee evaluation, the plotting functions of
``aiida_trainspot.utils.plotting`` summarise how well the committee reproduces the reference data.
``plot_parity`` draws, for each completed committee evaluation, predicted against DFT energies,
forces and stresses, shows a table of RMSEs and, with more than one loop, the RMSE across loops.
``detailed=True`` adds the RMSE of each potential to the table.

``plot_error_calibration`` draws the committee deviation against the actual error. The slope of
the linear fit is the factor that scales ``thr_energy``, ``thr_forces`` and ``thr_stress``.

Both functions take ``cycles`` (1-based loop indices; default all completed loops), ``sets`` (a
subset of ``"training"``, ``"validation"`` and ``"test"``), ``show`` and ``save_path``. In a
notebook the figures are displayed inline. A script with these calls is `examples/plot_results.py
<https://github.com/aiida-trieste-developers/aiida-trainspot/blob/main/examples/plot_results.py>`_.

The outputs of the workchain (``dataset``, ``models_lammps``, ``models_ase``, ``RMSE``, ...) are
listed in :ref:`loop-stages`.
