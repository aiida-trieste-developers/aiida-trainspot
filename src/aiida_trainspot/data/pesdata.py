"""PESData class for handling datasets of atomic configurations."""

import os
import re
import tempfile
import warnings

from contextlib import redirect_stdout
from io import StringIO

import h5py
import numpy as np

from aiida.orm import Data
from ase import Atoms
from ase.calculators.calculator import PropertyNotImplementedError
from ase.calculators.singlepoint import SinglePointCalculator, SinglePointDFTCalculator
from ase.data import atomic_numbers
from ase.io import write

DEFAULT_WARN_THRESHOLD = 1000

VOIGT_STRESS_LENGTH = 6

SET_TRAINING = "TRAINING"
SET_VALIDATION = "VALIDATION"
SET_TEST = "TEST"
SET_LABELS = (SET_TRAINING, SET_VALIDATION, SET_TEST)
_SET_LABELS_BY_UPPER = {label.upper(): label for label in SET_LABELS}

_XYZ_EXCLUDED_KEYS = frozenset(
    {
        "cell",
        "symbols",
        "positions",
        "pbc",
        "forces",
        "stress",
        "energy",
        "dft_forces",
        "dft_stress",
        "dft_energy",
        "md_forces",
        "md_stress",
        "md_energy",
    }
)
_XYZ_EXCLUDED_PATTERN = re.compile(r"pot_\d+_(energy|forces|stress)")


def convert_stress(stress):
    """Convert stress to 3x3 matrix if in Voigt notation."""
    if len(np.shape(stress)) == 1:
        if len(stress) == VOIGT_STRESS_LENGTH:
            stress = np.array(
                [
                    [stress[0], stress[5], stress[4]],
                    [stress[5], stress[1], stress[3]],
                    [stress[4], stress[3], stress[2]],
                ]
            )
        else:
            stress = np.array(
                [
                    [stress[0], stress[1], stress[2]],
                    [stress[3], stress[4], stress[5]],
                    [stress[6], stress[7], stress[8]],
                ]
            )
    return np.array(stress)


