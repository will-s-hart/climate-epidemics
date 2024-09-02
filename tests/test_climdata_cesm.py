"""
Unit tests for the CESMDataGetter class in the _cesm.py module of the climdata
subpackage.
"""

from unittest.mock import patch

import intake_esm
import numpy as np
import pytest
import xarray as xr
import xarray.testing as xrt

from climepi.climdata._cesm import CESMDataGetter


def test_find_remote_data():
    """
    Test the _find_remote_data method of the CESMDataGetter class. The conversion of
    the intake_esm catalog to a dataset dictionary is mocked to avoid opening the
    actual remote data.
    """

    frequency = "monthly"
    ds = xr.Dataset(
        data_vars={
            var: xr.DataArray(np.random.rand(6, 4), dims=["time", "member_id"])
            for var in ["TREFHT", "PRECC", "PRECL"]
        },
        coords={
            "time": xr.DataArray(np.arange(6), dims="time"),
            "member_id": xr.DataArray(np.arange(4), dims="member_id"),
        },
    )

    def _mock_to_dataset_dict(catalog_subset, storage_options=None):
        assert sorted(catalog_subset.df.path.tolist()) == sorted(
            [
                "s3://ncar-cesm2-lens/atm/"
                + f"{frequency}/cesm2LE-{forcing}-{assumption}-{var}.zarr"
                for forcing in ["historical", "ssp370"]
                for assumption in ["cmip6", "smbb"]
                for var in ["TREFHT", "PRECC", "PRECL"]
            ]
        )
        assert storage_options == {"anon": True}
        return {
            "atm." + forcing + ".monthly." + assumption: ds.isel(
                time=3 * (forcing == "ssp370") + np.arange(3),
                member_id=2 * (assumption == "smbb") + np.arange(2),
            )
            for forcing in ["historical", "ssp370"]
            for assumption in ["cmip6", "smbb"]
        }

    data_getter = CESMDataGetter(frequency="monthly")

    with patch.object(
        intake_esm.core.esm_datastore, "to_dataset_dict", _mock_to_dataset_dict
    ):
        data_getter._find_remote_data()

    xrt.assert_identical(data_getter._ds, ds)


@pytest.mark.parametrize("year_opt", ["single", "multiple"])
@pytest.mark.parametrize("lon_opt", ["single", "range_0_360", "range_180_180"])
def test_subset_remote_data(year_opt, lon_opt):
    """
    Test the _subset_remote_data method of the CESMDataGetter class.
    """
    time_lb = xr.cftime_range(start="2001-01-01", periods=36, freq="MS")
    time_rb = xr.cftime_range(start="2001-02-01", periods=36, freq="MS")
    time_bnds = xr.DataArray(np.array([time_lb, time_rb]).T, dims=("time", "nbnd"))
    time = time_bnds.mean(dim="nbnd")
    ds_all = xr.Dataset(
        data_vars={
            "gus": xr.DataArray(
                np.random.rand(36, 4, 3, 5), dims=["time", "member_id", "lat", "lon"]
            ),
            "time_bnds": time_bnds,
        },
        coords={
            "time": time,
            "member_id": xr.DataArray(["id1", "id2", "id3", "id4"], dims="member_id"),
            "lat": xr.DataArray([-30, 15, 60], dims="lat"),
            "lon": xr.DataArray([0, 50, 180, 230, 359], dims="lon"),
        },
    )

    if year_opt == "single":
        years = 2002
        time_inds_expected = slice(12, 24)
    elif year_opt == "multiple":
        years = [2002, 2003]
        time_inds_expected = slice(12, 36)
    if lon_opt == "single":
        location = "Los Angeles"
        lat_range = None
        lon_range = None
        lat_inds_expected = 1
        lon_inds_expected = 3
    elif lon_opt == "range_0_360":
        location = None
        lat_range = [10, 60]
        lon_range = [15, 240]
        lat_inds_expected = [1, 2]
        lon_inds_expected = [1, 2, 3]
    elif lon_opt == "range_180_180":
        location = None
        lat_range = [-20, 30]
        lon_range = [-30, 60]
        lat_inds_expected = [1]
        lon_inds_expected = [0, 1, 4]
    subset = {
        "years": years,
        "realizations": [0, 2],
        "location": location,
        "lat_range": lat_range,
        "lon_range": lon_range,
    }
    data_getter = CESMDataGetter(frequency="monthly", subset=subset)
    data_getter._ds = ds_all
    data_getter._subset_remote_data()
    xrt.assert_identical(
        data_getter._ds,
        ds_all.isel(
            time=time_inds_expected,
            lat=lat_inds_expected,
            lon=lon_inds_expected,
            member_id=[0, 2],
        ),
    )
