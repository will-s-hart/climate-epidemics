import cftime
import numpy as np
import numpy.testing as npt
import pytest
import xarray as xr
import xarray.testing as xrt

from climepi import ClimEpiDatasetAccessor  # noqa
from climepi.testing.fixtures import generate_dataset, generate_epi_model


def test__init__():
    """Test the __init__ method of the ClimEpiDatasetAccessor class."""
    ds = generate_dataset()
    accessor = ClimEpiDatasetAccessor(ds)
    xrt.assert_identical(accessor._obj, ds)


def test_run_epi_model():
    """
    Test the run_epi_model method of the ClimEpiDatasetAccessor class. Only test that
    the method returns the same result as the run method of the EpiModel class. The run
    method of the EpiModel class is tested in the test module for the epimod subpackage.
    """
    ds = generate_dataset()
    epi_model = generate_epi_model()
    result = ds.climepi.run_epi_model(epi_model)
    expected = epi_model.run(ds)
    xrt.assert_identical(result, expected)


@pytest.mark.parametrize("lon_0_360", [True, False])
def test_sel_geo(lon_0_360):
    """Test the sel_geo method of the ClimEpiDatasetAccessor class."""
    ds = generate_dataset(lon_0_360=lon_0_360)
    location = "Miami"
    lat = 25.7617
    lon = -80.1918
    if lon_0_360:
        lon = lon % 360
    result = ds.climepi.sel_geo(location=location)
    lat_result = result.lat.values
    lon_result = result.lon.values
    lat_expected = ds.lat.sel(lat=lat, method="nearest").values
    lon_expected = ds.lon.sel(lon=lon, method="nearest").values
    npt.assert_allclose(lat_result, lat_expected)
    npt.assert_allclose(lon_result, lon_expected)


@pytest.mark.parametrize("frequency", ["yearly", "monthly", "daily"])
class TestTemporalGroupAverage:
    """
    Class defining tests for the temporal_group_average method of the
    ClimEpiDatasetAccessor class.
    """

    def test_temporal_group_average(self, frequency):
        """
        Test the temporal_group_average method of the ClimEpiDatasetAccessor class,
        particularly the centering of the time values (which is added to the underlying
        xcdat temporal.group_average method).
        """
        time_lb = xr.cftime_range(start="2001-01-01", periods=365, freq="D")
        time_rb = xr.cftime_range(start="2001-01-02", periods=365, freq="D")
        time_bnds = xr.DataArray(np.array([time_lb, time_rb]).T, dims=("time", "bnds"))
        time = time_bnds.mean(dim="bnds")
        temperature_values_in = np.arange(365)
        ds = xr.Dataset(
            {
                "temperature": (("time"), temperature_values_in),
                "time_bnds": time_bnds,
            },
            coords={"time": time},
        )
        ds.time.attrs.update(bounds="time_bnds")
        ds["time"].encoding.update(calendar="standard")
        result = ds.climepi.temporal_group_average(frequency=frequency)
        time_index_result = result.get_index("time")
        temperature_values_result = result.temperature.values
        if frequency == "yearly":
            # Note no centering is performed when the time-averaged data has a single
            # time value
            temperature_values_expected = np.array([np.mean(temperature_values_in)])
            time_index_expected = xr.cftime_range(start="2001-01-01", periods=1)
        elif frequency == "monthly":
            temperature_values_expected = np.array(
                [
                    np.mean(
                        temperature_values_in[month_start : month_start + month_length]
                    )
                    for month_start, month_length in zip(
                        np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30]),
                        np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]),
                    )
                ]
            )
            ds_time_bnds_expected = xr.Dataset(
                {
                    "time_bnds": (
                        ("time", "bnds"),
                        np.array(
                            [
                                xr.cftime_range(
                                    start="2001-01-01", periods=12, freq="MS"
                                ),
                                xr.cftime_range(
                                    start="2001-02-01", periods=12, freq="MS"
                                ),
                            ]
                        ).T,
                    ),
                },
            )
            ds_time_bnds_expected["time"] = ds_time_bnds_expected["time_bnds"].mean(
                dim="bnds"
            )
            time_index_expected = ds_time_bnds_expected.get_index("time")
        elif frequency == "daily":
            temperature_values_expected = temperature_values_in
            time_index_expected = ds.get_index("time")
        npt.assert_allclose(temperature_values_result, temperature_values_expected)
        assert time_index_result.equals(time_index_expected)

    def test_temporal_group_average_varlist(self, frequency):
        """
        Test the temporal_group_average method of the ClimEpiDatasetAccessor class with a
        list of data variables.
        """
        data_vars = ["temperature", "precipitation"]
        ds = generate_dataset(data_var=data_vars)
        result = ds.climepi.temporal_group_average(frequency=frequency)
        for data_var in data_vars:
            expected = ds[[data_var, "time_bnds"]].climepi.temporal_group_average(
                frequency=frequency
            )
            xrt.assert_identical(result[data_var], expected[data_var])

    def test_temporal_group_average_datatypes(self, frequency):
        """
        Test that the temporal_group_average method of the ClimEpiDatasetAccessor class
        works with different data types.
        """
        ds_bool = generate_dataset(data_var="temperature", dtype=bool)
        ds_int = ds_bool.copy()
        ds_int["temperature"] = ds_int["temperature"].astype(int)
        ds_float = ds_int.copy()
        ds_float["temperature"] = ds_float["temperature"].astype(float)
        result_bool = ds_bool.climepi.temporal_group_average(frequency=frequency)
        result_int = ds_int.climepi.temporal_group_average(frequency=frequency)
        result_float = ds_float.climepi.temporal_group_average(frequency=frequency)
        xrt.assert_identical(result_bool, result_int)
        xrt.assert_identical(result_bool, result_float)


