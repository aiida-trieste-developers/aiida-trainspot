#!/usr/bin/env python
"""Committee evaluation of a set of potentials against reference datasets, for MACE/META/NEQUIP/DEEPMD alike.

Run without srun/SLURM at all, it just falls back to a single process on one device.
"""

import argparse
import glob
import logging
import os
import re
import sys
import time

import ase.io
import numpy as np
import torch

from prettytable import PrettyTable


def get_parity_data(dataset):
    """Get data for parity plots from dataset.

    Parameters
    ----------
    dataset : list
        List of dictionaries containing the information of the
        evaluated dataset.

    Returns:
    -------
    dict
        Dictionary containing the DFT and DNN quantities for
        energy, forces and stress.
    """
    if len(dataset) == 0:
        return {
            "dft_e": np.array([]),
            "pot_e": np.array([]),
            "std_pot_e": np.array([]),
            "dft_f": np.array([[], [], []]).T,
            "pot_f": np.array([[], [], []]).T,
            "std_pot_f": np.array([[], [], []]).T,
            "dft_s": np.array([]),
            "pot_s": np.array([]),
            "std_pot_s": np.array([]),
        }
    pot_e = []
    dft_e = []
    std_pot_e = []
    pot_f = []
    dft_f = []
    std_pot_f = []
    pot_s = []
    dft_s = []
    std_pot_s = []

    for frame in dataset:
        pot_e.append(
            [
                frame[key] / len(frame["positions"])
                for key in frame
                if "pot" in key and "energy" in key and "rmse" not in key
            ]
        )
        std_pot_e.append(np.std(pot_e[-1]))
        pot_e[-1] = np.mean(pot_e[-1])
        dft_e.append(frame["dft_energy"] / len(frame["positions"]))

        pot_f.append([frame[key] for key in frame if "pot" in key and "forces" in key and "rmse" not in key])
        std_pot_f.append(np.std(pot_f[-1], axis=0))
        pot_f[-1] = np.mean(pot_f[-1], axis=0)
        dft_f.append(frame["dft_forces"])

        pot_s.append([frame[key] for key in frame if "pot" in key and "stress" in key and "rmse" not in key])
        std_pot_s.append(np.std(pot_s[-1], axis=0))
        pot_s[-1] = np.mean(pot_s[-1], axis=0)
        dft_s.append(frame["dft_stress"])

    dft_f = np.concatenate(dft_f)
    pot_f = np.concatenate(pot_f)
    std_pot_f = np.concatenate(std_pot_f)
    dft_s = np.concatenate(dft_s)
    pot_s = np.concatenate(pot_s).ravel()
    std_pot_s = np.concatenate(std_pot_s).ravel()

    return {
        "dft_e": np.array(dft_e),
        "pot_e": np.array(pot_e),
        "std_pot_e": np.array(std_pot_e),
        "dft_f": np.array(dft_f),
        "pot_f": np.array(pot_f),
        "std_pot_f": np.array(std_pot_f),
        "dft_s": np.array(dft_s),
        "pot_s": np.array(pot_s),
        "std_pot_s": np.array(std_pot_s),
    }


def rmse_table(RMSE) -> PrettyTable:
    """Create a PrettyTable for the RMSE results."""
    table = PrettyTable()
    table.field_names = [
        "SET",
        "POTENTIAL",
        "RMSE Energy (meV/atom)",
        "RMSE Forces (meV/Å)",
        "RMSE Stress (meV/Å^3/atom)",
    ]

    for key in RMSE:
        keys2 = list(RMSE[key].keys())
        if "committee" in keys2:
            keys2.remove("committee")
            keys2 = ["committee"] + keys2
        for key2 in keys2:
            if key2 == "committee":
                table.add_row(
                    [
                        key,
                        key2,
                        f"{RMSE[key][key2]['rmse_e'] * 1000:8.1f} ± {RMSE[key][key2]['std_e'] * 1000:<8.1f}",
                        f"{RMSE[key][key2]['rmse_f'] * 1000:8.1f} ± {RMSE[key][key2]['std_f'] * 1000:<8.1f}",
                        f"{RMSE[key][key2]['rmse_s'] * 1000:8.2f} ± {RMSE[key][key2]['std_s'] * 1000:<8.2f}",
                    ]
                )
            else:
                table.add_row(
                    [
                        "",
                        key2.split("_")[-1],
                        f"{RMSE[key][key2]['rmse_e'] * 1000:8.1f}",
                        f"{RMSE[key][key2]['rmse_f'] * 1000:8.1f}",
                        f"{RMSE[key][key2]['rmse_s'] * 1000:8.2f}",
                    ]
                )
    return table


