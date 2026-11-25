Workchains
==========

.. toctree::
   :maxdepth: 3

   trains_pot_wc
   augmentation_wc
   abinitio_labelling_wc
   training_wc
   exploration_wc

.. currentmodule:: aiida_trainspot


Below are the primary workchains available in the module:



**Main TrainsPot WorkChain**
  .. autoclass:: aiida_trainspot.workflows.trainspot.TrainsPotWorkChain
     :members:
     :exclude-members: DEFAULT_RATTLE_rattle_fraction

**Dataset Augmentation WorkChain**
  .. autoclass:: aiida_trainspot.workflows.dataset_augmentation.DatasetAugmentationWorkChain
     :members:

**Ab Initio Labelling WorkChain**
  .. autoclass:: aiida_trainspot.workflows.labelling.AbInitioLabellingWorkChain
     :members:

**Training WorkChain**
  .. autoclass:: aiida_trainspot.workflows.training.TrainingWorkChain
     :members:

**MD Exploration WorkChain**
  .. autoclass:: aiida_trainspot.workflows.exploration.ExplorationWorkChain
     :members:
