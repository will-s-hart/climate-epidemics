import xarray as xr
import cf_xarray.units
import pint_xarray
import hvplot.xarray
import cartopy.crs
import xclim
import xcdat
import warnings

class _SharedClimEpiAccessor:
    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        # self._ensemble_type = None
        # self._geo_scope = None
        self._crs = None
    
    # @property
    # def ensemble_type(self):
    #     #Possible values: 'single' and 'multiple' (may add other options later)
    #     if self._ensemble_type is None:
    #         if 'realization' in self._obj.dims:
    #             self._ensemble_type = 'multiple'
    #         else:
    #             self._ensemble_type = 'single'
    #     return self._ensemble_type
    
    # @property
    # def geo_scope(self):
    #     #Possible values: 'single' and 'multiple' (may add other options later)
    #     if any(x in self._obj.sizes.keys() for x in ['lat','lon']):
    #         self._geo_scope = 'multiple'
    #     else:
    #         self._geo_scope = 'single'
    #     return self._geo_scope

    # @property
    # def temporal_scope(self):
    #     #Possible values: 'single' and 'multiple' (may add other options later)
    #     if 'time' in self._obj.sizes.keys():
    #         self._temporal_scope = 'multiple'
    #     else:
    #         self._temporal_scope = 'single'
    #     return self._temporal_scope

    @property
    def crs(self):
        if self._crs is None:
            if 'crs' in self._obj.attrs:
                self._crs = cartopy.crs.CRS.from_cf(self._obj.attrs['crs'])
            else:
                self._crs = cartopy.crs.PlateCarree()
                warnings.warn('PlateCarree CRS assumed.') #TODO: Add setter method to set crs and mention it here.
        return self._crs

@xr.register_dataset_accessor("climepi")
class ClimEpiDatasetAccessor(_SharedClimEpiAccessor):
    
    def annual_mean(self, data_var):
        if 'time' not in self._obj.sizes:
            raise ValueError('Annual mean only defined for time series.')
        ds_m = self._obj.temporal.group_average(data_var, freq='year')
        return ds_m
    
    def ensemble_mean(self, data_var):
        if 'realization' not in self._obj.sizes:
            raise ValueError('Ensemble mean only defined for ensemble data.')
        ds_m = xr.Dataset(attrs=self._obj.attrs)
        ds_m[data_var] = self._obj[data_var].mean(dim='realization')
        ds_m[data_var].attrs = self._obj[data_var].attrs
        ds_m[data_var].attrs['ensemble_mode'] = 'mean'
        self._copy_bnds(ds_m)
        return ds_m
    
    def ensemble_percentiles(self, data_var, values, **kwargs):
        if 'realization' not in self._obj.sizes:
            raise ValueError('Ensemble percentiles only defined for ensemble data.')
        ds_p = xr.Dataset(attrs=self._obj.attrs)
        ds_p[data_var] = xclim.ensembles.ensemble_percentiles(self._obj[data_var], values, split=False, **kwargs)
        ds_p[data_var].attrs = self._obj[data_var].attrs
        ds_p[data_var].attrs['ensemble_mode'] = 'percentiles'
        self._copy_bnds(ds_p)
        return ds_p
    
    def ensemble_mean_conf(self, data_var, conf_level = 90, **kwargs):
        if 'realization' not in self._obj.sizes:
            raise ValueError('Ensemble statistics only defined for ensemble data.')
        ds_m = self.ensemble_mean(data_var)
        ds_p = self.ensemble_percentiles(data_var, [50-conf_level/2, 50+conf_level/2], **kwargs)
        da_m = ds_m[data_var].expand_dims(dim={'statistic':['mean']})
        da_p = ds_p[data_var].rename({'percentiles':'statistic'}).assign_coords(statistic=['lower','upper'])
        ds_mp = xr.Dataset(attrs=self._obj.attrs)
        ds_mp[data_var] = xr.concat([da_m,da_p], dim='statistic')
        ds_mp.assign_coords(statistic=['mean','lower','upper'])
        ds_mp[data_var].attrs['ensemble_mode'] = 'mean and CI'
        self._copy_bnds(ds_mp)
        return ds_mp

    def plot_time_series(self, data_var, **kwargs):
        da_plot = self._obj[data_var]
        if 'time' not in da_plot.sizes:
            raise ValueError('Time series plot only defined for time series.')
        kwargs_hvplot = {'x':'time', 'frame_width':600}
        kwargs_hvplot.update(kwargs)
        return da_plot.hvplot.line(**kwargs_hvplot)
    
    def plot_map(self, data_var, **kwargs):
        da_plot = self._obj[data_var]
        if any(x not in da_plot.sizes for x in ('lat','lon')):
            raise ValueError('Map plot only defined for spatial data.')
        elif any(x not in ['time','lat','lon'] for x in da_plot.sizes):
            raise ValueError('Input variable has unsupported dimensions.')
        kwargs_hvplot = {'x':'lon','y':'lat','groupby':'time','cmap':'viridis', 'project':True, 'geo':True, 'rasterize':True, 'coastline':True, 'frame_width':600, 'dynamic':False}
        kwargs_hvplot.update(kwargs)
        if 'crs' not in kwargs_hvplot:
            kwargs_hvplot['crs'] = self.crs
        return da_plot.hvplot.quadmesh(**kwargs_hvplot)
    
    def plot_ensemble_mean_conf(self, data_var, conf_level = None, **kwargs):
        if 'realization' in self._obj.sizes:
            return self.ensemble_mean_conf(data_var,conf_level).climepi.plot_ensemble_mean_conf(data_var, **kwargs)
        elif 'ensemble_mode' not in self._obj[data_var].attrs or self._obj[data_var].attrs['ensemble_mode'] != 'mean and CI':
            raise ValueError('Invalid ensemble input type or formatting.')
        else:
            da_mean = self._obj[data_var].sel(statistic='mean')
            ds_ci = xr.Dataset(attrs=self._obj.attrs)
            ds_ci['lower'] = self._obj[data_var].sel(statistic='lower')
            ds_ci['upper'] = self._obj[data_var].sel(statistic='upper')
            kwargs_hvplot = {'x':'time','frame_width':600}
            kwargs_hvplot.update(kwargs)
            return ds_ci.hvplot.area(y='lower',y2='upper', alpha=0.2, **kwargs_hvplot) * da_mean.hvplot(**kwargs_hvplot)
    
    def _copy_bnds(self, ds_to):
        for var in ['lat_bnds','lon_bnds','time_bnds']:
            if var in self._obj.data_vars:
                ds_to[var] = self._obj[var]
                ds_to[var].attrs = self._obj[var].attrs

@xr.register_dataarray_accessor("climepi")
class ClimEpiDataArrayAccessor(_SharedClimEpiAccessor):

    pass
    
if __name__ == "__main__":
    import climdata.cesm as cesm
    ds = cesm.import_data()
    # ds = xr.tutorial.open_dataset('air_temperature').rename_vars({'air':'temperature'}).isel(time=range(10)).expand_dims(dim={'realization':[0]},axis=3)
    ds_tmm = ds.climepi.annual_mean('temperature')
    ds_tmm_ensmean = ds_tmm.climepi.ensemble_mean('temperature')
    ds_tmm_perc_ex = ds_tmm.sel(lon=0, lat=0, method='nearest').climepi.ensemble_percentiles('temperature', [5,50,95])
    ds_tmm_stats_ex = ds_tmm.sel(lon=0, lat=0, method='nearest').climepi.ensemble_mean_conf('temperature', conf_level = 90)
    ds_tmm_stats_ex.climepi.plot_ensemble_mean_conf('temperature')
    ds_tmm