def split_by_set(dataset):
    """Group entries by their 'set' info key (TRAINING/VALIDATION/TEST).

    Lumps everything under NOT_SPLITTED if that key is missing/unrecognised. Skips empty groups.
    """
    not_split_list = [el for el in dataset if el.get("set") not in ("TRAINING", "TEST", "VALIDATION")]
    groups = {}
    if not_split_list:
        groups["NOT_SPLITTED"] = not_split_list
    if len(not_split_list) < len(dataset):
        for split in ("TRAINING", "VALIDATION", "TEST"):
            split_dataset = [el for el in dataset if el["set"] == split]
            if split_dataset:
                groups[split] = split_dataset
    return groups


def committee_deviation_stats(dataset):
    """Summary stats (mean/std/max over frames) of the per-frame committee disagreement.

    Already stored by `build_evaluated_dataset`. Unlike RMSE this needs no DFT reference, so it's
    available for every evaluated frame.
    """
    if not dataset:
        return None

    def summarize(key):
        values = np.array([el[key] for el in dataset])
        return {"mean": np.mean(values), "std": np.std(values), "max": np.max(values)}

    return {
        "n_frames": len(dataset),
        "energy_deviation_model": summarize("energy_deviation_model"),
        "forces_deviation_model": summarize("forces_deviation_model"),
        "stress_deviation_model": summarize("stress_deviation_model"),
    }


def _fmt_deviation(stat, decimals):
    mean, std, mx = stat["mean"] * 1000, stat["std"] * 1000, stat["max"] * 1000
    return f"{mean:.{decimals}f} ± {std:.{decimals}f} (max {mx:.{decimals}f})"


def committee_deviation_table(DEVIATION) -> PrettyTable:
    """Create a PrettyTable for the committee deviation results."""
    table = PrettyTable()
    table.field_names = [
        "SET",
        "N FRAMES",
        "Energy Deviation (meV/atom)",
        "Forces Deviation (meV/Å)",
        "Stress Deviation (meV/Å^3/atom)",
    ]
    for key, stats in DEVIATION.items():
        if stats is None:
            continue
        table.add_row(
            [
                key,
                stats["n_frames"],
                _fmt_deviation(stats["energy_deviation_model"], 1),
                _fmt_deviation(stats["forces_deviation_model"], 1),
                _fmt_deviation(stats["stress_deviation_model"], 2),
            ]
        )
    return table


def global_rmse(dataset):
    """Calculate global root mean square error between DFT and DNN quantities.

    Then return mean and standard deviation among the committee of potentials.

    Parameters
    ----------
    dataset : list
        List of dictionaries containing the information of the
        evaluated dataset.

    Returns:
    -------
    dict
        Dictionary containing the mean and standard deviation of
        the root mean square error for energy, forces and stress.
    """
    RMSE = {}
    if len(dataset) == 0:
        return RMSE
    dnn_f = []
    dnn_e = []
    dnn_s = []
    dft_e = []
    dft_f = []
    dft_s = []
    for key in dataset[-1]:
        if re.fullmatch(r"pot_\d+_forces", key):
            dnn_f.append([])
            for frame in dataset:
                dnn_f[-1].extend(frame[key].ravel())
        elif re.fullmatch(r"pot_\d+_energy", key):
            dnn_e.append([])
            for frame in dataset:
                dnn_e[-1].append(frame[key] / len(frame["positions"]))
        elif re.fullmatch(r"pot_\d+_stress", key):
            dnn_s.append([])
            for frame in dataset:
                dnn_s[-1].extend(frame[key].ravel())
        elif "dft_energy" in key:
            for frame in dataset:
                dft_e.append(frame[key] / len(frame["positions"]))
        elif "dft_forces" in key:
            for frame in dataset:
                dft_f.extend(frame[key].ravel())
        elif "dft_stress" in key:
            for frame in dataset:
                dft_s.extend(frame[key].ravel())

    rmse_e = np.array([calc_rmse(dft_e, dnn) for dnn in dnn_e])
    rmse_f = np.array([calc_rmse(dft_f, dnn) for dnn in dnn_f])
    rmse_s = np.array([calc_rmse(dft_s, dnn) for dnn in dnn_s])

    for ii, _ in enumerate(dnn_e):
        RMSE[f"pot_{ii+1}"] = {
            "rmse_e": rmse_e[ii],
            "rmse_f": rmse_f[ii],
            "rmse_s": rmse_s[ii],
        }
    if len(dnn_e) > 1:
        RMSE["committee"] = {
            "rmse_e": np.mean(rmse_e),
            "std_e": np.std(rmse_e),
            "rmse_f": np.mean(rmse_f),
            "std_f": np.std(rmse_f),
            "rmse_s": np.mean(rmse_s),
            "std_s": np.std(rmse_s),
        }

    return RMSE


