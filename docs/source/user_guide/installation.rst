.. _installation:

============
Installation
============

AiiDA-TrainsPot runs on a machine you control: a workstation, a login node, a small server. It never
runs the scientific codes itself. It connects over SSH to one or more remote computers, submits
Quantum ESPRESSO, LAMMPS and training jobs to their scheduler, and retrieves the results when they
finish.

That split decides where each piece goes. The Python packages below are installed on the local
machine. The Quantum ESPRESSO, LAMMPS and training-engine executables are installed on the remote
machine that runs the calculations.

Prerequisites
=============

On the local machine, a working |aiida-core|_ installation with a profile configured and the daemon
running.

On the remote machine:

- Quantum ESPRESSO, at least the ``pw.x`` executable, for ab initio labelling. See the `installation
  instructions <https://www.quantum-espresso.org/Doc/user_guide/node7.html>`_.
- LAMMPS (`official installation guide <https://docs.lammps.org/Install.html>`_), built with support
  for the potentials you plan to explore with: the `MACE extension
  <https://mace-docs.readthedocs.io/en/latest/guide/lammps.html>`_ for ``pair_style mace``, the
  `ML-IAP and PYTHON packages <https://mace-docs.readthedocs.io/en/latest/guide/lammps_mliap.html>`_
  for ``pair_style mliap unified``, or `lammps-metatomic
  <https://docs.metatensor.org/metatomic/latest/engines/lammps.html>`_ for ``pair_style metatomic``
  with metatrain models.
- At least one training engine, `MACE <https://github.com/ACEsuit/mace>`_ or `metatrain
  <https://docs.metatensor.org/metatrain/latest/getting-started/quickstart.html>`_, each preferably
  in its own Python environment.

A GPU cluster with SLURM, such as Leonardo at CINECA, is strongly recommended for anything beyond
toy examples.

Installing AiiDA-TrainsPot and its dependencies
===============================================

In order to install AiiDA-TrainsPot, you need to clone the repository and install it on your local machine.

.. code-block:: bash

   git clone git@github.com:aiida-trieste-developers/aiida-trains-pot.git
   cd aiida-trains-pot
   pip install .

.. warning::
   The current release of ``aiida-lammps`` available on PyPI and automatically installed by the previous command
   does not support the ``mliap`` and ``metatomic`` LAMMPS pair styles used by AiiDA-TrainsPot.

   You should install the version of ``aiida-lammps`` that supports those pair styles, which is
   available on `our fork <https://github.com/aiida-trieste-developers/aiida-lammps>`_:

   .. code-block:: bash

      pip install --force-reinstall \
        "aiida-lammps @ git+https://github.com/aiida-trieste-developers/aiida-lammps@2ea56006bae7f57fc703bf2ef1f8393c1e63fbbe"

Finally, install the AiiDA plugin for each training engine you intend to use. These are not yet
on PyPI, so install them straight from their repositories:

.. code-block:: bash

   pip install git+https://github.com/aiida-trieste-developers/aiida-mace.git        # MACE
   pip install git+https://github.com/aiida-trieste-developers/aiida-metatrain.git   # metatrain

Install only the engines you intend to train with. The ``training_engine`` input of
``TrainsPotWorkChain`` selects among those available.

Pseudopotentials
================

The ab initio labelling takes its pseudopotentials from a family installed in the AiiDA profile with
`aiida-pseudo <https://aiida-pseudo.readthedocs.io/>`_, which is installed together with
``aiida-quantumespresso``. The examples use the SSSP 1.3 PBE efficiency family:

.. code-block:: bash

   aiida-pseudo install sssp -v 1.3 -x PBE -p efficiency

Computers and codes
===================

In order to interact with the executables installed on the remote machine, AiiDA asks you to
register a ``computer`` for the remote machine and a ``code`` for each executable it will run there:
Quantum ESPRESSO, LAMMPS, and one per training-engine stage.
A full set of working setup files for Leonardo at CINECA is in `examples/setup_codes
<https://github.com/aiida-trieste-developers/aiida-trains-pot/tree/main/examples/setup_codes>`_ and
can be used as a template for other clusters.

A detailed guide to registering computers and codes, and to setting up the SSH connection, can be
found on AiiDA's website: `how-to on connecting to a remote computer
<https://aiida.readthedocs.io/projects/aiida-core/en/stable/howto/ssh.html>`_.

Committee evaluation
====================

Committee evaluation is the one code you do not install on the remote machine. It is an AiiDA
``PortableCode``: its files live in the AiiDA repository and are uploaded with each calculation, so
there is nothing to build on the cluster. It does run in the Python environment of the training
engine on the remote machine, since it loads the trained potentials. Install it with:

.. code-block:: bash

   portable_codes_installation

The command asks for a label for the code (``committee_evaluation_portable`` is the one used in the
examples) and for a prepend command, run on the remote machine before the evaluation: it has to
activate the environment of the training engine, for example
``source /path/to/mace_env/bin/activate``. Install one such code per training engine you use, and
give its label to ``committee_evaluation.code`` when launching a run.

.. |aiida-core| replace:: ``aiida-core``
.. _aiida-core: https://aiida.readthedocs.io/projects/aiida-core/en/latest/intro/get_started.html
