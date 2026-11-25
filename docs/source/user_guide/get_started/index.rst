.. _get-started:

===========
Get started
===========

This page runs a first, small active-learning loop on graphene. Starting from a single graphene
cell, the workflow builds a larger set of structures by rattling, straining and cutting it, and
computes their energies, forces and stresses with Quantum ESPRESSO. It then trains a committee of
MACE potentials on these labelled structures and uses them to run short molecular dynamics (MD)
simulations with LAMMPS. Where the members of the committee disagree on a frame of those
trajectories, the potentials are unreliable, so those frames are labelled with Quantum ESPRESSO,
added to the training set, and the cycle starts again. The aim of this run is not a useful potential
but a check that the installation, the codes and the scheduler settings work together, and a first
look at how the workflow is driven.

The whole run is one Python script, `examples/graphene/get_started.py
<https://github.com/aiida-trieste-developers/aiida-trains-pot/blob/main/examples/graphene/get_started.py>`_,
which reads ``gr8x8.xyz`` and ``mace_config.yml`` from its own directory. After filling in the
placeholders marked ``<...>`` and the cluster settings it runs as is. The sections below go through
it in order.

You need :ref:`AiiDA-TrainsPot installed <installation>`, an AiiDA profile with the daemon running,
and a registered code for each of Quantum ESPRESSO (``pw.x``), LAMMPS, MACE training, MACE
post-processing and committee evaluation, as described in the installation page.

Codes and cluster settings
==========================

AiiDA stores everything it knows (codes, computers, calculations, results) in a database selected by
a *profile*, so the script starts by loading it. Each executable you registered is an AiiDA *code*,
identified by a label of the form ``<code>@<computer>``, where the *computer* is the remote machine
it runs on. The labels below are placeholders for your own. The committee evaluation code is a
``PortableCode``: its files are stored in AiiDA and uploaded with each calculation, so it is not
tied to a computer and has to be given one explicitly later.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- profile and codes ---
   :end-before: # --- scheduler settings ---

Every calculation is then submitted to the cluster's scheduler, which will refuse a job without an
account, a partition, a quality of service (QoS), and, on a GPU machine, a GPU request, and which
needs a wall time and a memory limit. In AiiDA these are the ``metadata.options`` of each
calculation. They are the same for every code here, so the script defines them once and applies them
with a small function. The values are those of Leonardo (Booster) at CINECA and have to be replaced
with the ones of your cluster; :ref:`production-scheduler` explains them further.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- scheduler settings ---
   :end-before: # --- dataset ---

Dataset and builder
===================

The starting point is a ``PESData`` node, the dataset type of the workflow. It is created from a
list of ASE structures, here the one read from ``gr8x8.xyz``.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- dataset ---
   :end-before: # --- builder ---

AiiDA workflows are configured through a *builder*, an object whose attributes are the inputs of the
workflow, organised in namespaces. ``TrainsPotWorkChain.get_builder()`` returns one with the ab
initio labelling and the exploration already filled in: the Quantum ESPRESSO inputs come from the
protocol (``fast`` here) and the pseudopotential family, and a default MD run is set. Training and
committee evaluation are left to the user. ``demo=True`` sets small, reasonable values for a test
run; the details are in :ref:`loop-stages`. ``max_loops`` is the maximum number of iterations of
the loop.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- builder ---
   :end-before: # --- training ---

Training and scheduler settings
===============================

The default training engine is MACE. It needs its configuration, a dictionary read here from
``mace_config.yml``, and two codes: the one that trains and the one that converts the trained model
for use in LAMMPS. The ``prepend_text`` option adds lines to the job script before the executable
runs; the one used here, taken from ``examples/graphene/run_atp.py``, makes the training run through
``srun``. By default two potentials are trained, which form the committee.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- training ---
   :end-before: # --- scheduler per code ---

Each calculation that runs on the cluster has its own ``metadata.options``, reached through the
corresponding namespace of the builder. To keep this first script short, the same settings are
applied to all of them, Quantum ESPRESSO (run under MPI, hence ``withmpi``), MACE training and
LAMMPS, changing only wall time and memory; in a real run each code can get its own partition,
resources or GPU request.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- scheduler per code ---
   :end-before: # --- committee evaluation ---

Committee evaluation
====================

After each exploration, the committee evaluation runs all the potentials on the sampled frames and
measures how much they disagree. As it is a ``PortableCode``, it needs the computer it will run on,
besides the same scheduler settings.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- committee evaluation ---
   :end-before: # --- submit ---

Submit and launch
=================

Submitting hands the workflow to the AiiDA daemon, a background process that runs the workflow and
talks to the cluster, so the script returns immediately and the run continues without it.

.. literalinclude:: ../../../../examples/graphene/get_started.py
   :language: python
   :start-after: # --- submit ---

The script is launched with ``verdi run get_started.py``, which loads the profile and runs it.
Plain ``python get_started.py`` works as well, because the script calls ``load_profile()``. In both
cases the daemon has to be running (``verdi daemon status``).

Following the run
=================

The workflow and every calculation it spawns are AiiDA processes, which can be inspected from the
command line using the PK printed by the script.

.. code-block:: bash

    verdi process list -a -p1       # recent processes and their state
    verdi process status <pk>       # tree of sub-workchains and calculations
    verdi process report <pk>       # log of the workflow

``status`` shows which stage the run is in, and ``report`` lists, for each loop, how many frames
were selected for labelling.

Results
=======

Once at least one committee evaluation has finished, the results can be plotted from a Python
session or a notebook. ``plot_parity`` compares the predicted energies, forces and stresses with the
Quantum ESPRESSO values for each loop, and shows how the errors evolve from one loop to the next.

.. code-block:: python

    from aiida.orm import load_node
    from aiida_trainspot.utils.plotting import plot_parity

    plot_parity(load_node(1234))  # pk of the TrainsPotWorkChain

Next
====

:doc:`../loop_stages` describes what each stage does and which settings are worth changing.
:doc:`../production_runs` covers cluster settings, the choice of training engine, longer runs,
resuming and further plots.