def calc_rmse(dft_list, dnn_list):
    """Calculate root mean square error between DFT and DNN lists.

    Parameters
    ----------
    dft_list : list
        List of DFT quantities
    dnn_list : list
        List of DNN quantities

    Returns:
    -------
    rmse : float
        Root mean square error between DFT and DNN quantities
    """
    dft = np.array(dft_list)
    dnn = np.array(dnn_list)
    return np.sqrt(np.mean(np.square(dft - dnn)))


def model_deviation(data):
    """Calculate the model deviation as the standard deviation for the set of potentials."""
    shape = data.shape
    if len(shape) == 1:
        return np.std(data)
    mean = np.mean(data, axis=0)
    return np.max(np.mean(np.linalg.norm(data - mean, axis=2) ** 2, axis=0) ** 0.5)


def maximum_deviation(data):
    """Calculate the maximum deviation for the set of potentials."""
    shape = data.shape
    if len(shape) == 1:
        return max(data) - min(data)
    data = np.linalg.norm(data, axis=2)
    return np.mean(np.max(data, axis=0) - np.min(data, axis=0))


def dist_info():
    """(rank, world_size, local_rank) from SLURM env vars; (0, 1, 0) outside SLURM."""
    return (
        int(os.environ.get("SLURM_PROCID", 0)),
        int(os.environ.get("SLURM_NTASKS", 1)),
        int(os.environ.get("SLURM_LOCALID", 0)),
    )


def select_device(local_rank):
    """Auto-select a device: one GPU per rank if available, else CPU."""
    if torch.cuda.is_available():
        return f"cuda:{local_rank % torch.cuda.device_count()}"
    return "cpu"


def shard_indices(n_frames, rank, world_size):
    """Round-robin split so every rank gets a near-equal share of the frames."""
    return list(range(rank, n_frames, world_size))


def run_id():
    """Shared identifier for this SLURM job (same for every rank of it).

    Stamped into partial-file names so a stale .part left behind by a crashed/timed-out job (same
    working directory, e.g. a resubmitted AiiDA calc) can never be mistaken for a shard of the current
    run - no cleanup-on-startup needed, and no race with peers still writing.
    """
    return os.environ.get("SLURM_JOB_ID", "local")


def partial_path(dataset_name, rank):
    """Filename for one rank's shard of a dataset's evaluated frames."""
    return f"{dataset_name}_evaluated_rank{rank}.job{run_id()}.npz.part"


def wait_for_partials(paths, poll_interval=2.0, timeout=3600.0):
    """Block until every path in `paths` exists (or raise `TimeoutError`)."""
    start = time.time()
    for path in paths:
        while not os.path.exists(path):
            if time.time() - start > timeout:
                raise TimeoutError(f"Timed out after {timeout:.0f}s waiting for {path}")
            time.sleep(poll_interval)
    return paths