class PESData(Data):
    """Class to handle datasets of atomic configurations for potential energy surfaces."""

    _list_key = "pesdata.h5"

    @property
    def _legacy_list_key(self):
        """Repository key used by nodes stored before the naming fix, kept for read compatibility."""
        return f"psedata_{self.uuid}.npz"

    def _read_key(self):
        """Return whichever repository key currently holds this node's data, new or legacy naming."""
        if self._list_key in self.base.repository.list_object_names():
            return self._list_key
        return self._legacy_list_key

    def __init__(self, data=None, save_labels=True, **kwargs):
        """Initialize a PESData instance.

        :param data: Optional list of data to initialize the PESData node.
        :param kwargs: Additional keyword arguments passed to the parent Data class.
        """
        super().__init__(**kwargs)  # Initialize the parent class
        if data:
            if isinstance(data[0], Atoms):
                self.set_ase(data, save_labels=save_labels)
            else:
                self.set_list(data)

    def __iter__(self):
        """Return an iterator over the dataset."""
        return self.iter_items()

    def __add__(self, other):
        """Support the + operation for combining two PESData objects by creating a new node."""
        if not isinstance(other, PESData):
            raise TypeError(f"Cannot add {type(other)} to PESData")
        return self.__iadd__(other)

    def __iadd__(self, other):
        """Support the += operation for combining two PESData objects by creating a new node."""
        if not isinstance(other, PESData):
            raise TypeError(f"Cannot add {type(other)} to PESData")

        return PESData(data=self.get_list() + other.get_list())

    def __len__(self):
        """Return the number of configurations in the dataset."""
        try:
            return self._dataset_size()
        except Exception:
            return 0

    def __getitem__(self, index):
        """Return the configuration at the given index, or a list of configurations for a slice."""
        if isinstance(index, slice):
            return [self.get_item(i) for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        return self.get_item(index)

    def __str__(self):
        """Return a human-readable one-line summary, e.g. for `verdi node show` or a Python shell."""
        return f"{super().__str__()}, {len(self)} configurations ({self.len_labelled} labelled)"

    def __repr__(self):
        """Return a detailed representation useful for debugging."""
        return (
            f"<{self.__class__.__name__}: {len(self)} configurations "
            f"(labelled={self.len_labelled}, unlabelled={self.len_unlabelled}, "
            f"training={self.len_training}, validation={self.len_validation}, "
            f"test={self.len_test}, unassigned={self.len_no_set})>"
        )

    def _dataset_size(self):
        """Return the number of configurations, counting the HDF5 groups if not yet cached."""
        n_items = self.base.attributes.get("dataset_size", 0)
        if n_items:
            return n_items
        try:
            with self.base.repository.open(self._read_key(), "rb") as hdf_file, h5py.File(hdf_file, "r") as hdf:
                return len(hdf)
        except FileNotFoundError:
            return 0

    def _extract_config_from_group(self, group):
        """Helper method to extract configuration data from an HDF5 group.

        :param group: HDF5 group object containing configuration data
        :return: Dictionary with the configuration data
        """
        config = {}
        # Extract datasets
        for key, value in group.items():
            # Convert datasets to lists or native Python types
            data = value[()]
            config[key] = data.tolist() if hasattr(data, "tolist") else data

        # Add attributes to the config
        for attr_key, attr_value in group.attrs.items():
            config[attr_key] = attr_value

        # Ensure symbols are decoded properly
        if "symbols" in config:
            config["symbols"] = [
                str(symbol, "utf-8") if isinstance(symbol, bytes) else str(symbol) for symbol in config["symbols"]
            ]

        return config

    def get_atomic_species(self):
        """Return the list of atomic species in the dataset."""
        return self.base.attributes.get("atomic_species", [])

    def get_atomic_numbers(self):
        """Return the list of atomic numbers in the dataset."""
        atomic_species = self.get_atomic_species()
        atomic_nums = [atomic_numbers[symbol] for symbol in atomic_species if symbol in atomic_numbers]
        return atomic_nums

    def get_item(self, index):
        """Return a specific item from the dataset by index."""
        try:
            with self.base.repository.open(self._read_key(), "rb") as hdf_file, h5py.File(hdf_file, "r") as hdf:
                group_key = f"item_{index}"
                if group_key not in hdf:
                    raise IndexError(f"Index {index} out of range")
                return self._extract_config_from_group(hdf[group_key])
        except FileNotFoundError as e:
            raise IndexError(f"Index {index} out of range") from e

    def iter_items(self):
        """Generator function to iterate through items without loading all into memory."""
        try:
            with self.base.repository.open(self._read_key(), "rb") as hdf_file, h5py.File(hdf_file, "r") as hdf:
                for group_key in sorted(hdf.keys(), key=lambda k: int(k.split("_")[1])):
                    yield self._extract_config_from_group(hdf[group_key])
        except FileNotFoundError:
            return

    def get_list(self, max_items=None, warn_threshold=DEFAULT_WARN_THRESHOLD):
        """Return the contents of this node as a list.

        :param max_items: Optional limit to the number of items to load
        :param warn_threshold: Show warning if loading more than this many items
        """
        n_items = self._dataset_size()
        max_items = n_items if max_items is None else min(max_items, n_items)

        if max_items > warn_threshold:
            warnings.warn(
                f"Loading {max_items} items into memory. This may consume a significant amount "
                "of RAM. Consider using iter_items() for memory-efficient iteration.",
                UserWarning,
                stacklevel=2,
            )

        data = []
        for i, config in enumerate(self.iter_items()):
            if i >= max_items:
                break
            data.append(config)

        return data

    def _persist(self, save_data, num_labelled_frames, num_unlabelled_frames, atomic_species):
        """Write configurations to the repository and store dataset metadata as node attributes.

        :param save_data: List of configuration dictionaries, ready to be written to HDF5
        :param num_labelled_frames: Number of configurations carrying DFT energy/forces
        :param num_unlabelled_frames: Number of configurations without DFT energy/forces
        :param atomic_species: Iterable of chemical symbols present in the dataset
        """
        # Normalize case variants (e.g. "training", "Training") to the canonical label, so that
        # both the stored data and downstream consumers doing an exact match see "TRAINING".
        for item in save_data:
            raw_set = item.get("set")
            if isinstance(raw_set, str):
                canonical = _SET_LABELS_BY_UPPER.get(raw_set.upper())
                if canonical is not None:
                    item["set"] = canonical

        num_training_frames = sum(1 for item in save_data if item.get("set") == SET_TRAINING)
        num_validation_frames = sum(1 for item in save_data if item.get("set") == SET_VALIDATION)
        num_test_frames = sum(1 for item in save_data if item.get("set") == SET_TEST)
        num_no_set_frames = len(save_data) - num_training_frames - num_validation_frames - num_test_frames

        unrecognized_sets = {item["set"] for item in save_data if "set" in item and item["set"] not in SET_LABELS}
        if unrecognized_sets:
            warnings.warn(
                f"Found configurations with unrecognised 'set' values: {sorted(unrecognized_sets, key=str)}. "
                f"Expected one of {SET_LABELS}; these configurations were counted as unassigned.",
                UserWarning,
                stacklevel=2,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_temp_file = os.path.join(temp_dir, "dataset.h5")
            with h5py.File(dataset_temp_file, "w") as hdf:
                for idx, item in enumerate(save_data):
                    group = hdf.create_group(f"item_{idx}")
                    for key, value in item.items():
                        if isinstance(value, list | np.ndarray):
                            group.create_dataset(key, data=value)
                        else:
                            group.attrs[key] = value

            # Store the file in the AiiDA repository
            self.base.repository.put_object_from_file(dataset_temp_file, self._list_key)

        # Store metadata as attributes
        self.base.attributes.set("dataset_size", len(save_data))
        self.base.attributes.set("num_labelled_frames", num_labelled_frames)
        self.base.attributes.set("num_unlabelled_frames", num_unlabelled_frames)
        self.base.attributes.set("num_training_frames", num_training_frames)
        self.base.attributes.set("num_validation_frames", num_validation_frames)
        self.base.attributes.set("num_test_frames", num_test_frames)
        self.base.attributes.set("num_no_set_frames", num_no_set_frames)
        self.base.attributes.set("atomic_species", sorted(atomic_species))

    def set_ase(self, data, save_labels=True):
        """Set the contents of this node by saving a list of ASE Atoms objects as an HDF5 file.

        :param data: A list of ASE Atoms objects to save.
        """
        if not isinstance(data, list) or not all(isinstance(item, Atoms) for item in data):
            raise TypeError("Input data must be a list of ase.atoms.Atoms.")

        num_labelled_frames = 0
        num_unlabelled_frames = 0
        symb = set()
        save_data = []
        for atm in data:
            has_dft_calc = isinstance(atm.calc, SinglePointDFTCalculator | SinglePointCalculator)
            if save_labels and has_dft_calc:
                num_labelled_frames += 1
                entry = {
                    "cell": atm.cell,
                    "symbols": atm.get_chemical_symbols(),
                    "positions": atm.get_positions(),
                    "pbc": atm.pbc,
                    "dft_energy": atm.calc.results["energy"],
                    "dft_forces": atm.calc.results["forces"],
                }
                try:
                    entry["dft_stress"] = atm.get_stress(voigt=False)
                except PropertyNotImplementedError:
                    pass
            else:
                num_unlabelled_frames += 1
                entry = {
                    "cell": atm.cell,
                    "symbols": atm.get_chemical_symbols(),
                    "positions": atm.get_positions(),
                    "pbc": atm.pbc,
                }

            symb.update(entry["symbols"])
            for key, value in atm.info.items():
                if "energy" not in key:
                    entry[key] = value

            save_data.append(entry)

        self._persist(save_data, num_labelled_frames, num_unlabelled_frames, symb)

    def set_list(self, data):
        """Set the contents of this node by saving a list as an HDF5 file."""
        if not isinstance(data, list):
            raise TypeError("Input data must be a list.")

        num_labelled_frames = 0
        num_unlabelled_frames = 0
        symb = set()
        save_data = []
        for item in data:
            if "pbc" not in item:
                item["pbc"] = [True, True, True]
                warnings.warn(
                    "Periodic boundary conditions not found in the dataset. Assuming PBC = [True, True, True].",
                    UserWarning,
                    stacklevel=2,
                )
            if "cell" not in item:
                raise ValueError("Cell vectors not found in the dataset.")
            if "symbols" not in item:
                raise ValueError("Atomic symbols not found in the dataset.")
            if "positions" not in item:
                raise ValueError("Atomic positions not found in the dataset.")

            if "dft_forces" in item and "dft_energy" in item:
                num_labelled_frames += 1
            else:
                num_unlabelled_frames += 1

            # Ensure that symbols are a list of strings
            item["symbols"] = [str(symbol) for symbol in item["symbols"]]
            symb.update(item["symbols"])

            save_data.append(
                {key: value.tolist() if isinstance(value, np.ndarray) else value for key, value in item.items()}
            )

        self._persist(save_data, num_labelled_frames, num_unlabelled_frames, symb)

    def _config_to_ase(self, config):
        """Helper method to convert a configuration dictionary to an ASE Atoms object.

        :param config: Dictionary containing atomic configuration data
        :return: ASE Atoms object
        """
        atoms = Atoms(
            symbols=config["symbols"],
            positions=config["positions"],
            cell=config["cell"],
            pbc=config["pbc"],
        )

        # Add calculator with DFT data if available
        if "dft_energy" in config and "dft_forces" in config:
            calc_kwargs = {
                "energy": config["dft_energy"],
                "forces": config["dft_forces"],
            }
            if "dft_stress" in config:
                calc_kwargs["stress"] = convert_stress(config["dft_stress"])

            atoms.calc = SinglePointCalculator(atoms, **calc_kwargs)

        return atoms

    def get_ase_item(self, index):
        """Get a specific configuration as an ASE Atoms object.

        :param index: Index of the configuration to retrieve
        :return: ASE Atoms object
        """
        config = self.get_item(index)
        return self._config_to_ase(config)

    def get_ase(self, index=None):
        """Convert dataset to ASE Atoms object(s).

        :param index: Optional index of a specific configuration to retrieve
        """
        if index is not None:
            return self.get_ase_item(index)
        return self.get_ase_list()

    def get_ase_list(self, max_items=None, warn_threshold=DEFAULT_WARN_THRESHOLD):
        """Convert dataset to a list of ASE Atoms objects.

        :param max_items: Optional limit to the number of items to load
        :param warn_threshold: Show warning if loading more than this many items
        :return: List of ASE Atoms objects
        """
        n_items = self._dataset_size()
        max_items = n_items if max_items is None else min(max_items, n_items)

        if max_items > warn_threshold:
            warnings.warn(
                f"Loading {max_items} items into memory. This may consume a significant amount of RAM.",
                UserWarning,
                stacklevel=2,
            )

        ase_list = []
        for i, config in enumerate(self.iter_items()):
            if i >= max_items:
                break
            ase_list.append(self._config_to_ase(config))

        return ase_list

    def get_txt(self, write_params=False, key_prefix="", max_items=None, warn_threshold=DEFAULT_WARN_THRESHOLD):
        """Convert dataset to extxyz format."""
        return self.get_xyz(write_params, key_prefix, max_items, warn_threshold)

    def get_xyz(self, write_params=False, key_prefix="", max_items=None, warn_threshold=DEFAULT_WARN_THRESHOLD):
        """Convert dataset to XYZ format text.

        :param write_params: Whether to include additional parameters in the output
        :param key_prefix: Prefix to add to property keys (energy, forces, stress)
        :param max_items: Optional limit to the number of items to process
        :param warn_threshold: Show warning if processing more than this many items
        :return: Text in XYZ format
        """
        n_items = self._dataset_size()
        max_items = n_items if max_items is None else min(max_items, n_items)

        if max_items > warn_threshold:
            warnings.warn(
                f"Processing {max_items} items. This may take some time and consume memory.",
                UserWarning,
                stacklevel=2,
            )

        if key_prefix and not key_prefix.endswith("_"):
            key_prefix += "_"

        dataset_txt = ""
        for i, config in enumerate(self.iter_items()):
            if i >= max_items:
                break

            params = [key for key in config if key not in _XYZ_EXCLUDED_KEYS and not _XYZ_EXCLUDED_PATTERN.match(key)]
            atm = Atoms(
                symbols=config["symbols"],
                positions=config["positions"],
                cell=config["cell"],
                pbc=config["pbc"],
            )
            atm.pbc = config["pbc"]
            atm.info = {}

            if write_params:
                for key in params:
                    atm.info[key] = config[key]

            if len(atm.get_chemical_symbols()) == 1 and not atm.get_pbc().all():
                atm.info["config_type"] = "IsolatedAtom"

            if "dft_stress" in config:
                s = convert_stress(config["dft_stress"])
                if key_prefix:
                    # A custom-prefixed key isn't recognized by ASE's extxyz writer, so it
                    # must already be a plain formatted string rather than a numpy array.
                    atm.info[f"{key_prefix}stress"] = " ".join(f"{v:.6f}" for v in s.reshape(-1))
                else:
                    # ASE's extxyz writer inspects the unprefixed "stress" key itself
                    # (expects an array, not a string) to detect and expand Voigt notation.
                    atm.info["stress"] = s.reshape(3, 3)

            if "dft_energy" in config:
                atm.info[f"{key_prefix}energy"] = config["dft_energy"]

            if "dft_forces" in config:
                atm.calc = SinglePointCalculator(atm, forces=config["dft_forces"])

            with StringIO() as buf, redirect_stdout(buf):
                write("-", atm, format="extxyz", write_results=True, write_info=True)
                dataset_txt += buf.getvalue()

        if key_prefix:
            dataset_txt = dataset_txt.replace(":forces", f":{key_prefix}forces")

        return dataset_txt

    def get_unlabelled(self):
        """Return a PESData object with only unlabelled frames."""
        if self.base.attributes.get("num_labelled_frames") == 0:
            return self
        unlabelled_data = [
            config for config in self.iter_items() if "dft_forces" not in config or "dft_energy" not in config
        ]
        return PESData(data=unlabelled_data)

    def get_labelled(self):
        """Return a PESData object with only labelled frames."""
        if self.base.attributes.get("num_unlabelled_frames") == 0:
            return self
        labelled_data = [config for config in self.iter_items() if "dft_forces" in config and "dft_energy" in config]
        return PESData(data=labelled_data)

    def get_training(self):
        """Return a PESData object with only the frames belonging to the training set."""
        training_data = [config for config in self.iter_items() if config.get("set") == SET_TRAINING]
        return PESData(data=training_data)

    def get_validation(self):
        """Return a PESData object with only the frames belonging to the validation set."""
        validation_data = [config for config in self.iter_items() if config.get("set") == SET_VALIDATION]
        return PESData(data=validation_data)

    def get_test(self):
        """Return a PESData object with only the frames belonging to the test set."""
        test_data = [config for config in self.iter_items() if config.get("set") == SET_TEST]
        return PESData(data=test_data)

    def get_no_set(self):
        """Return a PESData object with only the frames not assigned to any set."""
        no_set_data = [config for config in self.iter_items() if config.get("set") not in SET_LABELS]
        return PESData(data=no_set_data)

    @property
    def len_unlabelled(self):
        """Return the number of unlabelled configurations in the dataset."""
        if "num_unlabelled_frames" in self.base.attributes:
            return self.base.attributes.get("num_unlabelled_frames")
        return len(self.get_unlabelled())

    @property
    def len_labelled(self):
        """Return the number of labelled configurations in the dataset."""
        if "num_labelled_frames" in self.base.attributes:
            return self.base.attributes.get("num_labelled_frames")
        return len(self.get_labelled())

    @property
    def len_training(self):
        """Return the number of training-set configurations in the dataset."""
        if "num_training_frames" in self.base.attributes:
            return self.base.attributes.get("num_training_frames")
        return len(self.get_training())

    @property
    def len_validation(self):
        """Return the number of validation-set configurations in the dataset."""
        if "num_validation_frames" in self.base.attributes:
            return self.base.attributes.get("num_validation_frames")
        return len(self.get_validation())

    @property
    def len_test(self):
        """Return the number of test-set configurations in the dataset."""
        if "num_test_frames" in self.base.attributes:
            return self.base.attributes.get("num_test_frames")
        return len(self.get_test())

    @property
    def len_no_set(self):
        """Return the number of configurations not assigned to any set."""
        if "num_no_set_frames" in self.base.attributes:
            return self.base.attributes.get("num_no_set_frames")
        return len(self.get_no_set())

    def iter_ase(self, max_items=None):
        """Generator function to iterate through ASE Atoms objects without loading all into memory.

        :param max_items: Optional limit to the number of items to process
        :yield: ASE Atoms objects one at a time
        """
        for i, config in enumerate(self.iter_items()):
            if max_items is not None and i >= max_items:
                break
            yield self._config_to_ase(config)

    def get_e0s(self, fmt="atomic_numbers") -> dict:
        """Get the energies of isolated atoms from the dataset.

        :param fmt: Format of the atomic species ('atomic_numbers' or 'symbols')
        :return: dictionary of isolated atom energies
        """
        e0s = {k: None for k in self.get_atomic_species()}
        for config in self.iter_items():
            if not all(config["pbc"]) and len(config["symbols"]) == 1 and "dft_energy" in config:
                e0s[config["symbols"][0]] = config["dft_energy"]
        if fmt == "atomic_numbers":
            e0s = {atomic_numbers[k]: v for k, v in e0s.items()}
        return e0s
