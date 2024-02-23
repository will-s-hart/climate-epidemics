"""Core module for the climepi package. This module contains the
ClimEpiDatasetAccessor class for xarray datasets.
"""
import geoviews.feature as gf
import holoviews as hv
import hvplot.xarray  # noqa # pylint: disable=unused-import
import numpy as np
import scipy.stats
import xarray as xr
import xcdat  # noqa # pylint: disable=unused-import
import xclim.ensembles
from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="climepi")


@xr.register_dataset_accessor("climepi")
class ClimEpiDatasetAccessor:
    """
    Accessor class providing core methods, including for computing temporal and
    ensemble statistics, and for plotting, to xarray datasets through the ``.climepi``
    attribute.
    """

    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        self._modes = {}

    @property
    def modes(self):
        """
        Gets and sets a dictionary containing properties of the dataset used by climepi.
        The dictionary should contain the following keys and currently supported values:
        modes = {
            "spatial": "grid" or "single",
            "temporal": "monthly" or "yearly",
            "ensemble": "ensemble", "single" or "stats",
        }
        """
        return self._modes

    @modes.setter
    def modes(self, modes_in):
        # assert isinstance(modes_in, dict)
        # assert all(key in ["spatial", "temporal", "ensemble"] for key in modes_in)
        # assert all(key in modes_in for key in ["spatial", "temporal", "ensemble"])
        # assert modes_in["spatial"] in ["grid"]
        # assert modes_in["temporal"] in ["monthly", "yearly"]
        # assert modes_in["ensemble"] in ["ensemble", "single", "stats"]
        self._modes = modes_in

    def temporal_group_average(self, data_var=None, frequency="yearly", **kwargs):
        """
        Computes the group average of a data variable. Wraps xcdat
        temporal.group_average.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the group average for. If not
            provided, all non-bound data variables will be used.
        frequency : str, optional
            Frequency to compute the group average for (options are "yearly", "monthly"
            or "daily").
        **kwargs : dict, optional
            Additional keyword arguments to pass to xcdat temporal.group_average.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the group average of the selected data
            variable(s) at the specified frequency.
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        xcdat_freq_map = {"yearly": "year", "monthly": "month", "daily": "day"}
        xcdat_freq = xcdat_freq_map[frequency]
        if isinstance(data_var, list):
            ds_m_list = [
                self.temporal_group_average(data_var_curr, frequency)
                for data_var_curr in data_var
            ]
            ds_m = xr.merge(ds_m_list)
        elif np.issubdtype(self._obj[data_var].dtype, np.integer) or np.issubdtype(
            self._obj[data_var].dtype, np.integer
        ):
            # Workaround for bug in xcdat temporal.group_average using integer or
            # boolean data types
            ds_copy = self._obj.copy()
            ds_copy[data_var] = ds_copy[data_var].astype("float64")
            ds_m = ds_copy.climepi.temporal_group_average(data_var, frequency)
        else:
            ds_m = self._obj.temporal.group_average(data_var, freq=xcdat_freq, **kwargs)
            ds_m = ds_m.bounds.add_time_bounds(method="freq", freq=xcdat_freq)
            ds_m = xcdat.center_times(ds_m)
        ds_m.climepi.modes = dict(self.modes, temporal=frequency)
        return ds_m

    def yearly_average(self, data_var=None, **kwargs):
        """
        Computes the yearly mean of a data variable. Thin wrapper around group_average.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the yearly mean for. If not
            provided, all non-bound data variables will be used.
        **kwargs : dict, optional
            Additional keyword arguments to pass to xcdat temporal.group_average.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the yearly mean of the selected data
            variable(s).
        """
        return self.temporal_group_average(
            data_var=data_var, frequency="yearly", **kwargs
        )

    def monthly_average(self, data_var=None, **kwargs):
        """
        Computes the monthly mean of a data variable. Thin wrapper around group_average.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the monthly mean for. If not
            provided, all non-bound data variables will be used.
        **kwargs : dict, optional
            Additional keyword arguments to pass to xcdat temporal.group_average.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the monthly mean of the selected data
            variable(s).
        """
        return self.temporal_group_average(
            data_var=data_var, frequency="monthly", **kwargs
        )

    def ensemble_stats(
        self,
        data_var=None,
        conf_level=90,
        estimate_internal_variability=True,
    ):
        """
        Computes a range of ensemble statistics for a data variable.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the ensemble statistics for.
            If not provided, all non-bound data variables will be used.
        conf_level : float, optional
            Confidence level for computing ensemble percentiles.
        estimate_internal_variability : bool, optional
            Whether to estimate internal variability using the estimate_ensemble_stats
            method if only a single realization is available for each model and scenario
            (ignored if multiple realizations are available). Default is True.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the computed ensemble statistics for the
            selected data variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        if estimate_internal_variability and not (
            "realization" in self._obj.dims and len(self._obj.realization) > 1
        ):
            ds_stat = self.estimate_ensemble_stats(data_var, conf_level)
            return ds_stat
        ds_raw = self._obj[data_var]  # drops bounds for now (re-add at end)
        if "realization" not in self._obj.dims:
            ds_raw = ds_raw.expand_dims(dim="realization")
        ds_mean = ds_raw.mean(dim="realization").expand_dims(
            dim={"ensemble_stat": ["mean"]}, axis=-1
        )
        ds_std = ds_raw.std(dim="realization").expand_dims(
            dim={"ensemble_stat": ["std"]}, axis=-1
        )
        ds_var = ds_raw.var(dim="realization").expand_dims(
            dim={"ensemble_stat": ["var"]}, axis=-1
        )
        ds_quantile = ds_raw.quantile(
            [0, 0.5 - conf_level / 200, 0.5, 0.5 + conf_level / 200, 1],
            dim="realization",
        ).rename({"quantile": "ensemble_stat"})
        ds_quantile["ensemble_stat"] = ["min", "lower", "median", "upper", "max"]
        ds_stat = xr.concat(
            [ds_mean, ds_std, ds_var, ds_quantile],
            dim="ensemble_stat",
            coords="minimal",
        )
        if isinstance(ds_stat, xr.DataArray):
            ds_stat = ds_stat.to_dataset(name=data_var)
        ds_stat.climepi.modes = dict(self.modes, ensemble="stats")
        ds_stat.attrs = self._obj.attrs
        ds_stat.climepi.copy_var_attrs_from(self._obj, var=data_var)
        ds_stat.climepi.copy_bnds_from(self._obj)
        return ds_stat

    def estimate_ensemble_stats(self, data_var=None, conf_level=90):
        """
        Estimates ensemble statistics for a data variable by fitting a polynomial to
        a time series for a single ensemble member.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to estimate the ensemble statistics for.
            If not provided, all non-bound data variables will be used.
        conf_level : float, optional
            Confidence level for computing ensemble percentiles.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the estimated ensemble statistics for the
            selected data variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        if isinstance(data_var, str):
            data_var_list = [data_var]
        else:
            data_var_list = data_var
        # Estimate ensemble mean by fitting a polynomial to each time series.
        ds_raw = self._obj[data_var_list]
        if "realization" in ds_raw.sizes:
            if len(ds_raw.realization) > 1:
                raise ValueError(
                    """The estimate_ensemble_stats method is only implemented for
                    datasets with a single ensemble member. Use the ensemble_stats
                    method instead.""",
                )
            ds_raw = ds_raw.squeeze("realization", drop=True)
        elif "realization" in ds_raw.coords:
            ds_raw = ds_raw.drop("realization")
        fitted_polys = ds_raw.polyfit(dim="time", deg=4, full=True)
        poly_coeff_data_var_list = [x + "_polyfit_coefficients" for x in data_var_list]
        ds_mean = xr.polyval(
            coord=ds_raw.time,
            coeffs=fitted_polys[poly_coeff_data_var_list],
        ).rename(dict(zip(poly_coeff_data_var_list, data_var_list)))
        # Estimate ensemble variance/standard deviation using residuals from polynomial
        # fits (with an implicit assumption that the variance is constant in time).
        # Note that the calls to broadcast_like ensure broadcasting along the time
        # dimension (this should be equivalent to adding coords="minimal" when
        # concatenating the datasets, but is done explicitly here for clarity).
        poly_residual_data_var_list = [x + "_polyfit_residuals" for x in data_var_list]
        ds_var = (fitted_polys[poly_residual_data_var_list] / len(ds_raw.time)).rename(
            dict(zip(poly_residual_data_var_list, data_var_list))
        )
        ds_std = np.sqrt(ds_var)
        ds_var = ds_var.broadcast_like(ds_mean)
        ds_std = ds_std.broadcast_like(ds_mean)
        # Estimate confidence intervals
        z = scipy.stats.norm.ppf(0.5 + conf_level / 200)
        ds_lower = ds_mean - z * ds_std
        ds_upper = ds_mean + z * ds_std
        # Combine into a single dataset
        ds_stat = xr.concat(
            [ds_mean, ds_var, ds_std, ds_lower, ds_upper],
            dim=xr.Variable("ensemble_stat", ["mean", "var", "std", "lower", "upper"]),
            coords="minimal",
        )
        ds_stat.climepi.copy_var_attrs_from(self._obj, var=data_var)
        ds_stat.climepi.copy_bnds_from(self._obj)
        ds_stat.climepi.modes = dict(self.modes, ensemble="stats")
        return ds_stat

    def var_decomp(
        self, data_var=None, fraction=True, estimate_internal_variability=True
    ):
        """
        Decomposes the variance of a data variable into internal, model and scenario
        uncertainty at each time point.

        Parameters
        ----------
        data_var : str
            Name of the data variable(s) to decompose.
        fraction : bool, optional
            Whether to calculate the variance contributions as fractions of the total
            variance at each time, or the raw variances. Default is True.
        estimate_internal_variability : bool, optional
            Whether to estimate internal variability if only a single realization is
            available for each model and scenario (ignored if multiple realizations
            are available). Default is True.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the variance decomposition of the selected data
            variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        ds_stat = self.ensemble_stats(
            data_var, estimate_internal_variability=estimate_internal_variability
        )
        ds_var_internal = ds_stat.sel(ensemble_stat="var", drop=True).mean(
            dim=["scenario", "model"]
        )
        ds_var_model = (
            ds_stat.sel(ensemble_stat="mean", drop=True)
            .var(dim="model")
            .mean(dim="scenario")
        )
        ds_var_scenario = (
            ds_stat.sel(ensemble_stat="mean", drop=True)
            .mean(dim="model")
            .var(dim="scenario")
        )
        ds_var_decomp = xr.concat(
            [ds_var_internal, ds_var_model, ds_var_scenario],
            dim=xr.Variable("var_type", ["internal", "model", "scenario"]),
            coords="minimal",
        )
        if fraction:
            ds_var_decomp = ds_var_decomp / ds_var_decomp.sum(dim="var_type")
        ds_var_decomp.climepi.copy_bnds_from(self._obj)
        return ds_var_decomp

    def plot_time_series(self, data_var=None, **kwargs):
        """
        Generates a time series plot of a data variable. Wraps hvplot.line.

        Parameters
        ----------
        data_var : str, optional
            Name of the data variable to plot. If not provided, the function
            will attempt to automatically select a suitable variable.
        **kwargs : dict
            Additional keyword arguments to pass to hvplot.line.

        Returns
        -------
        hvplot object
            The resulting time series plot.
        """
        data_var = self._auto_select_data_var(data_var)
        da_plot = self._obj[data_var]
        kwargs_hvplot = {"x": "time"}
        kwargs_hvplot.update(kwargs)
        plot_obj = da_plot.hvplot.line(**kwargs_hvplot)
        return plot_obj

    def plot_map(self, data_var=None, include_ocean=False, **kwargs):
        """
        Generates a map plot of a data variable. Wraps hvplot.quadmesh.

        Parameters
        ----------
        data_var : str, optional
            Name of the data variable to plot. If not provided, the function
            will attempt to automatically select a suitable variable.
        include_ocean : bool, optional
            Whether or not to include ocean data in the plot. Default is False.
        **kwargs : dict, optional
            Additional keyword arguments to pass to hvplot.quadmesh.

        Returns
        -------
        hvplot object
            The resulting map plot.
        """
        data_var = self._auto_select_data_var(data_var)
        da_plot = self._obj[data_var]
        kwargs_hvplot = {
            "x": "lon",
            "y": "lat",
            "cmap": "viridis",
            "project": True,
            "geo": True,
            "rasterize": True,
            "coastline": True,
            "dynamic": False,
        }
        if "time" in da_plot.sizes:
            kwargs_hvplot["groupby"] = "time"
        else:
            kwargs_hvplot["groupby"] = None
        kwargs_hvplot.update(kwargs)
        plot_obj = da_plot.hvplot.quadmesh(**kwargs_hvplot)
        if not include_ocean:
            plot_obj *= gf.ocean.options(fill_color="white")
        return plot_obj

    def plot_var_decomp(
        self, data_var=None, fraction=True, estimate_internal_variability=True, **kwargs
    ):
        """
        Plots the contributions of internal, model and scenario uncertainty to the total
        variance of a data variable over time. Wraps hvplot.area.

        Parameters
        ----------
        data_var : str
            Name of the data variable to plot.
        fraction : bool, optional
            Whether to plot the variance contributions as fractions of the total
            variance at each time, or the raw variances. Default is True.
        estimate_internal_variability : bool, optional
            Whether to estimate internal variability if only a single realization is
            available for each model and scenario (ignored if multiple realizations
            are available). Default is True.
        **kwargs : dict, optional
            Additional keyword arguments to pass to hvplot.area.

        Returns
        -------
        hvplot object
            The resulting plot object.
        """
        data_var = self._auto_select_data_var(data_var)
        ds_var_decomp = self.var_decomp(
            data_var, fraction, estimate_internal_variability
        )
        ds_plot = xr.Dataset(
            {
                "scenario": ds_var_decomp[data_var].sel(var_type="scenario", drop=True),
                "model": ds_var_decomp[data_var].sel(var_type="model", drop=True),
                "internal": ds_var_decomp[data_var].sel(var_type="internal", drop=True),
            }
        )
        plot_obj = ds_plot.hvplot.area(
            x="time",
            y=["scenario", "model", "internal"],
            group_label="Uncertainty type",
            ylabel="Fraction of total variance" if fraction else "Variance",
        )
        return plot_obj

    def plot_ci_plume(
        self, data_var=None, conf_level=90, estimate_internal_variability=True, **kwargs
    ):
        """
        Generates a plume plot showing contributions of internal, model and scenario
        uncertainty (as applicable) to confidence intervals for a data variable over
        time. Wraps hvplot.area.

        Parameters
        ----------
        data_var : str
            Name of the data variable to plot.
        conf_level : float, optional
            Confidence level for the confidence intervals. Default is 90.
        estimate_internal_variability : bool, optional
            Whether to estimate internal variability if only a single ensemble member is
            available for each model and realization. Default is True.
        kwargs : dict, optional
            Additional keyword arguments to pass to hvplot.area.

        Returns
        -------
        hvplot object
            The resulting plot object.
        """
        data_var = self._auto_select_data_var(data_var)
        ds_raw = self.sel_data_var(data_var)
        plot_obj_list = []
        # Make "scenario", "model" and "realization" dimensions of the data variable if
        # they don't or are (singleton) non-dimension coordinates (reduces number of
        # cases to handle)
        for dim in ["scenario", "model", "realization"]:
            if dim not in ds_raw.dims:
                ds_raw[data_var] = ds_raw[data_var].expand_dims(dim)
        # Get ensemble statistics, baseline estimate, and if necessary a decomposition
        # of the variance and z value for approximate confidence intervals
        ds_stat = ds_raw.climepi.ensemble_stats(
            data_var, conf_level, estimate_internal_variability
        )
        ds_baseline = ds_stat.sel(ensemble_stat="mean", drop=True).mean(
            dim=["scenario", "model"]
        )
        ds_var_decomp = ds_raw.climepi.var_decomp(
            data_var, estimate_internal_variability
        )
        z = scipy.stats.norm.ppf(0.5 + conf_level / 200)
        # Plot the baseline estimate
        kwargs_hv_baseline = {"x": "time", "label": "Mean"}
        kwargs_hv_baseline.update(kwargs)
        plot_obj_baseline = ds_baseline.hvplot.line(**kwargs_hv_baseline)
        plot_obj_list.append(plot_obj_baseline)
        # Plot internal variability if there are multiple realizations or if internal
        # variability is to be estimated
        multiple_realizations = len(ds_raw.realization) > 1
        if estimate_internal_variability or multiple_realizations:
            if len(ds_raw.scenario) == 1 and len(ds_raw.model) == 1:
                ds_ci_internal = xr.Dataset(
                    {
                        "lower": ds_stat.squeeze(["model", "scenario"], drop=True).sel(
                            ensemble_stat="lower"
                        ),
                        "upper": ds_stat.squeeze(["model", "scenario"], drop=True).sel(
                            ensemble_stat="upper"
                        ),
                    }
                )
            else:
                ds_std_internal = np.sqrt(
                    ds_var_decomp.sel(var_type="internal", drop=True)
                )
                ds_ci_internal = xr.Dataset(
                    {
                        "lower": ds_baseline - z * ds_std_internal,
                        "upper": ds_baseline + z * ds_std_internal,
                    }
                )
            kwargs_hv_internal = {
                "x": "time",
                "y": "lower",
                "y2": "upper",
                "alpha": 0.2,
                "label": "Internal",
            }
            kwargs_hv_internal.update(kwargs)
            plot_obj_internal = ds_ci_internal.hvplot.area(**kwargs_hv_internal)
            plot_obj_list.append(plot_obj_internal)
        # Plot model variability if there are multiple models
        if len(ds_raw.model) > 1:
            if len(ds_raw.scenario) == 1 and not (
                multiple_realizations or estimate_internal_variability
            ):
                ds_ci_internal_model = xr.Dataset(
                    {
                        "lower": ds_raw.squeeze(
                            ["scenario", "realization"], drop=True
                        ).quantile(0.5 - conf_level / 200, dim="model"),
                        "high": ds_raw.squeeze(
                            ["scenario", "realization"], drop=True
                        ).quantile(0.5 + conf_level / 200, dim="model"),
                    }
                )
            else:
                ds_std_internal_model = np.sqrt(
                    ds_var_decomp.sel(var_type=["internal", "model"]).sum(
                        dim="var_type"
                    )
                )
                ds_ci_internal_model = xr.Dataset(
                    {
                        "lower": ds_baseline - z * ds_std_internal_model,
                        "upper": ds_baseline + z * ds_std_internal_model,
                    }
                )
            kwargs_hv_model = {
                "x": "time",
                "y": "lower",
                "y2": "upper",
                "alpha": 0.2,
                "label": "Model",
            }
            kwargs_hv_model.update(kwargs)
            plot_obj_model = ds_ci_internal_model.hvplot.area(**kwargs_hv_model)
            plot_obj_list.append(plot_obj_model)
        # Plot scenario variability if there are multiple scenarios
        if len(ds_raw.scenario) > 1:
            if len(ds_raw.model) == 1 and not (
                multiple_realizations or estimate_internal_variability
            ):
                ds_ci_internal_model_scenario = xr.Dataset(
                    {
                        "lower": ds_raw.squeeze(
                            ["model", "realization"], drop=True
                        ).quantile(0.5 - conf_level / 200, dim="scenario"),
                        "high": ds_raw.squeeze(
                            ["model", "realization"], drop=True
                        ).quantile(0.5 + conf_level / 200, dim="scenario"),
                    }
                )
            else:
                ds_std_internal_model_scenario = np.sqrt(
                    ds_var_decomp.sum(dim="var_type")
                )
                ds_ci_internal_model_scenario = xr.Dataset(
                    {
                        "lower": ds_baseline - z * ds_std_internal_model_scenario,
                        "upper": ds_baseline + z * ds_std_internal_model_scenario,
                    }
                )
            kwargs_hv_scenario = {
                "x": "time",
                "y": "lower",
                "y2": "upper",
                "alpha": 0.2,
                "label": "Scenario",
            }
            kwargs_hv_scenario.update(kwargs)
            plot_obj_scenario = ds_ci_internal_model_scenario.hvplot.area(
                **kwargs_hv_scenario
            )
            plot_obj_list.append(plot_obj_scenario)
        # Combine the plots
        plot_obj = hv.Overlay(plot_obj_list.reverse())
        return plot_obj

    def plot_ensemble_ci_time_series(
        self, data_var=None, central="mean", conf_level=None, **kwargs
    ):
        """
        Generates a time series plot of the ensemble confidence interval and
        (optionally) central estimate for a data variable. Can be called either
        on an ensemble statistics dataset created using climepi.ensemble_stats,
        or on an ensemble dataset (in which case climepi.ensemble_stats is used
        to compute the statistics).

        Parameters
        ----------
        data_var : str, optional
            The name of the data variable to plot. If not provided, the
            function will attempt to automatically select a suitable variable.
        central : str, optional
            The central estimate to plot. Can be "mean", "median", or None. If
            None, only the confidence interval will be plotted.
        conf_level : float, optional
            The confidence level for the confidence interval. Has no effect if
            the method is called on an ensemble statistics dataset created
            using climepi.ensemble_stats (in which case the already calculated
            confidence interval is used). Otherwise, defaults to the default
            value of climepi.ensemble_stats.
        **kwargs : optional
            Additional keyword arguments to pass to the plotting functions.

        Returns
        -------
        hvplot object
            The resulting plot object.
        """
        data_var = self._auto_select_data_var(data_var)
        if "realization" in self._obj.sizes:
            ds_stat = self.ensemble_stats(data_var, conf_level)
            return ds_stat.climepi.plot_ensemble_ci_time_series(data_var, **kwargs)
        ds_ci = xr.Dataset(attrs=self._obj.attrs)
        ds_ci["lower"] = self._obj[data_var].sel(ensemble_stat="lower")
        ds_ci["upper"] = self._obj[data_var].sel(ensemble_stat="upper")
        kwargs_hv_ci = {
            "x": "time",
            "y": "lower",
            "y2": "upper",
            "alpha": 0.2,
        }
        kwargs_hv_ci.update(kwargs)
        plot_ci = ds_ci.hvplot.area(**kwargs_hv_ci)
        if central is None:
            return plot_ci
        da_central = self._obj[data_var].sel(ensemble_stat=central)
        kwargs_hv_central = {"x": "time"}
        kwargs_hv_central.update(kwargs)
        plot_central = da_central.hvplot.line(**kwargs_hv_central)
        plot_obj = plot_central * plot_ci
        return plot_obj

    def sel_data_var(self, data_var):
        """
        Returns a new dataset containing only the selected data variable(s) and any
        bounds variables.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to select.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the selected data variable(s) and any bounds
            variables.
        """
        ds_new = xr.Dataset(attrs=self._obj.attrs)
        ds_new[data_var] = self._obj[data_var]
        ds_new.climepi.copy_bnds_from(self._obj)
        ds_new.climepi.modes = self.modes
        return ds_new

    def sel_geopy(self, loc_str, **kwargs):
        """
        Uses geopy to obtain the latitude and longitude co-ordinates of the location
        specified in loc_str, and returns a new dataset containing the data for the
        nearest grid point.

        Parameters
        ----------
        loc_str : str
            Name of the location to select.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the data for the specified location.
        """
        if not self.modes["spatial"] == "grid":
            raise ValueError(
                """The sel_geopy method can only be used on datasets with climepi
                spatial mode "grid"."""
            )
        location = geolocator.geocode(loc_str, **kwargs)
        lat = location.latitude
        lon = location.longitude
        if max(self._obj.lon) > 180.001:
            # Deals with the case where the longitude co-ordinates are in the range
            # [0, 360] (slightly crude)
            lon = lon % 360
        ds_new = self._obj.sel(lat=lat, lon=lon, method="nearest")
        ds_new.climepi.modes = dict(self.modes, spatial="single")
        return ds_new

    def copy_var_attrs_from(self, ds_from, var):
        """
        Copies the attributes for a variable from another xarray dataset (ds_from) to
        this one.

        Parameters
        ----------
        ds_from : xarray.Dataset
            The dataset to copy the variable attributes from.
        var : str or list
            The name(s) of the variable(s) to copy the attributes for (both datasets
            must contain variable(s) with these names).

        Returns
        -------
        None
        """
        if isinstance(var, list):
            for var_curr in var:
                self.copy_var_attrs_from(ds_from, var_curr)
        else:
            self._obj[var].attrs = ds_from[var].attrs

    def copy_bnds_from(self, ds_from):
        """
        Copies the latitude, longitude, and time bounds from another xarray
        dataset (ds_from) to this one, whenever the bounds exist in ds_from but not this
        dataset and the corresponding co-ordinate dimension is the same for both
        datasets.

        Parameters
        ----------
        ds_from : xarray.Dataset
            The dataset to copy the bounds from.

        Returns
        -------
        None
        """
        for var in ["lat", "lon", "time"]:
            bnd_var = var + "_bnds"
            if (
                bnd_var in self._obj.data_vars
                or bnd_var not in ds_from.data_vars
                or not self._obj[var].equals(ds_from[var])
            ):
                continue
            self._obj[bnd_var] = ds_from[bnd_var]
            self._obj[bnd_var].attrs = ds_from[bnd_var].attrs
            self._obj[var].attrs.update(bounds=bnd_var)

    def get_non_bnd_data_vars(self):
        """
        Returns a list of the names of the non-bound variables in the dataset.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Names of the non-bound variables in the dataset.
        """
        data_vars = list(self._obj.data_vars)
        bnd_vars = ["lat_bnds", "lon_bnds", "time_bnds"]
        non_bnd_data_vars = [
            data_vars[i] for i in range(len(data_vars)) if data_vars[i] not in bnd_vars
        ]
        return non_bnd_data_vars

    def _auto_select_data_var(self, data_var_in, allow_multiple=False):
        # Method for obtaining the name of the data variable in the xarray
        # dataset, if only one is present (alongside latitude, longitude, and
        # time bounds).
        if data_var_in is not None and (isinstance(data_var_in, str) or allow_multiple):
            return data_var_in
        non_bnd_data_vars = self.get_non_bnd_data_vars()
        if len(non_bnd_data_vars) == 1:
            return non_bnd_data_vars[0]
        if allow_multiple:
            return non_bnd_data_vars
        raise ValueError(
            """Multiple data variables present. The data variable to use must be
            specified."""
        )