def save_partial_dataset(dataset_name, rank, indices, shard_evaluated):
    """Atomically write one rank's shard of evaluated frames to its partial-file."""
    path = partial_path(dataset_name, rank)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as fh:
        np.savez(fh, indices=np.array(indices), evaluated_dataset=shard_evaluated)
    os.replace(tmp_path, path)  # atomic, so a peer never observes a half-written file
    return path


def gather_partial_datasets(dataset_name, world_size):
    """Rank 0 only: wait for every rank's shard and reassemble the original frame order."""
    paths = wait_for_partials([partial_path(dataset_name, r) for r in range(world_size)])
    by_index = {}
    for path in paths:
        with np.load(path, allow_pickle=True) as npz:
            for idx, entry in zip(npz["indices"], npz["evaluated_dataset"], strict=True):
                by_index[int(idx)] = entry
        os.remove(path)
    return [by_index[i] for i in sorted(by_index)]


# --------------------------------------------------------------------------------------------------
# MACE backend: raw torch weights, batched evaluation via torch_geometric's DataLoader (no ASE
# Calculator in the loop at all). This is the only engine with a native batched path today.
# --------------------------------------------------------------------------------------------------


def mace_load(potential_files, device):
    """Load committee members as bare torch models (no per-model ASE calculator)."""
    from mace.calculators.mace import get_model_dtype
    from mace.tools import torch_tools

    models = []
    for path in potential_files:
        model = torch.load(path, map_location=device)
        model = model.to(device)
        for param in model.parameters():
            param.requires_grad = False
        model.eval()
        models.append(model)
    torch_tools.set_default_dtype(get_model_dtype(models[0]))
    return models


def graph_signature(model):
    """(cutoff, atomic-number order, heads) that determines the neighbour-list graphs a model needs.

    Committee members sharing a signature can share the same pre-built graphs instead of each
    rebuilding them from scratch.
    """
    from mace.tools import utils

    z_table = utils.AtomicNumberTable([int(z) for z in model.atomic_numbers])
    heads = tuple(getattr(model, "heads", None) or ())
    return (float(model.r_max), tuple(z_table.zs), heads)


def build_atomic_data(atoms_list, model):
    """Build one `mace.data.AtomicData` graph per structure, for the given model's cutoff/species."""
    from mace import data as mace_data
    from mace.tools import utils

    z_table = utils.AtomicNumberTable([int(z) for z in model.atomic_numbers])
    heads = getattr(model, "heads", None)
    return [
        mace_data.AtomicData.from_config(
            mace_data.config_from_atoms(atoms),
            z_table=z_table,
            cutoff=float(model.r_max),
            heads=heads,
        )
        for atoms in atoms_list
    ]


def evaluate_model(model, dataset, device, batch_size):
    """Batched forward pass of a single model over a pre-built list of AtomicData graphs.

    Yields (batch_forces, energies_chunk, stresses_chunk) per batch so the caller can track progress;
    batch_forces is a list of per-frame (n_atoms_i, 3) arrays.
    """
    from mace.tools import torch_geometric, torch_tools

    loader = torch_geometric.dataloader.DataLoader(
        dataset=dataset, batch_size=batch_size, shuffle=False, drop_last=False
    )
    for raw_batch in loader:
        batch = raw_batch.to(device)
        out = model(batch.to_dict(), compute_stress=True)
        energies_chunk = torch_tools.to_numpy(out["energy"])
        stresses_chunk = torch_tools.to_numpy(out["stress"])
        ptr = batch.ptr.cpu().numpy()
        batch_forces = np.split(torch_tools.to_numpy(out["forces"]), indices_or_sections=ptr[1:], axis=0)[:-1]
        yield batch_forces, energies_chunk, stresses_chunk


