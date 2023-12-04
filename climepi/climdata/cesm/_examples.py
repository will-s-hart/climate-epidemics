"""
Module for creating and accessing example CESM LENS2 datasets. If a directory named
'data/cesm_examples' exists in the same parent directory as the climepi package, the
example datasets will be downloaded to and accessed from that directory. Otherwise,
the datasets will be downloaded to and accessed from the OS cache directory. Running
this module as a script will create all example datasets by downloading and formatting
the relevant CESM LENS2 output data.
"""

import pathlib

import numpy as np
import pooch
import xcdat

import climepi.climdata.cesm as cesm

BASE_DIR = pathlib.Path(__file__).parents[3] / "data/cesm_examples"
if not BASE_DIR.exists():
    BASE_DIR = pathlib.Path(pooch.os_cache("climepi/cesm_examples"))
EXAMPLES = {
    "world_2020_2060_2100": {
        "data_dir": BASE_DIR / "world_2020_2060_2100",
        "subset": {
            "years": [2020, 2060, 2100],
        },
        "climepi_modes": {
            "spatial": "global",
            "temporal": "monthly",
            "ensemble": "ensemble",
        },
    },
    "cape_town": {
        "data_dir": BASE_DIR / "cape_town",
        "subset": {
            "years": np.arange(2000, 2101),
            "loc_str": "Cape Town",
        },
        "climepi_modes": {
            "spatial": "single",
            "temporal": "monthly",
            "ensemble": "ensemble",
        },
    },
}


def get_example_dataset(name):
    try:
        example_details = EXAMPLES[name]
    except KeyError as exc:
        raise ValueError(
            f"Example data '{name}' not found. Available examples are: "
            f"{', '.join(EXAMPLES.keys())}"
        ) from exc

    data_dir = example_details["data_dir"]
    data_getter = cesm.CESMDataGetter(**example_details["subset"], save_dir=data_dir)
    file_names = data_getter.file_names

    pup = pooch.create(
        base_url="",
        path=data_dir,
        registry={file_name: None for file_name in file_names},
    )

    try:
        paths = [pup.fetch(file_name) for file_name in file_names]
    except ValueError as exc:
        raise NotImplementedError(
            "The formatted example dataset was not found locally and is not yet"
            + " available to download directly. Run 'create_example_data' to create"
            + " and download the formatted dataset from CESM output data."
        ) from exc

    ds = xcdat.open_mfdataset(paths)
    ds.climepi.modes = example_details["climepi_modes"]
    return ds


def create_example_dataset(name):
    """Create CESM LENS2 example dataset."""
    try:
        example_details = EXAMPLES[name]
    except KeyError as exc:
        raise ValueError(
            f"Example data '{name}' not found. Available examples are: "
            f"{', '.join(EXAMPLES.keys())}"
        ) from exc

    data_dir = example_details["data_dir"]
    subset = example_details["subset"]

    cesm.get_cesm_data(**subset, download=True, save_dir=data_dir)


if __name__ == "__main__":
    for example_name in EXAMPLES:
        create_example_dataset(example_name)
        # get_example_dataset(example_name)