def test_yearly_average():
    """
    Test the yearly_average method of the ClimEpiDatasetAccessor class. Since this
    method is a thin wrapper around the temporal_group_average method, only test that
    this method returns the same result as calling temporal_group_average directly.
    """
    ds = generate_dataset()
    result = ds.climepi.yearly_average()
    expected = ds.climepi.temporal_group_average(frequency="yearly")
    xrt.assert_identical(result, expected)


def test_monthly_average():
    """
    Test the monthly_average method of the ClimEpiDatasetAccessor class. Since this
    method is a thin wrapper around the temporal_group_average method, only test that
    this method returns the same result as calling temporal_group_average directly.
    """
    ds = generate_dataset()
    result = ds.climepi.monthly_average()
    expected = ds.climepi.temporal_group_average(frequency="monthly")
    xrt.assert_identical(result, expected)


class TestMonthsSuitable:
    """
    Class defining tests for the months_suitable method of the ClimEpiDatasetAccessor
    class.
    """

    def test_months_suitable(self):
        """
        Main test for the months_suitable method of the ClimEpiDatasetAccessor class.
        """
        time_lb = xr.cftime_range(start="2001-01-01", periods=24, freq="MS")
        time_rb = xr.cftime_range(start="2001-02-01", periods=24, freq="MS")
        time_bnds = xr.DataArray(np.array([time_lb, time_rb]).T, dims=("time", "bnds"))
        time = time_bnds.mean(dim="bnds")
        suitability_values_in = np.random.rand(24, 2)
        ds = xr.Dataset(
            {
                "suitability": (("time", "kenobi"), suitability_values_in),
                "time_bnds": time_bnds,
            },
            coords={"time": time},
        )
        ds.time.attrs.update(bounds="time_bnds")
        ds["time"].encoding.update(calendar="standard")
        suitability_threshold = 0.5
        result = ds.climepi.months_suitable(suitability_threshold=suitability_threshold)
        months_suitable_values_result = result.months_suitable.values
        months_suitable_values_expected = np.array(
            [
                np.sum(suitability_values_in[:12, :] > suitability_threshold, axis=0),
                np.sum(suitability_values_in[12:, :] > suitability_threshold, axis=0),
            ]
        )
        npt.assert_allclose(
            months_suitable_values_result, months_suitable_values_expected
        )

    def test_months_suitable_var_names(self):
        """
        Test the months_suitable method of the ClimEpiDatasetAccessor class with
        different data variable names present in the dataset.
        """
        data_vars = ["suitability", "also_suitability", "temperature"]
        ds = generate_dataset(data_var=data_vars)
        ds["suitability"].values = np.random.rand(*ds["suitability"].shape)
        ds["also_suitability"].values = ds["suitability"].values
        ds["temperature"].values = np.random.rand(*ds["temperature"].shape)
        suitability_threshold = 0.2
        result1 = ds.climepi.months_suitable(
            suitability_threshold=suitability_threshold
        )
        result2 = ds.climepi.months_suitable(
            suitability_threshold=suitability_threshold,
            suitability_var_name="also_suitability",
        )
        xrt.assert_allclose(result1["months_suitable"], result2["months_suitable"])
        result3 = ds[["also_suitability", "time_bnds"]].climepi.months_suitable(
            suitability_threshold=suitability_threshold,
        )
        xrt.assert_allclose(result1["months_suitable"], result3["months_suitable"])
        result4 = ds.climepi.months_suitable(
            suitability_threshold=suitability_threshold,
            suitability_var_name="temperature",
        )
        with pytest.raises(AssertionError):
            xrt.assert_allclose(result1["months_suitable"], result4["months_suitable"])
        with pytest.raises(ValueError):
            ds[
                ["also_suitability", "temperature", "time_bnds"]
            ].climepi.months_suitable(suitability_threshold=suitability_threshold)


