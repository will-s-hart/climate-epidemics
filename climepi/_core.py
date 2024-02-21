"""Core module for the climepi package. This module contains the
ClimEpiDatasetAccessor class for xarray datasets.
"""
import geoviews.feature as gf
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

    def ensemble_mean(self, data_var=None):
        """
        Computes the ensemble mean of a data variable.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the ensemble mean for. If not
            provided, all non-bound data variables will be used.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the ensemble mean of the selected data
            variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        ds_m = xr.Dataset(attrs=self._obj.attrs)
        ds_m[data_var] = self._obj[data_var].mean(dim="realization")
        ds_m.climepi.copy_var_attrs_from(self._obj, var=data_var)
        ds_m.climepi.copy_bnds_from(self._obj)
        ds_m.climepi.modes = dict(self.modes, ensemble="stats")
        return ds_m

    def ensemble_percentiles(self, data_var=None, values=None, **kwargs):
        """
        Computes ensemble percentiles of a data variable. Wraps
        xclim.ensembles.ensemble_percentiles.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the ensemble percentiles for.
            If not provided, all non-bound data variables will be used.
        values : list of float, optional
            Percentiles to compute. Defaults to [5, 50, 95] if not provided.
        **kwargs : dict, optional
            Additional keyword arguments to pass to
            xclim.ensembles.ensemble_percentiles.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the ensemble percentiles of the selected
            data variable(s).
        """
        if values is None:
            values = [5, 50, 95]
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        if isinstance(data_var, list) and len(data_var) == 1:
            # xclim.ensembles.ensemble_percentiles doesn't seem to work with a list of
            # length 1
            data_var = data_var[0]
        ds_p = xr.Dataset(attrs=self._obj.attrs)
        ds_p[data_var] = xclim.ensembles.ensemble_percentiles(
            self._obj[data_var], values, split=False, **kwargs
        ).rename({"percentiles": "percentile"})
        ds_p.climepi.copy_var_attrs_from(self._obj, var=data_var)
        ds_p.climepi.copy_bnds_from(self._obj)
        ds_p.climepi.modes = dict(self.modes, ensemble="stats")
        return ds_p

    def ensemble_mean_std_max_min(self, data_var=None, **kwargs):
        """
        Computes the ensemble mean, standard deviation, maximum, and minimum of
        a data variable. Wraps xclim.ensembles.ensemble_mean_std_max_min.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the ensemble statistics for.
            If not provided, all non-bound data variables will be used.
        **kwargs : dict, optional
            Additional keyword arguments to pass to
            xclim.ensembles.ensemble_mean_std_max_min.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the computed ensemble statistics for the
            selected data variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        if isinstance(data_var, list):
            ds_stat_list = [
                self.ensemble_mean_std_max_min(data_var_curr, **kwargs)
                for data_var_curr in data_var
            ]
            ds_stat = xr.merge(ds_stat_list)
        else:
            ds_stat_xclim = xclim.ensembles.ensemble_mean_std_max_min(
                self._obj[data_var].to_dataset(), **kwargs
            )
            stat_list = ["mean", "std", "max", "min"]
            stat_list_xclim = [
                data_var + "_" + stat_list[i] for i in range(len(stat_list))
            ]
            stat_list_xclim[1] += "ev"
            ds_stat = xr.Dataset(attrs=self._obj.attrs)
            da_stat_xclim_list = [
                ds_stat_xclim[stat_list_xclim[i]]
                .rename(data_var)
                .expand_dims(dim={"ensemble_statistic": [stat_list[i]]}, axis=-1)
                for i in range(len(stat_list))
            ]
            ds_stat[data_var] = xr.concat(da_stat_xclim_list, dim="ensemble_statistic")
            ds_stat.climepi.copy_var_attrs_from(self._obj, var=data_var)
            ds_stat.climepi.copy_bnds_from(self._obj)
        ds_stat.climepi.modes = dict(self.modes, ensemble="stats")
        return ds_stat

    def ensemble_stats(self, data_var=None, conf_level=90, **kwargs):
        """
        Computes a range of ensemble statistics for a data variable.

        Parameters
        ----------
        data_var : str or list, optional
            Name(s) of the data variable(s) to compute the ensemble statistics for.
            If not provided, all non-bound data variables will be used.
        conf_level : float, optional
            Confidence level for computing ensemble percentiles.
        **kwargs : dict, optional
            Additional keyword arguments to pass to
            xclim.ensembles.ensemble_percentiles.

        Returns
        -------
        xarray.Dataset
            A new dataset containing the computed ensemble statistics for the
            selected data variable(s).
        """
        data_var = self._auto_select_data_var(data_var, allow_multiple=True)
        if isinstance(data_var, list) and len(data_var) == 1:
            # Problem squaring a dataset with a single data variable (this ensures a
            # DataArray is squared instead)
            data_var = data_var[0]
        ds_msmm = self._obj.climepi.ensemble_mean_std_max_min(data_var, **kwargs)
        ds_v = ds_msmm.sel(ensemble_statistic="std").copy()
        ds_v[data_var] = np.square(ds_v[data_var]).expand_dims(
            dim={"ensemble_statistic": ["var"]}
        )
        ds_mci = self._obj.climepi.ensemble_percentiles(
            data_var, [50 - conf_level / 2, 50, 50 + conf_level / 2], **kwargs
        )
        ds_mci = ds_mci.rename({"percentile": "ensemble_statistic"}).assign_coords(
            ensemble_statistic=["lower", "median", "upper"]
        )
        ds_stat = xr.concat(
            [ds_msmm, ds_v, ds_mci], dim="ensemble_statistic", data_vars="minimal"
        )
        ds_stat.climepi.modes = dict(self.modes, ensemble="stats")
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
        if "realization" in self._obj.sizes and len(self._obj.realization) > 1:
            raise ValueError(
                """The estimate_ensemble_stats method is only implemented for datasets
                with a single ensemble member. Use the ensemble_stats method instead."""
            )
        # Estimate ensemble mean by fitting a polynomial to each time series.
        fitted_polys = (
            self._obj[data_var_list]
            .squeeze("realization", drop=True)
            .polyfit(dim="time", deg=4, full=True)
        )
        poly_coeff_data_var_list = [x + "_polyfit_coefficients" for x in data_var_list]
        ds_m = xr.polyval(
            coord=self._obj.time,
            coeffs=fitted_polys[poly_coeff_data_var_list],
        ).rename(dict(zip(poly_coeff_data_var_list, data_var_list)))
        # Estimate ensemble variance/standard deviation using residuals from polynomial
        # fits (with an implicit assumption that the variance is constant in time).
        # Note that the calls to broadcast_like ensure broadcasting along the time
        # dimension (this should be equivalent to adding coords="minimal" when
        # concatenating the datasets, but is done explicitly here for clarity).
        poly_residual_data_var_list = [x + "_polyfit_residuals" for x in data_var_list]
        ds_v = (fitted_polys[poly_residual_data_var_list] / len(self._obj.time)).rename(
            dict(zip(poly_residual_data_var_list, data_var_list))
        )
        ds_s = np.sqrt(ds_v)
        ds_v = ds_v.broadcast_like(ds_m)
        ds_s = ds_s.broadcast_like(ds_m)
        # Estimate confidence intervals
        z = scipy.stats.norm.ppf(0.5 + conf_level / 200)
        ds_l = ds_m - z * ds_s
        ds_u = ds_m + z * ds_s
        # Combine into a single dataset
        ds_stat = xr.concat([ds_m, ds_v, ds_s, ds_l, ds_u], dim="ensemble_statistic")
        ds_stat = ds_stat.assign_coords(
            ensemble_statistic=["mean", "var", "std", "lower", "upper"]
        )
        ds_stat.climepi.copy_var_attrs_from(self._obj, var=data_var)
        ds_stat.climepi.copy_bnds_from(self._obj)
        ds_stat.climepi.modes = dict(self.modes, ensemble="stats")
        return ds_stat

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
            ds_stat = self._obj.climepi.ensemble_stats(data_var, conf_level)
            return ds_stat.climepi.plot_ensemble_ci_time_series(data_var, **kwargs)
        ds_ci = xr.Dataset(attrs=self._obj.attrs)
        ds_ci["lower"] = self._obj[data_var].sel(ensemble_statistic="lower")
        ds_ci["upper"] = self._obj[data_var].sel(ensemble_statistic="upper")
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
        da_central = self._obj[data_var].sel(ensemble_statistic=central)
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
        if not self._obj.climepi.modes["spatial"] == "grid":
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