def mace_evaluate(models, atoms_list, device, batch_size, log_freq=100):
    """Run every committee member over the whole dataset, batched.

    Logs an ETA every `log_freq` evaluated (frame, model) pairs.

    Returns:
    -------
    energies : np.ndarray, shape (n_models, n_frames)
    forces   : list of np.ndarray, one (n_models, n_atoms_i, 3) array per frame
    stresses : np.ndarray, shape (n_models, n_frames, 3, 3)
    """
    n_frames = len(atoms_list)
    n_models = len(models)
    if n_frames == 0:
        return np.empty((n_models, 0)), [], np.empty((n_models, 0, 3, 3))
    total_work = n_models * n_frames
    energies = np.empty((n_models, n_frames))
    stresses = np.empty((n_models, n_frames, 3, 3))
    forces = [None] * n_frames

    # Committee members are almost always the same architecture/cutoff (just
    # different training seeds), so the neighbour-list graphs are identical
    # across them; build them once instead of n_models times.
    shared_graphs = len({graph_signature(model) for model in models}) == 1
    shared_dataset = build_atomic_data(atoms_list, models[0]) if shared_graphs else None

    time_i = time.time()
    done = 0
    last_log = 0
    for m_idx, model in enumerate(models):
        dataset = shared_dataset if shared_graphs else build_atomic_data(atoms_list, model)
        e_chunks, s_chunks = [], []
        frame_idx = 0
        for batch_forces, energies_chunk, stresses_chunk in evaluate_model(model, dataset, device, batch_size):
            e_chunks.append(energies_chunk)
            s_chunks.append(stresses_chunk)
            for frame_forces in batch_forces:
                if forces[frame_idx] is None:
                    forces[frame_idx] = np.empty((n_models, frame_forces.shape[0], 3))
                forces[frame_idx][m_idx] = frame_forces
                frame_idx += 1
            done += len(batch_forces)

            if done - last_log >= log_freq or done == total_work:
                elapsed = time.time() - time_i
                eta = elapsed / done * (total_work - done)
                logging.info(
                    f"Potential {m_idx+1}/{n_models}: frame {frame_idx:5d}/{n_frames} evaluated "
                    f"- estimated time remaining: {eta:.2f} s"
                )
                last_log = done
        energies[m_idx] = np.concatenate(e_chunks, axis=0)
        stresses[m_idx] = np.concatenate(s_chunks, axis=0)
    return energies, forces, stresses


# --------------------------------------------------------------------------------------------------
# META/NEQUIP/DEEPMD backend: plain ASE Calculator, one structure at a time.
# --------------------------------------------------------------------------------------------------


def metatomic_load(potential_files, device):
    """Load committee members as `MetatomicCalculator` ASE calculators."""
    from metatomic.torch.ase_calculator import MetatomicCalculator

    return [MetatomicCalculator(pot, extensions_directory="extensions/", device=device) for pot in potential_files]


def nequip_load(potential_files, device):
    """Load committee members as `NequIPCalculator` ASE calculators (compiled `.nequip.pt2` files)."""
    from nequip.integrations.ase import NequIPCalculator

    return [NequIPCalculator.from_compiled_model(compile_path=pot, device=device) for pot in potential_files]


def deepmd_load(potential_files, device):  # noqa: ARG001
    """Load committee members as DeePMD-kit `DP` ASE calculators (frozen `.pth` files)."""
    from deepmd.calculator import DP

    return [DP(model=pot) for pot in potential_files]


def ase_calculator_evaluate(models, atoms_list, device, batch_size, log_freq=100):  # noqa: ARG001
    """Evaluate every committee member one ASE `Atoms`/one calculator at a time."""
    n_frames = len(atoms_list)
    n_models = len(models)
    if n_frames == 0:
        return np.empty((n_models, 0)), [], np.empty((n_models, 0, 3, 3))

    energies = np.empty((n_models, n_frames))
    stresses = np.empty((n_models, n_frames, 3, 3))
    forces = [None] * n_frames

    time_i = time.time()
    for ii, atm in enumerate(atoms_list):
        for m_idx, calculator in enumerate(models):
            atm.calc = calculator
            energies[m_idx, ii] = atm.get_potential_energy()
            frame_forces = np.array(atm.get_forces())
            if forces[ii] is None:
                forces[ii] = np.empty((n_models, frame_forces.shape[0], 3))
            forces[ii][m_idx] = frame_forces
            stresses[m_idx, ii] = np.array(atm.get_stress(voigt=False))

        if (ii + 1) % log_freq == 0 or ii + 1 == n_frames:
            elapsed = time.time() - time_i
            eta = elapsed / (ii + 1) * (n_frames - ii - 1)
            logging.info(f"Frame {ii+1:5d}/{n_frames} evaluated - estimated time remaining: {eta:.2f} s")

    return energies, forces, stresses