class TestEnsembleStats:
    """
    Class defining tests for the ensemble_stats method of the ClimEpiDatasetAccessor.
    """

    def test_ensemble_stats(self):
        """
        Main test for the ensemble_stats method of the ClimEpiDatasetAccessor class.
        """
        ds = generate_dataset(data_var="temperature", extra_dims={"realization": 3})
        ds["temperature"].values = np.random.rand(*ds["temperature"].shape)
        result = ds.climepi.ensemble_stats(conf_level=60)
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="mean", drop=True),
            ds["temperature"].mean(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="std", drop=True),
            ds["temperature"].std(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="var", drop=True),
            ds["temperature"].var(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="median", drop=True),
            ds["temperature"].median(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="min", drop=True),
            ds["temperature"].min(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="max", drop=True),
            ds["temperature"].max(dim="realization"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="lower", drop=True),
            ds["temperature"].quantile(0.2, dim="realization").drop_vars("quantile"),
        )
        xrt.assert_allclose(
            result["temperature"].sel(ensemble_stat="upper", drop=True),
            ds["temperature"].quantile(0.8, dim="realization").drop_vars("quantile"),
        )

    def test_ensemble_stats_varlist(self):
        """
        Test the ensemble_stats method of the ClimEpiDatasetAccessor class with a list
        of data variables.
        """
        data_vars = ["temperature", "precipitation"]
        ds = generate_dataset(data_var=data_vars, extra_dims={"realization": 3})
        ds["temperature"].values = np.random.rand(*ds["temperature"].shape)
        ds["precipitation"].values = np.random.rand(*ds["precipitation"].shape)
        result = ds.climepi.ensemble_stats()
        for data_var in data_vars:
            xrt.assert_allclose(
                result[data_var],
                ds[[data_var]].climepi.ensemble_stats()[data_var],
            )
            xrt.assert_allclose(
                result[data_var],
                ds.climepi.ensemble_stats(data_var)[data_var],
            )

    def test_ensemble_stats_single_realization(self):
        """
        Test the ensemble_stats method of the ClimEpiDatasetAccessor class with a single
        realization, with the option to estimate internal variability at its default on
        value (only test that this gives the same result as the estimate_ensemble_stats
        method, which is tested separately).
        """
        ds1 = generate_dataset(data_var="temperature")
        ds1["temperature"].values = np.random.rand(*ds1["temperature"].shape)
        ds2 = ds1.copy()
        ds2["temperature"] = ds2["temperature"].expand_dims("realization")
        ds3 = ds1.copy()
        ds3["realization"] = "googly"
        ds3 = ds3.set_coords("realization")
        result1 = ds1.climepi.ensemble_stats()
        result2 = ds2.climepi.ensemble_stats()
        result3 = ds3.climepi.ensemble_stats()
        expected = ds1.climepi.estimate_ensemble_stats()
        xrt.assert_allclose(result1, expected)
        xrt.assert_allclose(result2, expected)
        xrt.assert_allclose(result3, expected)

    def test_ensemble_stats_single_realization_no_estimation(self):
        """
        Test the ensemble_stats method of the ClimEpiDatasetAccessor class with a single
        realization, with the option to estimate internal variability turned off.
        """
        ds1 = generate_dataset(data_var="temperature")
        ds1["temperature"].values = np.random.rand(*ds1["temperature"].shape)
        ds2 = ds1.copy()
        ds2["temperature"] = ds2["temperature"].expand_dims("realization")
        ds3 = ds1.copy()
        ds3["realization"] = "googly"
        ds3 = ds3.set_coords("realization")
        result1 = ds1.climepi.ensemble_stats(estimate_internal_variability=False)
        result2 = ds2.climepi.ensemble_stats(estimate_internal_variability=False)
        result3 = ds3.climepi.ensemble_stats(estimate_internal_variability=False)
        xrt.assert_allclose(result1, result2)
        xrt.assert_allclose(result1, result3)
        for ensemble_stat in ["mean", "median", "min", "max", "lower", "upper"]:
            xrt.assert_allclose(
                result1["temperature"].sel(ensemble_stat=ensemble_stat, drop=True),
                ds1["temperature"],
            )
        for ensemble_stat in ["std", "var"]:
            npt.assert_allclose(
                result1["temperature"]
                .sel(ensemble_stat=ensemble_stat, drop=True)
                .values,
                0,
            )


class TestEstimateEnsembleStats:
    """
    Class defining tests for the estimate_ensemble_stats method of the
    ClimEpiDatasetAccessor class.
    """

    def test_estimate_ensemble_stats(self):
        pass

    def test_estimate_ensemble_stats_varlist(self):
        pass

    def test_estimate_ensemble_stats_contains_realization(self):
        ds_base = generate_dataset(data_var="temperature")
        ds_base["temperature"].values = np.random.rand(*ds_base["temperature"].shape)
        ds1 = ds_base.copy()
        ds1["temperature"] = ds1["temperature"].expand_dims("realization")
        ds2 = ds_base.copy()
        ds2["realization"] = "googly"
        ds2 = ds2.set_coords("realization")
        result1 = ds1.climepi.ensemble_stats()
        result2 = ds2.climepi.ensemble_stats()
        expected = ds_base.climepi.estimate_ensemble_stats()
        xrt.assert_allclose(result1, expected)
        xrt.assert_allclose(result2, expected)
        ds3 = generate_dataset(extra_dims={"realization": 3})
        ds3["temperature"].values = np.random.rand(*ds3["temperature"].shape)
        with pytest.raises(ValueError):
            ds3.climepi.estimate_ensemble_stats()
