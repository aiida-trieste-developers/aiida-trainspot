"""First active-learning loop on graphene, with the MACE engine.

Fill in the placeholders marked with <...> and the cluster settings, then run:

    verdi run get_started.py
"""

from pathlib import Path

import yaml

from aiida import load_profile
from aiida.engine import submit
from aiida.orm import Dict, Int, load_code, load_computer
from ase.io import read

from aiida_trainspot.data.pesdata import PESData
from aiida_trainspot.workflows.trainspot import TrainsPotWorkChain

script_dir = Path(__file__).parent

# --- profile and codes ---
load_profile()

QE_code = load_code("<pw_label>@<computer>")
LAMMPS_code = load_code("<lammps_label>@<computer>")
MACE_train_code = load_code("<mace_train_label>@<computer>")
MACE_postprocess_code = load_code("<mace_postprocess_label>@<computer>")
EVALUATION_code = load_code("committee_evaluation_portable")
EVALUATION_computer = load_computer("<computer>")

# --- scheduler settings ---
# Values for Leonardo (Booster) at CINECA. Adapt them to your cluster.
HPC_account = "<account>"
SLURM = {
    "account": HPC_account,
    "queue_name": "boost_usr_prod",  # SLURM partition
    "qos": "normal",
    "custom_scheduler_commands": "#SBATCH --gres=gpu:1",  # one GPU per job
    "import_sys_environment": False,
}


def set_scheduler(options, wallclock_min, mem_gb, cpus=8):
    """Set resources, wall time, memory and SLURM options of one calculation."""
    options.resources = {
        "num_machines": 1,
        "num_mpiprocs_per_machine": 1,
        "num_cores_per_mpiproc": cpus,
    }
    options.max_wallclock_seconds = wallclock_min * 60
    options.max_memory_kb = mem_gb * 1024 * 1024
    for key, value in SLURM.items():
        setattr(options, key, value)


# --- dataset ---
dataset = PESData([read(script_dir / "gr8x8.xyz")])

# --- builder ---
builder = TrainsPotWorkChain.get_builder(
    dataset=dataset,
    abinitiolabelling_code=QE_code,
    md_code=LAMMPS_code,
    abinitiolabelling_protocol="fast",
    pseudo_family="SSSP/1.3/PBE/efficiency",
    demo=True,
)
builder.max_loops = Int(2)

# --- training ---
with open(script_dir / "mace_config.yml") as handle:
    builder.training.mace.train.mace_config = Dict(yaml.safe_load(handle))
builder.training.mace.train.code = MACE_train_code
builder.training.mace.train.postprocess_code = MACE_postprocess_code
builder.training.mace.train.metadata.options.withmpi = False
# Launches MACE training through srun, needed for multi-GPU training on SLURM.
builder.training.mace.train.metadata.options.prepend_text = """function mace_run_train(){
    srun mace_run_train $@
}
export -f mace_run_train"""

# --- scheduler per code ---
qe_options = builder.ab_initio_labelling.quantumespresso.pw.metadata.options
qe_options.withmpi = True
set_scheduler(qe_options, wallclock_min=30, mem_gb=70)
set_scheduler(builder.training.mace.train.metadata.options, wallclock_min=60, mem_gb=30)
set_scheduler(builder.exploration.md.lammps.metadata.options, wallclock_min=30, mem_gb=30)

# --- committee evaluation ---
builder.committee_evaluation.code = EVALUATION_code
builder.committee_evaluation.metadata.computer = EVALUATION_computer
set_scheduler(builder.committee_evaluation.metadata.options, wallclock_min=30, mem_gb=30)

# --- submit ---
node = submit(builder)
print(f"Submitted TrainsPotWorkChain with PK = {node.pk}")