BACKENDS = {
    "MACE": (mace_load, mace_evaluate),
    "META": (metatomic_load, ase_calculator_evaluate),
    "NEQUIP": (nequip_load, ase_calculator_evaluate),
    "DEEPMD": (deepmd_load, ase_calculator_evaluate),
}


def build_evaluated_dataset(atoms_list, energies, forces, stresses):
    """Assemble the per-frame dataset dict (DFT reference + per-potential predictions + deviations)."""
    n_models = energies.shape[0]
    evaluated_dataset = []
    for ii, atm in enumerate(atoms_list):
        entry = {k: v for k, v in atm.info.items() if k not in ("energy", "stress")}
        entry["cell"] = np.array(atm.get_cell())
        entry["positions"] = np.array(atm.get_positions())
        entry["symbols"] = atm.get_chemical_symbols()
        entry["pbc"] = atm.get_pbc()
        try:
            entry["dft_energy"] = atm.get_potential_energy()
            entry["dft_forces"] = np.array(atm.get_forces())
            entry["dft_stress"] = np.array(atm.get_stress(voigt=False)).ravel()
        except Exception:
            pass

        for m in range(n_models):
            entry[f"pot_{m+1}_energy"] = energies[m, ii]
            entry[f"pot_{m+1}_forces"] = forces[ii][m]
            entry[f"pot_{m+1}_stress"] = stresses[m, ii]
            if "dft_energy" in entry:
                entry[f"pot_{m+1}_energy_rmse"] = calc_rmse([entry["dft_energy"]], [entry[f"pot_{m+1}_energy"]])
            if "dft_forces" in entry:
                entry[f"pot_{m+1}_forces_rmse"] = calc_rmse(entry["dft_forces"], entry[f"pot_{m+1}_forces"])
            if "dft_stress" in entry:
                entry[f"pot_{m+1}_stress_rmse"] = calc_rmse(entry["dft_stress"], stresses[m, ii].ravel())

        entry["energy_deviation"] = maximum_deviation(energies[:, ii])
        entry["forces_deviation"] = maximum_deviation(forces[ii])
        entry["stress_deviation"] = maximum_deviation(stresses[:, ii])
        entry["energy_deviation_model"] = model_deviation(energies[:, ii])
        entry["forces_deviation_model"] = model_deviation(forces[ii])
        entry["stress_deviation_model"] = model_deviation(stresses[:, ii])
        evaluated_dataset.append(entry)
    return evaluated_dataset


def main(args, rank, world_size, local_rank):  # noqa: PLR0912, PLR0915
    """Committee evaluation of `args.engine` models."""
    is_main = rank == 0
    if is_main:
        logging.info("###########################################")
        logging.info(f"### Committee evaluation of {args.engine} models ###")
        logging.info("###########################################\n")
        if world_size > 1:
            logging.info(f"Running distributed across {world_size} SLURM tasks.\n")

    potential_files = sorted(glob.glob("potential*"))
    datasets = sorted(glob.glob("dataset*xyz"))

    load, evaluate = BACKENDS[args.engine]

    device = args.device or select_device(local_rank)
    if device == "cpu":
        cpus_per_task = os.environ.get("SLURM_CPUS_PER_TASK")
        if cpus_per_task:
            torch.set_num_threads(int(cpus_per_task))
    logging.info(f"Loading {len(potential_files)} potentials on {device}...")
    models = load(potential_files, device)
    logging.info(f"Loaded {len(models)} potentials.\n")

    for jj, dataset in enumerate(datasets):
        dataset_name = dataset.replace(".xyz", "")
        if is_main:
            logging.info(f"Loading dataset {jj+1}/{len(datasets)}...")
        atoms_list = ase.io.read(dataset, index=":", format="extxyz")
        n_frames = len(atoms_list)
        if is_main:
            logging.info(f"Loaded {n_frames} frames from dataset {jj+1}.\n")

        indices = shard_indices(n_frames, rank, world_size)
        shard_atoms = [atoms_list[i] for i in indices]

        logging.info(
            f"Evaluating {len(shard_atoms)}/{n_frames} frames of dataset {jj+1}/{len(datasets)} "
            f"with {len(models)} potentials on {device} (batch size {args.batch_size})..."
        )
        time_i = time.time()
        energies, forces, stresses = evaluate(models, shard_atoms, device, args.batch_size, log_freq=args.log_freq)
        logging.info(f"Evaluation of this shard of dataset {jj+1} finished in {time.time()-time_i:.2f} s.")

        shard_evaluated = build_evaluated_dataset(shard_atoms, energies, forces, stresses)

        if world_size == 1:
            evaluated_dataset = shard_evaluated
        else:
            save_partial_dataset(dataset_name, rank, indices, shard_evaluated)
            if not is_main:
                continue  # only rank 0 gathers and writes the combined outputs
            evaluated_dataset = gather_partial_datasets(dataset_name, world_size)

        logging.info(f"Saving evaluated dataset {jj+1}...")
        np.savez(f"{dataset_name}_evaluated.npz", evaluated_dataset=evaluated_dataset)
        logging.info(f"Saved evaluated dataset {jj+1} as {dataset_name}_evaluated.npz.\n")

        # Committee deviation needs no DFT reference, so it's reported for
        # every dataset, labelled or not.
        logging.info(f"Calculating committee deviation for dataset {jj+1}...")
        DEVIATION = {key: committee_deviation_stats(group) for key, group in split_by_set(evaluated_dataset).items()}
        DEVIATION["ALL"] = committee_deviation_stats(evaluated_dataset)
        logging.info("Committee deviation table:\n" + str(committee_deviation_table(DEVIATION)))
        logging.info(f"Saving committee deviation for dataset {jj+1}...")
        np.savez(f"{dataset_name}_deviation.npz", deviation=DEVIATION)

        labelled_dataset = [el for el in evaluated_dataset if "dft_energy" in el and "dft_forces" in el]

        if not labelled_dataset:
            logging.info(f"No Labelled structures found in dataset {jj+1}. Skipping RMSE calculation.")
            continue

        logging.info(f"Calculating global RMSE for dataset {jj+1}...")
        RMSE = {}
        PARITY = {}
        for key, group in split_by_set(labelled_dataset).items():
            RMSE[key] = global_rmse(group)
            prefix = "not_splitted" if key == "NOT_SPLITTED" else key.lower()
            PARITY.update({f"{prefix}_{k}": v for k, v in get_parity_data(group).items()})
        RMSE["ALL"] = global_rmse(labelled_dataset)

        logging.info("Error-table:\n" + str(rmse_table(RMSE)))
        logging.info(f"Saving global RMSE for dataset {jj+1}...")
        np.savez(f"{dataset_name}_rmse.npz", rmse=RMSE)
        logging.info(f"Saving data for parity plots for dataset {jj+1}...")
        np.savez(f"{dataset_name}_parity.npz", parity=PARITY)

    if is_main:
        logging.info("DONE!")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", required=True, choices=sorted(BACKENDS), help="Which engine trained the committee members"
    )
    parser.add_argument(
        "--batch-size", type=int, default=32, help="Number of structures evaluated per batch (MACE only)"
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Device to run on, e.g. cpu/cuda/cuda:1 (default: auto-select from SLURM_LOCALID)",
    )
    parser.add_argument(
        "--log-freq", type=int, default=100, help="Log an ETA every N evaluated (frame, potential) pairs"
    )
    return parser.parse_args()


def set_logger(level=logging.INFO, rank=0):
    """Set up the logger for the committee evaluation."""
    # Only rank 0 writes to stdout/the SLURM output file; other ranks stay silent.
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if rank != 0:
        logger.addHandler(logging.NullHandler())
        return
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
    logger.addHandler(ch)


if __name__ == "__main__":
    slurm_rank, slurm_world_size, slurm_local_rank = dist_info()
    set_logger(rank=slurm_rank)
    main(parse_args(), slurm_rank, slurm_world_size, slurm_local_rank)
